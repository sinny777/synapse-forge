"""
BeeAI executor for real agent execution with NeuralToolRouter.
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


def _extract_text_from_beeai_message(message: Any) -> str:
    """Extract readable text from BeeAI message/content objects."""
    if message is None:
        return ""

    if isinstance(message, str):
        return message

    if isinstance(message, list):
        parts = [_extract_text_from_beeai_message(item) for item in message]
        return "\n\n".join(part for part in parts if part)

    for attr in ("text", "content", "message", "result", "output", "response"):
        if hasattr(message, attr):
            value = getattr(message, attr)
            extracted = _extract_text_from_beeai_message(value)
            if extracted:
                return extracted

    if isinstance(message, dict):
        parts = [_extract_text_from_beeai_message(value) for value in message.values()]
        return "\n\n".join(part for part in parts if part) or json.dumps(message, indent=2, default=str)

    try:
        return json.dumps(message, indent=2, default=str)
    except Exception:
        return str(message)


class BeeAIExecutor(BaseAgentExecutor):
    """
    BeeAI executor that implements real agent execution.
    
    Uses IBM BeeAI's RequirementAgent and integrates with NeuralToolRouter
    for dynamic tool selection.
    """
    
    def __init__(self, scenario: AgentScenario, examples_dir: Path, model_path: str = None):
        """Initialize BeeAI executor"""
        super().__init__(scenario, examples_dir)
        self.router = None
        self.tools_retrieved = 0
        self.tools_executed = 0
        self.agents_executed = 0
        self.model_path = model_path
        
        # Map scenario IDs to example directories (must match mcp_manager.py)
        scenario_map = {
            "mediclaim_processing": "beeai_mediclaim_processing",
        }
        
        # Get the correct example directory for this scenario
        example_dir_name = scenario_map.get(scenario.id, "beeai_mediclaim_processing")
        self.example_dir = examples_dir / example_dir_name
        
        # Add example directory to path for imports
        if str(self.example_dir) not in sys.path:
            sys.path.insert(0, str(self.example_dir))
    
    async def initialize(self):
        """Initialize BeeAI components and start MCP server"""
        try:
            logger.info("Initializing BeeAI executor...")
            
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
            if spec and spec.loader:
                orchestrator_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(orchestrator_module)
                ToolRouterForBeeAI = orchestrator_module.ToolRouterForBeeAI
            else:
                raise RuntimeError(f"Could not load module from {module_path}")
            
            self.router = ToolRouterForBeeAI(model_path=self.model_path)
            await self.router.initialize()
            
            self.initialized = True
            logger.info("✓ BeeAI executor initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize BeeAI executor: {e}")
            raise
    
    async def execute(
        self,
        user_query: str,
        llm_config: Optional[Dict[str, Any]] = None,
        runtime_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Execute BeeAI scenario with real tool execution.
        
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
            # Import BeeAI components
            from beeai_framework.backend import ChatModel
            from beeai_framework.agents.requirement import RequirementAgent
            from beeai_framework.memory import TokenMemory
            
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
                BeeAIToolAdapter = orchestrator_module.BeeAIToolAdapter
            else:
                raise RuntimeError(f"Could not load module from {module_path}")
            
            # Get LLM model
            model_name = llm_config.get("model", "gpt-4o") if llm_config else "gpt-4o"
            llm_model = f"openai:{model_name}" if not model_name.startswith("openai:") else model_name
            llm = ChatModel.from_name(llm_model)
            
            # Define agents with their queries for tool retrieval
            agents_config = [
                {
                    "name": "Policy Agent",
                    "role": "Insurance Policy Specialist",
                    "query": "Fetch insurance policy details for POL-999 and check coverage limits for knee replacement surgery",
                    "tool_query": "Fetch policy details and check coverage"
                },
                {
                    "name": "Billing Agent",
                    "role": "Medical Billing Analyst",
                    "query": "Fetch hospital discharge summary for patient 1024 and verify the hospital bills",
                    "tool_query": "Get discharge summary and verify bills"
                },
                {
                    "name": "Claim Processing Agent",
                    "role": "Claims Processor",
                    "query": "Calculate the final claimable amount and submit the mediclaim for patient 1024 with policy POL-999",
                    "tool_query": "Calculate and submit claim"
                }
            ]
            
            # Context accumulation for sequential agents
            context = []
            
            # Execute each agent sequentially
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
                
                # Retrieve tools using NeuralToolRouter with scores
                tool_results = self.router.semantic_router.retrieve_tools(agent_config["tool_query"], top_k=2, use_hybrid=True)
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
                logger.info(f"QUERY: {agent_config['tool_query']}")
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
                        "query": agent_config["tool_query"],
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

                # Expose the effective agent prompt like LangGraph
                enriched_query = agent_config["query"]
                if context:
                    enriched_query = f"{agent_config['query']}\n\nContext from previous agents:\n" + "\n".join(context)

                yield AgentEvent(
                    type=EventType.AGENT_REASONING,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_config["name"],
                        "reasoning": f"Preparing BeeAI RequirementAgent with {len(tools_mcp)} retrieved tools and prior agent context."
                    }
                )

                # Emit a prompt preview so UI can show Agent Input during execution
                yield AgentEvent(
                    type=EventType.AGENT_RESPONSE_CHUNK,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_config["name"],
                        "chunk": "",
                        "accumulated": "",
                        "status_label": "Reasoning",
                        "input": enriched_query
                    }
                )
                
                # Convert MCP tools to BeeAI tools
                beeai_tools = []
                for tool_mcp in tools_mcp:
                    tool_func = BeeAIToolAdapter.convert_mcp_to_beeai_tool(
                        tool_mcp,
                        self.router.mcp_client
                    )
                    beeai_tools.append(tool_func)
                
                # Create BeeAI agent
                memory = TokenMemory()
                agent = RequirementAgent(
                    llm=llm,
                    memory=memory,
                    tools=beeai_tools
                )
                
                # Execute retrieved tools to surface real tool outputs and statuses in the UI
                tool_execution_summaries = []
                for tool_mcp in tools_mcp:
                    tool_args = self._generate_tool_args(tool_mcp.name, agent_config["name"])

                    yield AgentEvent(
                        type=EventType.AGENT_REASONING,
                        timestamp=time.time(),
                        data={
                            "agent_name": agent_config["name"],
                            "reasoning": f"Executing tool {tool_mcp.name} with generated arguments."
                        }
                    )

                    tool_start = time.time()
                    tool_result = await self.router.mcp_client.call_tool(tool_mcp.id, tool_args)
                    tool_time = time.time() - tool_start
                    self.tools_executed += 1

                    tool_success = tool_result.get("success", False)
                    tool_result_text = _extract_text_from_beeai_message(tool_result)

                    tool_execution_summaries.append(
                        f"Tool: {tool_mcp.name}\nArguments: {json.dumps(tool_args, indent=2)}\nResult: {tool_result_text}"
                    )
                    
                    yield AgentEvent(
                        type=EventType.TOOL_EXECUTION,
                        timestamp=time.time(),
                        data={
                            "agent_name": agent_config["name"],
                            "tool_name": tool_mcp.name,
                            "tool_args": tool_args,
                            "result": tool_result,
                            "execution_time": tool_time,
                            "success": tool_success
                        }
                    )
                
                # Run agent after tool results are available for richer final response
                agent_start = time.time()
                response_obj = await agent.run(enriched_query)
                response = _extract_text_from_beeai_message(response_obj)
                agent_time = time.time() - agent_start

                # Simulate streaming for BeeAI final response so UI matches LangGraph experience
                accumulated_response = ""
                for paragraph in [part.strip() for part in response.split("\n\n") if part.strip()]:
                    accumulated_response = f"{accumulated_response}\n\n{paragraph}".strip() if accumulated_response else paragraph
                    yield AgentEvent(
                        type=EventType.AGENT_RESPONSE_CHUNK,
                        timestamp=time.time(),
                        data={
                            "agent_name": agent_config["name"],
                            "chunk": f"{paragraph}\n\n",
                            "accumulated": accumulated_response,
                            "status_label": "Output",
                            "input": enriched_query
                        }
                    )
                
                # Add response to context for next agent
                context.append(f"{agent_config['name']}: {response}")
                
                # Emit final agent response
                yield AgentEvent(
                    type=EventType.AGENT_RESPONSE,
                    timestamp=time.time(),
                    data={
                        "agent_name": agent_config["name"],
                        "input": enriched_query,
                        "response": response,
                        "execution_time": agent_time,
                        "tool_execution_summary": tool_execution_summaries
                    }
                )
                
        except Exception as e:
            logger.error(f"BeeAI execution error: {e}")
            yield AgentEvent(
                type=EventType.ERROR,
                timestamp=time.time(),
                data={
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
    
    async def cleanup(self):
        """Cleanup BeeAI resources"""
        try:
            if self.router:
                try:
                    await self.router.close()
                except Exception as e:
                    logger.warning(f"Error closing router: {e}")
                finally:
                    self.router = None
            
            try:
                await self._stop_mcp_server()
            except Exception as e:
                logger.warning(f"Error stopping MCP server: {e}")
            
            self.initialized = False
            logger.info("✓ BeeAI executor cleaned up")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
    
    def _generate_tool_args(self, tool_name: str, agent_name: str) -> Dict[str, Any]:
        """Generate valid tool arguments based on the Mediclaim MCP tool schemas."""
        args_map = {
            "get_policy_details": {"policy_number": "POL-999"},
            "check_coverage_limits": {
                "policy_number": "POL-999",
                "treatment_type": "knee_replacement"
            },
            "fetch_discharge_summary": {"patient_id": "1024"},
            "verify_hospital_bills": {"patient_id": "1024"},
            "calculate_claimable_amount": {
                "total_bill_amount": 285000.0,
                "coverage_limit": 300000.0,
                "co_pay_percentage": 10.0
            },
            "submit_mediclaim": {
                "policy_number": "POL-999",
                "patient_id": "1024",
                "claim_amount": 256500.0
            }
        }
        
        return args_map.get(tool_name, {})

# Made with Bob
