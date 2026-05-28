"""
LangGraph-based Agent Executor Service for SynapseForge

Simplified implementation that uses LangGraph ReAct pattern with
proper event streaming for frontend compatibility.
"""

import json
import logging
import os
import time
import uuid
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import Agent, Tool, LLMConfig
from services.router_service import RouterService

logger = logging.getLogger("ntr.services.langgraph_agent_executor")


def _sse_event(
    event_type: str,
    label: str,
    detail: str = "",
    *,
    status_value: str = "success",
    latency_ms: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Format SSE event for streaming"""
    from datetime import datetime, timezone
    payload: dict[str, Any] = {
        "type": event_type,
        "label": label,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status_value,
    }
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    if metadata:
        payload["metadata"] = metadata
        payload["data"] = metadata
    return f"data: {json.dumps(payload)}\n\n"


def _safe_json(value: Any) -> str:
    """Safely convert value to JSON string"""
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


class LangGraphAgentExecutor:
    """
    Simplified LangGraph-based agent executor with proper event streaming.
    Uses LangGraph for tool binding but emits custom events for frontend.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute_agent(
        self,
        agent: Agent,
        user_prompt: str,
        depth: int = 0,
    ) -> AsyncGenerator[str, None]:
        """
        Execute agent with LangGraph ReAct pattern and proper event streaming.
        """
        try:
            # Load agent dependencies
            llm_config = await self._load_llm_config(agent)
            if not llm_config:
                yield _sse_event(
                    "error",
                    "Missing LLM Configuration",
                    "Agent must have an LLM configuration assigned",
                    status_value="error",
                    metadata={"agent_id": str(agent.id), "agent_name": agent.name},
                )
                return

            tools = await self._load_agent_tools(agent)
            collaborators = await self._load_collaborator_agents(agent)

            # Apply LLM credentials
            self._apply_llm_credentials(llm_config)

            # Emit initialization event
            yield _sse_event(
                "reasoning",
                f"Initializing Agent: {agent.name}",
                f"Setting up agent with {len(tools)} tools and {len(collaborators)} collaborators",
                status_value="running",
                metadata={
                    "depth": depth,
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "tool_count": len(tools),
                    "collaborator_count": len(collaborators),
                },
            )

            # Select tools using NeuralToolRouter
            selected_tools, router_metadata = await self._select_tools_for_prompt(
                agent, tools, user_prompt
            )

            if router_metadata:
                strategy = router_metadata.get("strategy", "attached_tools")
                label = "Neural Tool Router Selection" if strategy == "neural_router" else "Attached Tool Selection"
                
                # Format detail as JSON for router events (frontend expects structured data for router)
                detail = _safe_json(
                    {
                        "selected_tools": [
                            {"id": str(tool.id), "name": tool.name, "type": tool.type.value}
                            for tool in selected_tools
                        ],
                        "router": router_metadata,
                    }
                )
                
                yield _sse_event(
                    "router",
                    label,
                    detail,
                    status_value="success",
                    latency_ms=router_metadata.get("latency_ms"),
                    metadata={
                        **router_metadata,
                        "depth": depth,
                        "agent_id": str(agent.id),
                        "selected_tools": [
                            {"id": str(tool.id), "name": tool.name, "type": tool.type.value}
                            for tool in selected_tools
                        ],
                    },
                )

            # Execute using LangGraph ReAct
            async for event in self._execute_with_langgraph(
                agent=agent,
                llm_config=llm_config,
                tools=selected_tools,
                collaborators=collaborators,
                user_prompt=user_prompt,
                depth=depth,
            ):
                yield event

        except Exception as exc:
            logger.exception(f"Agent execution failed for {agent.id}")
            yield _sse_event(
                "error",
                "Agent Execution Failed",
                str(exc),
                status_value="error",
                metadata={
                    "error_type": type(exc).__name__,
                    "agent_id": str(agent.id),
                    "depth": depth,
                },
            )

    async def _execute_with_langgraph(
        self,
        agent: Agent,
        llm_config: LLMConfig,
        tools: list[Tool],
        collaborators: list[Agent],
        user_prompt: str,
        depth: int,
    ) -> AsyncGenerator[str, None]:
        """Execute agent using LangGraph with custom event streaming"""
        try:
            from langgraph.prebuilt import create_react_agent
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
            from tool_router.executors.langgraph_executor import LiteLLMChatOpenAI

            # Get LLM model
            provider, model_name = self._resolve_provider_model(llm_config)
            if not provider or not model_name:
                raise ValueError("Invalid LLM configuration")

            if provider == "ibm_watsonx":
                provider = "watsonx"

            litellm_model = f"{provider}/{model_name}"
            logger.info(f"Creating LangGraph agent with model: {litellm_model}")

            llm = LiteLLMChatOpenAI(
                model="gpt-4o",
                litellm_model=litellm_model,
                openai_api_key="litellm-dummy-key",
                temperature=llm_config.temperature or 0.7,
                max_tokens=llm_config.max_tokens,
            )

            # Convert tools to LangChain format
            langchain_tools = await self._convert_tools_to_langchain(tools)

            # Add collaborator tools
            for collab in collaborators:
                collab_tool = self._create_collaborator_tool(collab, depth)
                langchain_tools.append(collab_tool)

            # Create ReAct agent
            react_agent = create_react_agent(llm, langchain_tools)

            # Prepare messages
            system_message = agent.system_prompt or "You are a helpful AI assistant."
            messages = [
                SystemMessage(content=system_message),
                HumanMessage(content=user_prompt)
            ]

            # Emit LLM call start
            start_time = time.perf_counter()
            yield _sse_event(
                "thought",
                "Agent Thinking",
                f"Analyzing the request and planning actions...",
                status_value="running",
                metadata={
                    "depth": depth,
                    "agent_id": str(agent.id),
                    "model": litellm_model,
                },
            )

            # Execute agent and collect results
            config = {"recursion_limit": agent.max_iterations or 10}
            inputs = {"messages": messages}
            
            final_response = ""
            tool_calls_made = []
            iteration = 0
            
            # Stream execution
            async for event in react_agent.astream(inputs, config=config):
                for node_name, node_output in event.items():
                    if node_name == "agent":
                        messages_list = node_output.get("messages", [])
                        if messages_list:
                            last_message = messages_list[-1]
                            
                            # Check for tool calls
                            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                                for tool_call in last_message.tool_calls:
                                    tool_calls_made.append(tool_call)
                                    tool_name = tool_call.get("name", "unknown")
                                    tool_args = tool_call.get("args", {})
                                    
                                    # Emit tool call event with JSON detail (for structured display)
                                    detail = _safe_json({
                                        "tool_name": tool_name,
                                        "arguments": tool_args,
                                    })
                                    
                                    yield _sse_event(
                                        "tool_call",
                                        f"Calling {tool_name}",
                                        detail,
                                        status_value="running",
                                        metadata={
                                            "depth": depth,
                                            "agent_id": str(agent.id),
                                            "tool_name": tool_name,
                                            "tool_args": tool_args,
                                        },
                                    )
                            
                            # Check for reasoning content
                            if hasattr(last_message, "content") and last_message.content:
                                content = last_message.content
                                if isinstance(content, str) and content.strip() and not tool_calls_made:
                                    # Plain text for reasoning - no metadata to avoid structured display
                                    yield _sse_event(
                                        "reasoning",
                                        "Agent Reasoning",
                                        content,
                                        status_value="success",
                                    )
                                    iteration += 1
                    
                    elif node_name == "tools":
                        messages_list = node_output.get("messages", [])
                        for msg in messages_list:
                            if hasattr(msg, "content"):
                                content_str = str(msg.content)
                                tool_name = getattr(msg, "name", "unknown")
                                
                                # Emit tool result - plain text for readability
                                yield _sse_event(
                                    "tool_result",
                                    f"{tool_name} Result",
                                    content_str,
                                    status_value="success",
                                )
                
                # Check for final answer
                if "__end__" in event:
                    end_messages = event["__end__"].get("messages", [])
                    if end_messages:
                        final_message = end_messages[-1]
                        if isinstance(final_message, AIMessage) and final_message.content:
                            final_response = final_message.content

            execution_time = (time.perf_counter() - start_time) * 1000

            # Emit final response
            if not final_response:
                final_response = "Agent completed execution"
            
            # Ensure final_response is a string
            response_text = str(final_response) if final_response else "Agent completed execution"
            
            # Plain text response - no metadata to keep it clean
            yield _sse_event(
                "assistant",
                f"{agent.name} Response",
                response_text,
                status_value="success",
                latency_ms=execution_time,
            )

        except ImportError as e:
            logger.error(f"LangGraph import error: {e}")
            yield _sse_event(
                "error",
                "LangGraph Not Available",
                f"Please install langgraph and langchain packages: {str(e)}",
                status_value="error",
            )
        except Exception as e:
            logger.exception(f"LangGraph execution error: {e}")
            yield _sse_event(
                "error",
                "LangGraph Execution Error",
                str(e),
                status_value="error",
                metadata={"error_type": type(e).__name__},
            )

    async def _select_tools_for_prompt(
        self,
        agent: Agent,
        available_tools: list[Tool],
        prompt: str,
    ) -> tuple[list[Tool], dict | None]:
        """Select tools using NeuralToolRouter or return all attached tools"""
        if not available_tools:
            return [], None

        executable_tools = [
            tool for tool in available_tools
            if tool.type.value in {"MCP_TOOL", "REST"}
        ]
        fallback_tools = executable_tools or available_tools

        if not agent.use_neural_router:
            return fallback_tools, {
                "strategy": "attached_tools",
                "selected_tool_ids": [str(tool.id) for tool in fallback_tools],
            }

        # Use NeuralToolRouter
        top_k = agent.router_top_k or min(5, len(fallback_tools))
        start_time = time.perf_counter()
        
        router_result = await RouterService.predict(
            session=self.session,
            workspace_id=agent.workspace_id,
            user_prompt=prompt,
            top_k=max(top_k, len(fallback_tools)),
            redis=None,
        )
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        ranked = router_result.get("tools", [])
        allowed = {str(tool.id): tool for tool in fallback_tools}

        selected: list[Tool] = []
        seen_ids: set[str] = set()

        for ranked_tool in ranked:
            ranked_id = ranked_tool.get("id")
            if ranked_id and ranked_id in allowed:
                tool = allowed[ranked_id]
                if str(tool.id) not in seen_ids:
                    selected.append(tool)
                    seen_ids.add(str(tool.id))
            
            if len(selected) >= top_k:
                break

        if not selected:
            selected = fallback_tools[:top_k]

        return selected, {
            "strategy": "neural_router",
            "router_top_k": top_k,
            "selected_tool_ids": [str(tool.id) for tool in selected],
            "ranked_tools": ranked[:10],
            "cached": router_result.get("cached", False),
            "latency_ms": latency_ms,
        }

    async def _convert_tools_to_langchain(self, tools: list[Tool]) -> list:
        """Convert SynapseForge tools to LangChain tool format"""
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field, create_model
        
        langchain_tools = []
        
        for tool in tools:
            try:
                schema = tool.schema_def or {}
                if isinstance(schema.get("inputSchema"), dict):
                    input_schema = schema["inputSchema"]
                else:
                    input_schema = schema
                
                properties = input_schema.get("properties", {})
                required = input_schema.get("required", [])
                
                # Create Pydantic model for tool inputs
                fields = {}
                for prop_name, prop_schema in properties.items():
                    prop_type = prop_schema.get("type", "string")
                    prop_desc = prop_schema.get("description", "")
                    is_required = prop_name in required
                    
                    if prop_type == "string":
                        py_type = str
                    elif prop_type == "integer":
                        py_type = int
                    elif prop_type == "number":
                        py_type = float
                    elif prop_type == "boolean":
                        py_type = bool
                    else:
                        py_type = str
                    
                    if is_required:
                        fields[prop_name] = (py_type, Field(description=prop_desc))
                    else:
                        fields[prop_name] = (py_type | None, Field(default=None, description=prop_desc))
                
                if fields:
                    InputModel = create_model(f"{tool.name}Input", **fields)
                else:
                    InputModel = None
                
                # Create tool execution function
                async def tool_func(**kwargs):
                    return await self._execute_tool(tool, kwargs)
                
                lc_tool = StructuredTool.from_function(
                    func=tool_func,
                    name=tool.name,
                    description=tool.description or f"Execute {tool.name}",
                    args_schema=InputModel,
                    coroutine=tool_func,
                )
                
                langchain_tools.append(lc_tool)
                
            except Exception as e:
                logger.warning(f"Failed to convert tool {tool.name}: {e}")
                continue
        
        return langchain_tools

    async def _execute_tool(self, tool: Tool, args: dict) -> str:
        """Execute a single tool and return result"""
        try:
            if tool.type.value == "MCP_TOOL":
                return await self._execute_mcp_tool(tool, args)
            elif tool.type.value == "REST":
                return await self._execute_rest_tool(tool, args)
            else:
                return f"Unsupported tool type: {tool.type.value}"
        except Exception as e:
            logger.error(f"Tool execution failed for {tool.name}: {e}")
            return f"Tool execution failed: {str(e)}"

    async def _execute_mcp_tool(self, tool: Tool, args: dict) -> str:
        """Execute MCP tool"""
        try:
            from tool_router.mcp_client import MCPClient
            from tool_router.config import MCPConfig
            
            if not tool.parent_id:
                return "MCP tool has no parent server"
            
            parent_server = await self.session.get(Tool, tool.parent_id)
            if not parent_server or parent_server.type.value != "MCP_SERVER":
                return "Parent MCP server not found"
            
            if not parent_server.transport:
                return "MCP server transport not configured"
            
            server_id = str(parent_server.id)
            server_cfg: dict[str, Any] = {"transport": parent_server.transport.value}
            
            if parent_server.transport.value == "stdio":
                server_cfg["command"] = parent_server.command
                server_cfg["args"] = parent_server.args or []
                server_cfg["env"] = parent_server.env or {}
            elif parent_server.url:
                server_cfg["url"] = parent_server.url
            
            client = MCPClient(MCPConfig(servers={server_id: server_cfg}))
            await client.connect_all()
            
            tool_id = f"{server_id}.{tool.name}"
            result = await client.call_tool(tool_id, args)
            
            await client.close_all()
            
            if result.get("success"):
                content = result.get("content", [])
                if isinstance(content, list):
                    return "\n".join(
                        item.get("text", str(item))
                        for item in content
                        if isinstance(item, dict)
                    )
                return str(content)
            else:
                return result.get("error", "Tool execution failed")
                
        except Exception as e:
            logger.error(f"MCP tool execution error: {e}")
            return f"MCP tool error: {str(e)}"

    async def _execute_rest_tool(self, tool: Tool, args: dict) -> str:
        """Execute REST tool"""
        try:
            import httpx
            
            connection = tool.connection_config or {}
            method = str(connection.get("method", "POST")).upper()
            url = connection.get("url") or tool.url
            headers = connection.get("headers", {})
            timeout = float(connection.get("timeout_seconds", 60))
            
            if not url:
                return "REST tool URL not configured"
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    response = await client.get(url, params=args, headers=headers)
                else:
                    response = await client.request(method, url, json=args, headers=headers)
            
            if response.is_success:
                try:
                    return json.dumps(response.json(), indent=2)
                except:
                    return response.text
            else:
                return f"HTTP {response.status_code}: {response.text}"
                
        except Exception as e:
            logger.error(f"REST tool execution error: {e}")
            return f"REST tool error: {str(e)}"

    def _create_collaborator_tool(self, collaborator: Agent, parent_depth: int):
        """Create a LangChain tool for delegating to a collaborator agent"""
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field
        
        class CollaboratorInput(BaseModel):
            task: str = Field(description="The specific task or question to delegate to the collaborator")
        
        async def delegate_to_collaborator(task: str) -> str:
            """Delegate a task to a collaborator agent"""
            result_text = ""
            async for event in self.execute_agent(
                agent=collaborator,
                user_prompt=task,
                depth=parent_depth + 1,
            ):
                try:
                    event_data = json.loads(event.removeprefix("data: ").strip())
                    if event_data.get("type") == "assistant":
                        result_text = event_data.get("detail", "")
                except:
                    pass
            
            return result_text or f"Collaborator {collaborator.name} completed the task"
        
        return StructuredTool.from_function(
            func=delegate_to_collaborator,
            name=f"delegate_to_{collaborator.name.lower().replace(' ', '_')}",
            description=collaborator.description or f"Delegate task to {collaborator.name}",
            args_schema=CollaboratorInput,
            coroutine=delegate_to_collaborator,
        )

    async def _load_llm_config(self, agent: Agent) -> LLMConfig | None:
        """Load LLM configuration for agent"""
        if not agent.llm_config_id:
            return None
        config = await self.session.get(LLMConfig, agent.llm_config_id)
        if config and config.workspace_id == agent.workspace_id:
            return config
        return None

    async def _load_agent_tools(self, agent: Agent) -> list[Tool]:
        """Load and expand tools for agent"""
        tool_ids = agent.attached_tool_ids or []
        if not tool_ids:
            return []

        result = await self.session.execute(
            select(Tool).where(
                Tool.workspace_id == agent.workspace_id,
                Tool.id.in_(tool_ids),
                Tool.is_enabled == True,
            )
        )
        attached_tools = result.scalars().all()
        tools_by_id = {tool.id: tool for tool in attached_tools}

        mcp_server_ids = [
            tool.id for tool in attached_tools
            if tool.type.value == "MCP_SERVER"
        ]

        expanded_child_tools: list[Tool] = []
        if mcp_server_ids:
            child_result = await self.session.execute(
                select(Tool).where(
                    Tool.workspace_id == agent.workspace_id,
                    Tool.parent_id.in_(mcp_server_ids),
                    Tool.is_enabled == True,
                )
            )
            expanded_child_tools = list(child_result.scalars().all())

        ordered_tools: list[Tool] = []
        seen_ids: set[uuid.UUID] = set()

        for tool_id in tool_ids:
            attached_tool = tools_by_id.get(tool_id)
            if not attached_tool:
                continue

            if attached_tool.type.value == "MCP_SERVER":
                for child_tool in expanded_child_tools:
                    if child_tool.parent_id == attached_tool.id and child_tool.id not in seen_ids:
                        ordered_tools.append(child_tool)
                        seen_ids.add(child_tool.id)
                continue

            if attached_tool.id not in seen_ids:
                ordered_tools.append(attached_tool)
                seen_ids.add(attached_tool.id)

        return ordered_tools

    async def _load_collaborator_agents(self, agent: Agent) -> list[Agent]:
        """Load collaborator agents"""
        collaborator_ids = agent.collaborator_agent_ids or []
        if not collaborator_ids:
            return []

        result = await self.session.execute(
            select(Agent).where(
                Agent.workspace_id == agent.workspace_id,
                Agent.id.in_(collaborator_ids),
            )
        )
        collaborators_by_id = {collab.id: collab for collab in result.scalars().all()}
        return [
            collaborators_by_id[collab_id]
            for collab_id in collaborator_ids
            if collab_id in collaborators_by_id
        ]

    def _resolve_provider_model(self, config: LLMConfig) -> tuple[str | None, str | None]:
        """Resolve provider and model name from LLM config"""
        if not config:
            return None, None
        return config.provider.value, config.model_name

    def _apply_llm_credentials(self, config: LLMConfig) -> None:
        """Apply LLM credentials to environment variables"""
        if not config or not config.credentials:
            return

        provider = config.provider.value
        credentials = config.credentials or {}

        if provider == "ibm_watsonx":
            api_key = credentials.get("api_key") or credentials.get("apikey")
            project_id = credentials.get("project_id")
            region = credentials.get("region", "us-south")
            if api_key:
                os.environ["WATSONX_APIKEY"] = api_key
                os.environ["WATSONX_API_KEY"] = api_key
            if project_id:
                os.environ["WATSONX_PROJECT_ID"] = project_id
            if region:
                os.environ["WATSONX_REGION"] = region
                os.environ["WATSONX_URL"] = (
                    region if region.startswith("http")
                    else f"https://{region}.ml.cloud.ibm.com"
                )
        elif provider == "openai":
            api_key = credentials.get("api_key") or credentials.get("apikey")
            api_base = credentials.get("api_base") or credentials.get("url")
            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
            if api_base:
                os.environ["OPENAI_API_BASE"] = api_base
        elif provider == "ollama":
            api_base = credentials.get("api_base") or credentials.get("url")
            if api_base:
                os.environ["OLLAMA_API_BASE"] = api_base

# Made with Bob
