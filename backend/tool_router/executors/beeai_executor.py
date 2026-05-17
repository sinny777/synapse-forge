"""
BeeAI executor for real agent execution with SynapseForge.
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
    
    Uses IBM BeeAI's RequirementAgent and integrates with SynapseForge
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
            model_name = "gpt-4o"
            heavy_config_id = None
            if llm_config:
                model_name = llm_config.get("model") or llm_config.get("heavy_model") or "gpt-4o"
                heavy_config_id = llm_config.get("heavy_config_id")
                
            provider = None
            if "/" in model_name:
                parts = model_name.split("/", 1)
                provider = parts[0].lower()
                model_name = parts[1]
            elif model_name.startswith("openai:") or model_name.startswith("ollama:"):
                parts = model_name.split(":", 1)
                provider = parts[0].lower()
                model_name = parts[1]

            import os
            db_provider = None
            db_credentials = None

            if heavy_config_id:
                try:
                    from db.engine import _session_factory
                    from db.models import LLMConfig
                    import uuid
                    config_uuid = uuid.UUID(str(heavy_config_id))
                    
                    async with _session_factory() as session:
                        config_row = await session.get(LLMConfig, config_uuid)
                        if config_row:
                            db_provider = config_row.provider.value
                            db_credentials = config_row.credentials
                            logger.info(f"Loaded credentials from database for LLMConfig '{config_row.name}' (provider: {db_provider})")
                except Exception as db_err:
                    logger.error(f"Error loading LLMConfig by ID {heavy_config_id}: {db_err}")

            if db_provider and db_credentials:
                provider = db_provider
                # Inject credentials into env vars
                if provider == "ibm_watsonx":
                    api_key = db_credentials.get("api_key") or db_credentials.get("apikey")
                    project_id = db_credentials.get("project_id")
                    region = db_credentials.get("region", "us-south")
                    
                    if api_key:
                        os.environ["WATSONX_APIKEY"] = api_key
                        os.environ["WATSONX_API_KEY"] = api_key
                    if project_id:
                        os.environ["WATSONX_PROJECT_ID"] = project_id
                    if region:
                        if region.startswith("http"):
                            os.environ["WATSONX_URL"] = region
                        else:
                            os.environ["WATSONX_URL"] = f"https://{region}.ml.cloud.ibm.com"
                        os.environ["WATSONX_REGION"] = region
                        
                elif provider == "openai":
                    api_key = db_credentials.get("api_key") or db_credentials.get("apikey")
                    api_base = db_credentials.get("api_base") or db_credentials.get("url")
                    if api_key:
                        os.environ["OPENAI_API_KEY"] = api_key
                    if api_base:
                        os.environ["OPENAI_API_BASE"] = api_base
                        
                elif provider == "ollama":
                    api_base = db_credentials.get("api_base") or db_credentials.get("url")
                    if api_base:
                        os.environ["OLLAMA_API_BASE"] = api_base

            # Map ibm_watsonx provider name to watsonx
            if provider == "ibm_watsonx":
                provider = "watsonx"

            is_watsonx = (provider == "watsonx")
            
            # Fallback check
            if not is_watsonx and not os.getenv("OPENAI_API_KEY") and provider != "openai":
                # If OpenAI key is missing and they didn't explicitly select OpenAI, fallback to Ollama
                local_model = os.getenv("DEFAULT_AGENT_MODEL", "granite4.1:8b")
                if "/" in local_model:
                    local_model = local_model.split("/", 1)[1]
                
                # If they tried to use a commercial model but have no key, fallback to local granite
                selected_model = local_model if (provider == "openai" or "gpt" in model_name or "claude" in model_name) else model_name
                llm_model = f"ollama:{selected_model}"
                logger.info(f"OPENAI_API_KEY not found. Using local Ollama model in BeeAI: {llm_model}")
            elif is_watsonx:
                llm_model = f"watsonx:{model_name}"
            else:
                # If we explicitly want ollama
                if provider == "ollama":
                    llm_model = f"ollama:{model_name}"
                else:
                    llm_model = f"openai:{model_name}"
            
            logger.info(f"Instantiating BeeAI ChatModel with: {llm_model}")
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
                
                logger.info(f"Agent '{agent_config['name']}' is executing using LLM model: {llm_model}")
                
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
                
                # Retrieve tools using SynapseForge with scores
                tool_results = self.router.semantic_router.retrieve_tools(agent_config["tool_query"], top_k=2, use_hybrid=True)
                tools_mcp = []
                tool_scores = {}
                for tool_id, score in tool_results:
                    # Try exact match first
                    tool_schema = self.router.all_tools.get(tool_id)
                    
                    # If not found, try flexible matching by extracting the tool name (part after the dot)
                    if not tool_schema:
                        tool_name = tool_id.split(".")[-1]
                        # Look for a key in self.router.all_tools that ends with "." + tool_name or equals tool_name
                        for key, schema in self.router.all_tools.items():
                            if key.split(".")[-1] == tool_name or schema.name == tool_name:
                                tool_schema = schema
                                break
                                
                    if tool_schema:
                        tools_mcp.append(tool_schema)
                        tool_scores[tool_schema.id] = score
                
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
