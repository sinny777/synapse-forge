"""
LangGraph executor for real agent execution with SynapseForge.
"""

import sys
import time
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional, List
from pathlib import Path

from .base_executor import BaseAgentExecutor
from ..common.events import AgentEvent, EventType
from ..common.models import AgentScenario

logger = logging.getLogger(__name__)


class LangGraphExecutor(BaseAgentExecutor):
    """
    LangGraph executor that implements real agent execution.
    
    Uses LangGraph's StateGraph with supervisor pattern and integrates
    with SynapseForge for dynamic tool selection.
    """
    
    def __init__(self, scenario: AgentScenario, examples_dir: Path, model_path: str = None):
        """Initialize LangGraph executor"""
        super().__init__(scenario, examples_dir)
        self.router = None
        self.tools_retrieved = 0
        self.tools_executed = 0
        self.agents_executed = 0
        self.model_path = model_path
        
        # Map scenario IDs to example directories (must match mcp_manager.py)
        scenario_map = {
            "langgraph_banking": "langgraph_UHNW_banking",
        }
        
        # Get the correct example directory for this scenario
        example_dir_name = scenario_map.get(scenario.id, "langgraph_UHNW_banking")
        self.example_dir = examples_dir / example_dir_name
        
        # Add example directory to path for imports
        if str(self.example_dir) not in sys.path:
            sys.path.insert(0, str(self.example_dir))
    
    async def initialize(self):
        """Initialize LangGraph components and start MCP server"""
        try:
            logger.info("Initializing LangGraph executor...")
            
            # Start MCP server
            server_started = await self._start_mcp_server()
            if not server_started:
                raise RuntimeError("Failed to start MCP server")
            
            # Load module directly from file path to avoid import issues
            import importlib.util
            module_path = self.example_dir / "multi_agent_orchestrator.py"
            
            spec = importlib.util.spec_from_file_location(
                "multi_agent_orchestrator",
                module_path
            )
            orchestrator_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(orchestrator_module)
            
            ToolRouterForLangChain = orchestrator_module.ToolRouterForLangChain
            
            self.router = ToolRouterForLangChain(model_path=self.model_path)
            await self.router.initialize()
            
            self.initialized = True
            logger.info("✓ LangGraph executor initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize LangGraph executor: {e}")
            raise
    
    async def execute(
        self,
        user_query: str,
        llm_config: Optional[Dict[str, Any]] = None,
        runtime_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Execute LangGraph scenario with real tool execution.
        
        Args:
            user_query: The user's query
            llm_config: LLM configuration (model name, etc.)
            runtime_config: Runtime configuration
        
        Yields:
            AgentEvent objects representing real execution progress
        """
        if not self.initialized:
            raise RuntimeError("Executor not initialized. Call initialize() first.")
        
        try:
            # Import LangGraph components
            from langchain_openai import ChatOpenAI
            
            # Load module directly from file path
            import importlib.util
            module_path = self.example_dir / "multi_agent_orchestrator.py"
            
            spec = importlib.util.spec_from_file_location(
                "multi_agent_orchestrator_exec",
                module_path
            )
            if spec and spec.loader:
                orchestrator_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(orchestrator_module)
                LangChainToolAdapter = orchestrator_module.LangChainToolAdapter
            else:
                raise RuntimeError(f"Could not load module from {module_path}")
            
            # Get LLM
            model_name = llm_config.get("model", "gpt-4o") if llm_config else "gpt-4o"
            llm = ChatOpenAI(model=model_name, temperature=0)
            
            # Define agents with their queries for tool retrieval
            agents_config = [
                {
                    "name": "Portfolio Manager",
                    "role": "Investment Portfolio Specialist",
                    "query": "retrieve portfolio summary, unrealized gains losses, asset allocation holdings performance"
                },
                {
                    "name": "Trading Analyst",
                    "role": "Market & Trading Specialist",
                    "query": "live market data, execute trade buy sell, stock market news sentiment"
                },
                {
                    "name": "Tax & Compliance Officer",
                    "role": "Tax Optimization Specialist",
                    "query": "simulate capital gains tax, tax loss harvesting options, run AML transaction check"
                }
            ]
            
            # Execute each agent sequentially with context passing
            agent_context = {
                "user_query": user_query,
                "previous_results": []
            }
            
            for agent_config in agents_config:
                start_time = time.time()
                self.agents_executed += 1
                
                # Emit agent activated
                yield AgentEvent(
                    type=EventType.AGENT_ACTIVATED,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_config["name"],
                        "agent_role": agent_config["role"],
                        "framework": self.scenario.framework.value
                    }
                )
                
                # Retrieve tools using SynapseForge
                k = 3 if "Trading" in agent_config["name"] or "Tax" in agent_config["name"] else 2
                
                # Get tools with scores from semantic router
                tool_results = self.router.semantic_router.retrieve_tools(agent_config["query"], top_k=k, use_hybrid=True)
                tools_mcp = []
                tool_scores = {}
                for tool_id, score in tool_results:
                    if tool_id in self.router.all_tools:
                        tool_schema = self.router.all_tools[tool_id]
                        tools_mcp.append(tool_schema)
                        tool_scores[tool_id] = score
                
                self.tools_retrieved += len(tools_mcp)
                
                # Log complete tool details for debugging
                logger.info(f"\n{'='*80}")
                logger.info(f"AGENT: {agent_config['name']}")
                logger.info(f"QUERY: {agent_config['query']}")
                logger.info(f"RETRIEVED {len(tools_mcp)} TOOLS:")
                logger.info(f"{'='*80}")
                for idx, tool_schema in enumerate(tools_mcp, 1):
                    logger.info(f"\n[Tool {idx}] {tool_schema.name}")
                    logger.info(f"  ID: {tool_schema.id}")
                    logger.info(f"  Score: {tool_scores.get(tool_schema.id, 0.0):.4f}")
                    logger.info(f"  Server: {tool_schema.server_name}")
                    logger.info(f"  Description: {tool_schema.description}")
                    logger.info(f"  Parameters: {json.dumps(tool_schema.parameters, indent=4)}")
                    logger.info(f"  Input Schema: {json.dumps(tool_schema.raw_schema.get('inputSchema', {}), indent=4)}")
                    logger.info(f"  Output Format: {tool_schema.raw_schema.get('outputFormat', 'Tool execution result')}")
                logger.info(f"{'='*80}\n")
                
                # Emit tool retrieval with complete metadata
                yield AgentEvent(
                    type=EventType.TOOL_RETRIEVAL,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_config["name"],
                        "query": agent_config["query"],
                        "tools": [
                            {
                                "id": t.id,
                                "name": t.name,
                                "description": t.description,
                                "score": tool_scores.get(t.id, 0.0),
                                "server_name": t.server_name,
                                "parameters": t.parameters,
                                "input_schema": t.raw_schema.get("inputSchema", {}),
                                "output_format": t.raw_schema.get("outputFormat", "Tool execution result")
                            } for t in tools_mcp
                        ]
                    }
                )
                
                # Convert MCP tools to LangChain tools
                tools = [
                    LangChainToolAdapter.convert_mcp_to_langchain_tool(t, self.router.mcp_client)
                    for t in tools_mcp
                ]
                
                # Execute tools and capture results
                tool_results = []
                for idx, (tool, tool_mcp) in enumerate(zip(tools, tools_mcp)):
                    self.tools_executed += 1
                    tool_start = time.time()
                    
                    try:
                        # Generate realistic arguments based on tool name
                        tool_args = self._generate_tool_args(tool_mcp.name, user_query)
                        
                        # Execute tool
                        result = await tool.ainvoke(tool_args)
                        parsed_result = self._parse_tool_result(result)
                        
                        tool_time = time.time() - tool_start
                        
                        # Store tool result for LLM context
                        tool_results.append({
                            "tool_name": tool_mcp.name,
                            "args": tool_args,
                            "result": parsed_result
                        })
                        
                        # Emit tool execution
                        yield AgentEvent(
                            type=EventType.TOOL_EXECUTION,
                            timestamp=time.time(),
                            data={
                                "agent_name": agent_config["name"],
                                "tool_name": tool_mcp.name,
                                "tool_args": tool_args,
                                "result": parsed_result,
                                "execution_time": tool_time,
                                "success": True
                            }
                        )
                        
                    except Exception as e:
                        logger.error(f"Tool execution failed: {e}")
                        error_result = {"error": str(e)}
                        tool_results.append({
                            "tool_name": tool_mcp.name,
                            "args": tool_args,
                            "result": error_result
                        })
                        yield AgentEvent(
                            type=EventType.TOOL_EXECUTION,
                            timestamp=time.time(),
                            data={
                                "agent_name": agent_config["name"],
                                "tool_name": tool_mcp.name,
                                "tool_args": tool_args,
                                "result": error_result,
                                "execution_time": time.time() - tool_start,
                                "success": False
                            }
                        )
                
                # Build LLM prompt with context
                llm_input = self._build_agent_prompt(
                    agent_config=agent_config,
                    user_query=user_query,
                    tool_results=tool_results,
                    previous_context=agent_context["previous_results"]
                )
                
                # Call LLM with streaming to generate agent response
                try:
                    agent_output = ""
                    
                    # Stream LLM response
                    async for chunk in llm.astream(llm_input):
                        chunk_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                        if chunk_content:
                            agent_output += chunk_content
                            
                            # Emit streaming chunk
                            yield AgentEvent(
                                type=EventType.AGENT_RESPONSE_CHUNK,
                                timestamp=time.time(),
                                data={
                                    "agent_name": agent_config["name"],
                                    "chunk": chunk_content,
                                    "accumulated": agent_output
                                }
                            )
                    
                    # Store result for next agent
                    agent_context["previous_results"].append({
                        "agent_name": agent_config["name"],
                        "input": llm_input,
                        "output": agent_output,
                        "tool_results": tool_results
                    })
                    
                except Exception as e:
                    logger.error(f"LLM call failed: {e}")
                    agent_output = f"Error generating response: {str(e)}"
                
                # Emit final agent response with complete LLM output
                agent_time = time.time() - start_time
                yield AgentEvent(
                    type=EventType.AGENT_RESPONSE,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_config["name"],
                        "input": llm_input,
                        "response": agent_output,
                        "tool_results": tool_results,
                        "execution_time": agent_time
                    }
                )
                
        except Exception as e:
            logger.error(f"LangGraph execution error: {e}")
            yield AgentEvent(
                type=EventType.ERROR,
                timestamp=time.time(),
                data={
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
    
    async def cleanup(self):
        """Cleanup LangGraph resources"""
        try:
            if self.router:
                await self.router.close()
                self.router = None
            
            await self._stop_mcp_server()
            
            self.initialized = False
            logger.info("✓ LangGraph executor cleaned up")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
    
    def _generate_tool_args(self, tool_name: str, user_query: str) -> Dict[str, Any]:
        """Generate realistic tool arguments based on tool name and query"""
        # Updated to match actual MCP tool schemas from UHNW Banking Server
        args_map = {
            # Portfolio Manager tools
            "get_portfolio_summary": {"client_id": "UHNW-123"},
            "get_unrealized_gains_losses": {"client_id": "UHNW-123"},
            "get_asset_allocation": {"client_id": "UHNW-123"},
            
            # Trading Analyst tools
            "get_market_data": {"symbols": ["NVDA", "SPY", "QQQ"]},
            "get_market_news": {"sector_or_ticker": "NVDA"},
            "execute_trade": {
                "client_id": "UHNW-123",
                "ticker": "NVDA",
                "quantity": "100",
                "action": "SELL"
            },
            
            # Tax & Compliance tools
            "simulate_capital_gains_tax": {
                "client_id": "UHNW-123",
                "ticker": "NVDA",
                "quantity_to_sell": 100
            },
            "get_tax_loss_harvesting_options": {"client_id": "UHNW-123"},
            "run_aml_transaction_check": {
                "client_id": "UHNW-123",
                "amount": 450000,
                "destination": "External Investment Fund"
            },
            
            # Additional tools (if present)
            "update_card_limit": {
                "client_id": "UHNW-123",
                "card_id": "CARD-001",
                "new_limit": 100000
            },
            "initiate_wire_transfer": {
                "client_id": "UHNW-123",
                "amount": 50000,
                "recipient": "External Account"
            }
        }
        
        return args_map.get(tool_name, {})
    
    def _parse_tool_result(self, result: Any) -> Dict[str, Any]:
        """Parse tool result into a dictionary"""
        if isinstance(result, str):
            try:
                # Try to parse as JSON
                return json.loads(result)
            except:
                # Return as text
                return {"result": result}
        elif isinstance(result, dict):
            return result
        else:
            return {"result": str(result)}
    
    def _build_agent_prompt(
        self,
        agent_config: Dict[str, Any],
        user_query: str,
        tool_results: List[Dict[str, Any]],
        previous_context: List[Dict[str, Any]]
    ) -> str:
        """Build LLM prompt for agent with context"""
        
        # Build context from previous agents
        context_str = ""
        if previous_context:
            context_str = "\n\n## Previous Agent Results:\n"
            for prev in previous_context:
                context_str += f"\n### {prev['agent_name']}:\n"
                context_str += f"{prev['output']}\n"
        
        # Build tool results section
        tools_str = "\n\n## Tool Execution Results:\n"
        for tr in tool_results:
            tools_str += f"\n### {tr['tool_name']}:\n"
            tools_str += f"Arguments: {json.dumps(tr['args'], indent=2)}\n"
            tools_str += f"Result: {json.dumps(tr['result'], indent=2)}\n"
        
        # Build complete prompt
        prompt = f"""You are a {agent_config['role']} named {agent_config['name']}.

## User Query:
{user_query}
{context_str}
{tools_str}

## Your Task:
Based on the tool execution results above{' and previous agent analysis' if previous_context else ''}, provide a comprehensive analysis and recommendations for the user's query.

Focus on:
1. Key insights from the tool results
2. Actionable recommendations
3. Any risks or considerations
4. Next steps if applicable

Provide your response in a clear, professional manner."""

        return prompt

# Made with Bob
