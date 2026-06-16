"""
Dynamic LangGraph Agent Executor with Pre-LLM Neural Tool Routing

This module implements a completely refactored LangGraph agent execution pipeline
that uses NeuralToolRouter (RouterService) for dynamic, per-query tool selection
BEFORE the LLM is invoked. This replaces the static tool binding approach.

Architecture:
    1. neural_routing_node: Pre-LLM node that uses RouterService to select top-k tools
    2. dynamic_llm_node: LLM node that binds ONLY the dynamically selected tools
    3. dynamic_tool_execution_node: Executes tool calls from the LLM
    4. Graph Flow: Start -> neural_routing -> llm -> [tool_execution -> llm] -> END
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, AsyncGenerator, Annotated, Sequence, Literal
from operator import add

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, create_model
from typing_extensions import TypedDict

from db.models import Agent, Tool, LLMConfig, Workspace
from services.router_service import RouterService
from services.embedding_service import embedding_service

logger = logging.getLogger("ntr.services.dynamic_langgraph_executor")

# Global cache for MCP clients to avoid starting/stopping subprocesses on every single tool call
_MCP_CLIENT_CACHE = {}
_MCP_CLIENT_LOCK = asyncio.Lock()


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


# ============================================================================
# AGENT STATE DEFINITION
# ============================================================================

class DynamicAgentState(TypedDict):
    """
    Enhanced AgentState with dynamic tool routing support.
    
    Fields:
        messages: Conversation history (LangGraph standard)
        suggested_tools: Tools selected by NeuralToolRouter for current query
        agent_config: Agent configuration metadata
        depth: Recursion depth for collaborator tracking
        last_tool_signature: Serialized signature of the last tool call(s) for loop detection
        tool_call_history: JSON-encoded dict mapping tool name -> call count for loop prevention
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    suggested_tools: list[Any]  # Dynamically selected tools from router
    agent_config: dict[str, Any]  # Agent metadata
    depth: int  # Collaboration depth
    last_tool_signature: str  # JSON signature of last tool call(s) for duplicate detection
    tool_call_history: str  # JSON dict of tool_name -> call_count for frequency-based loop detection


# ============================================================================
# DYNAMIC LANGGRAPH AGENT EXECUTOR
# ============================================================================

class DynamicLangGraphAgentExecutor:
    """
    Dynamic LangGraph agent executor with pre-LLM neural tool routing.
    
    This executor completely replaces static tool binding with a dynamic
    architecture where tools are selected per-query using NeuralToolRouter
    before the LLM is invoked.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.event_queue: list[str] = []  # Queue for SSE events
        self.queue: asyncio.Queue | None = None

    async def put_event(self, event: str) -> None:
        """Put event to the asyncio queue if present, otherwise append to event_queue"""
        if self.queue is not None:
            await self.queue.put(event)
        else:
            self.event_queue.append(event)

    async def execute_agent(
        self,
        agent: Agent,
        user_prompt: str,
        conversation_history: list[dict] | None = None,
        depth: int = 0,
        router_top_k_override: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Execute agent with dynamic neural tool routing.
        
        Args:
            agent: Agent configuration from database
            user_prompt: Current user message
            conversation_history: Previous messages for multi-turn conversations
            depth: Recursion depth for collaborator tracking
            router_top_k_override: Override agent.router_top_k for this execution
        """
        self.queue = asyncio.Queue()
        
        # Flush any previously accumulated event queue items into the queue
        while self.event_queue:
            await self.queue.put(self.event_queue.pop(0))

        async def run_flow():
            try:
                # Load agent dependencies
                llm_config = await self._load_llm_config(agent)
                if not llm_config:
                    await self.put_event(_sse_event(
                        "error",
                        "Missing LLM Configuration",
                        "Agent must have an LLM configuration assigned",
                        status_value="error",
                        metadata={"agent_id": str(agent.id), "agent_name": agent.name},
                    ))
                    await self.queue.put(None)
                    return

                tools = await self._load_agent_tools(agent)
                collaborators = await self._load_collaborator_agents(agent)

                # Apply LLM credentials
                self._apply_llm_credentials(llm_config)

                # Emit initialization event
                history_length = len(conversation_history) if conversation_history else 0
                await self.put_event(_sse_event(
                    "reasoning",
                    f"Initializing Dynamic Agent: {agent.name}",
                    f"Configuration: {len(tools)} tools available, {len(collaborators)} collaborators, "
                    f"neural_router={'enabled' if agent.use_neural_router else 'disabled'}, "
                    f"memory={agent.memory_type or 'buffer'}, history={history_length} messages",
                    status_value="running",
                    metadata={
                        "depth": depth,
                        "agent_id": str(agent.id),
                        "agent_name": agent.name,
                        "tool_count": len(tools),
                        "collaborator_count": len(collaborators),
                        "use_neural_router": agent.use_neural_router,
                        "memory_type": agent.memory_type or "buffer",
                        "memory_window": agent.memory_window or 10,
                        "history_length": history_length,
                        "max_iterations": agent.max_iterations or 10,
                    },
                ))

                # Execute with dynamic LangGraph
                await self._execute_with_dynamic_langgraph(
                    agent=agent,
                    llm_config=llm_config,
                    available_tools=tools,
                    collaborators=collaborators,
                    user_prompt=user_prompt,
                    depth=depth,
                    router_top_k_override=router_top_k_override,
                    conversation_history=conversation_history,
                )
                await self.queue.put(None)

            except Exception as exc:
                logger.exception(f"Dynamic agent execution failed for {agent.id}")
                await self.put_event(_sse_event(
                    "error",
                    "Agent Execution Failed",
                    str(exc),
                    status_value="error",
                    metadata={
                        "error_type": type(exc).__name__,
                        "agent_id": str(agent.id),
                        "depth": depth,
                    },
                ))
                await self.queue.put(None)

        task = asyncio.create_task(run_flow())
        try:
            while True:
                item = await self.queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _execute_with_dynamic_langgraph(
        self,
        agent: Agent,
        llm_config: LLMConfig,
        available_tools: list[Tool],
        collaborators: list[Agent],
        user_prompt: str,
        depth: int,
        router_top_k_override: int | None = None,
        conversation_history: list[dict] | None = None,
    ) -> None:
        """Execute agent using dynamic LangGraph with neural routing"""
        try:
            from tool_router.executors.langgraph_executor import LiteLLMChatOpenAI

            # Get LLM model
            provider, model_name = self._resolve_provider_model(llm_config)
            if not provider or not model_name:
                raise ValueError("Invalid LLM configuration")

            # Normalize provider name for LiteLLM (expects lowercase)
            provider = provider.lower()
            if provider == "ibm_watsonx":
                provider = "watsonx"

            litellm_model = f"{provider}/{model_name}"
            logger.info(f"Creating dynamic LangGraph agent with model: {litellm_model}")
            print(f"\n\nCreating dynamic LangGraph agent with model: >> {litellm_model}\n\n")

            llm = LiteLLMChatOpenAI(
                model="gpt-4o",
                litellm_model=litellm_model,
                openai_api_key="litellm-dummy-key",
                temperature=0.0,
                max_tokens=llm_config.max_tokens,
            )

            # Build the dynamic graph
            workflow = StateGraph(DynamicAgentState)

            # Store context for node functions
            context = {
                "agent": agent,
                "llm": llm,
                "llm_config": llm_config,
                "available_tools": available_tools,
                "collaborators": collaborators,
                "depth": depth,
                "router_top_k_override": router_top_k_override,
                "executor": self,
            }

            # ================================================================
            # NODE 1: NEURAL ROUTING NODE (Pre-LLM)
            # ================================================================
            # ================================================================
            # NODE 1: NEURAL ROUTING NODE (Pre-LLM)
            # ================================================================
            async def neural_routing_node(state: DynamicAgentState) -> dict:
                """
                Pre-LLM node that uses NeuralToolRouter to select top-k tools
                and sub-agents based on the latest user message or task.
                """
                import numpy as np
                messages = state["messages"]
                
                router_query = None
                
                # 1. Check for explicit fetch_tools_for_task tool call
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage):
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                if tc.get("name") == "fetch_tools_for_task":
                                    router_query = tc.get("args", {}).get("task")
                                    if router_query:
                                        break
                        if router_query:
                            break
                
                # 2. Check for explicit "Current Task:" or "Task:" in agent messages
                if not router_query:
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage) and msg.content:
                            content = msg.content
                            import re
                            # Match patterns like:
                            # Current Task: <task>
                            # Task: <task>
                            # Next Step: <task>
                            # Plan: <task>
                            match = re.search(r'(?:Current\s+)?Task\s*:\s*([^\n\r]+)', content, re.IGNORECASE)
                            if not match:
                                match = re.search(r'Next\s+Step\s*:\s*([^\n\r]+)', content, re.IGNORECASE)
                            if not match:
                                match = re.search(r'Plan\s*:\s*([^\n\r]+)', content, re.IGNORECASE)
                            
                            if match:
                                router_query = match.group(1).strip()
                                logger.info(f"Parsed router query from task pattern: '{router_query}'")
                                break

                # If no explicit task query is found, and we already have suggested tools,
                # preserve them and return without querying the router.
                if not router_query and state.get("suggested_tools"):
                    logger.info("Preserving existing suggested tools as no new task was specified.")
                    return {"suggested_tools": state["suggested_tools"]}

                # 3. Check for latest user prompt
                if not router_query:
                    for msg in reversed(messages):
                        if isinstance(msg, HumanMessage) and msg.content:
                            router_query = msg.content
                            break
                
                # 4. Fallback to initial user prompt
                if not router_query:
                    router_query = user_prompt

                agent_obj = context["agent"]
                available = context["available_tools"]
                collaborators = context["collaborators"]
                top_k_override = context["router_top_k_override"]
                executor = context["executor"]

                # Use neural router if enabled
                if agent_obj.use_neural_router:
                    # Build the set of tool IDs the agent is ALLOWED to use
                    # (only the agent's own attached tools, NOT all workspace tools)
                    allowed_tool_ids = {str(t.id) for t in available}
                    
                    top_k = top_k_override or agent_obj.router_top_k or 3
                    start_time = time.perf_counter()
                    
                    print(f"\n\nRouter query: >> {router_query}")
                    
                    # 1. Retrieve candidates from NeuralToolRouter (workspace-wide search)
                    router_result = await RouterService.predict(
                        session=executor.session,
                        workspace_id=agent_obj.workspace_id,
                        user_prompt=router_query,
                        top_k=max(top_k * 3, 10),  # fetch extra to filter
                        redis=None,
                    )
                    
                    tools_candidates = router_result.get("tools", [])
                    
                    # 2. Filter to ONLY the agent's own attached tools
                    filtered_candidates = [
                        t for t in tools_candidates
                        if t["id"] in allowed_tool_ids
                    ]
                    
                    # 3. Fetch DB records for filtered candidates only
                    filtered_candidate_ids = [uuid.UUID(t["id"]) for t in filtered_candidates]
                    if filtered_candidate_ids:
                        db_tools_res = await executor.session.execute(
                            select(Tool).where(
                                Tool.workspace_id == agent_obj.workspace_id,
                                Tool.id.in_(filtered_candidate_ids),
                                Tool.is_enabled == True,
                            )
                        )
                        db_tools = {str(t.id): t for t in db_tools_res.scalars().all()}
                    else:
                        db_tools = {}
                    
                    scored_tools = []
                    SIMILARITY_THRESHOLD = 0.40
                    added_tool_ids = set()
                    
                    for t in filtered_candidates:
                        t_id = t["id"]
                        if t_id in db_tools:
                            tool_obj = db_tools[t_id]
                            t_name = tool_obj.name.lower()
                            
                            is_core_tool = False
                            if agent_obj.description:
                                desc_lower = agent_obj.description.lower()
                                if t_name in desc_lower or t_name.replace('_', ' ') in desc_lower:
                                    is_core_tool = True
                            if agent_obj.system_prompt:
                                prompt_lower = agent_obj.system_prompt.lower()
                                if t_name in prompt_lower or t_name.replace('_', ' ') in prompt_lower:
                                    is_core_tool = True
                                    
                            if is_core_tool or t["similarity"] >= SIMILARITY_THRESHOLD:
                                scored_tools.append((tool_obj, t["similarity"]))
                                added_tool_ids.add(t_id)

                    # Ensure all core tools from the agent's available list are included
                    for tool_obj in available:
                        t_id = str(tool_obj.id)
                        if t_id not in added_tool_ids:
                            t_name = tool_obj.name.lower()
                            is_core_tool = False
                            if agent_obj.description:
                                desc_lower = agent_obj.description.lower()
                                if t_name in desc_lower or t_name.replace('_', ' ') in desc_lower:
                                    is_core_tool = True
                            if agent_obj.system_prompt:
                                prompt_lower = agent_obj.system_prompt.lower()
                                if t_name in prompt_lower or t_name.replace('_', ' ') in prompt_lower:
                                    is_core_tool = True
                            
                            if is_core_tool:
                                scored_tools.append((tool_obj, 0.35))
                                added_tool_ids.add(t_id)
                    
                    # 4. Sort by score and select top_k tools
                    scored_tools.sort(key=lambda x: x[1], reverse=True)
                    selected_scored = scored_tools[:top_k]
                    selected = [item[0] for item in selected_scored]
                    
                    # Combine and accumulate with existing suggested tools in the state
                    existing = state.get("suggested_tools", [])
                    combined = list(existing)
                    existing_ids = {str(item.id) if hasattr(item, "id") else getattr(item, "name", str(item)) for item in existing}
                    for item in selected:
                        item_id = str(item.id) if hasattr(item, "id") else getattr(item, "name", str(item))
                        if item_id not in existing_ids:
                            combined.append(item)
                    selected = combined
                    
                    # NOTE: Collaborator sub-agents are ALWAYS added separately in
                    # dynamic_llm_node and dynamic_tool_execution_node.
                    # The router only selects TOOLS, not sub-agents.
                    
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    
                    selected_tool_ids = []
                    selected_agent_ids = []
                    selected_serialized = []
                    for item, score in selected_scored:
                        if isinstance(item, Tool):
                            selected_tool_ids.append(str(item.id))
                            selected_serialized.append({
                                "id": str(item.id),
                                "name": item.name,
                                "type": item.type.value,
                                "score": score,
                                "description": item.description,
                                "parameters": item.schema_def,
                            })
                        elif isinstance(item, Agent):
                            selected_agent_ids.append(str(item.id))
                            selected_serialized.append({
                                "id": str(item.id),
                                "name": item.name,
                                "type": "SUB_AGENT",
                                "score": score,
                                "description": item.description,
                                "system_prompt": item.system_prompt,
                            })
                    
                    # Also serialize collaborators for frontend visibility
                    collab_serialized = []
                    for collab in collaborators:
                        collab_serialized.append({
                            "id": str(collab.id),
                            "name": collab.name,
                            "type": "COLLABORATOR",
                            "description": collab.description,
                        })
                    
                    router_metadata = {
                        "strategy": "neural_router",
                        "router_top_k": top_k,
                        "query": router_query,
                        "selected_tool_ids": selected_tool_ids,
                        "selected_agent_ids": [str(c.id) for c in collaborators],
                        "ranked_tools": selected_serialized,
                        "always_available_collaborators": collab_serialized,
                        "cached": router_result.get("cached", False),
                        "latency_ms": latency_ms,
                    }

                    print(f"\n\nRouter metadata: >> {router_metadata}\n\n")

                else:
                    selected = available + collaborators
                    selected_serialized = []
                    for item in selected:
                        if isinstance(item, Tool):
                            selected_serialized.append({
                                "id": str(item.id),
                                "name": item.name,
                                "type": item.type.value,
                                "description": item.description,
                                "parameters": item.schema_def,
                            })
                        elif isinstance(item, Agent):
                            selected_serialized.append({
                                "id": str(item.id),
                                "name": item.name,
                                "type": "SUB_AGENT",
                                "description": item.description,
                                "system_prompt": item.system_prompt,
                            })
                    router_metadata = {
                        "strategy": "attached_tools",
                        "query": router_query,
                        "selected_tool_ids": [str(tool.id) for tool in available],
                        "selected_agent_ids": [str(collab.id) for collab in collaborators],
                        "total_tools": len(selected),
                    }

                # Emit router event
                strategy = router_metadata.get("strategy", "attached_tools")
                label = "Neural Tool Router Selection" if strategy == "neural_router" else "Attached Tool Selection"
                
                detail = _safe_json({
                    "selected_tools": selected_serialized,
                    "router": router_metadata,
                })
                
                await executor.put_event(_sse_event(
                    "router",
                    label,
                    detail,
                    status_value="success",
                    latency_ms=router_metadata.get("latency_ms"),
                    metadata={
                        **router_metadata,
                        "depth": depth,
                        "agent_id": str(agent_obj.id),
                        "agent_name": agent_obj.name,
                        "selected_tools": selected_serialized,
                    },
                ))

                return {"suggested_tools": selected}

            # ================================================================
            # NODE 2: DYNAMIC LLM NODE
            # ================================================================
            async def dynamic_llm_node(state: DynamicAgentState) -> dict:
                """
                LLM node that dynamically binds ONLY the tools and sub-agents in suggested_tools.
                """
                messages = state["messages"]
                suggested_tools = state.get("suggested_tools", [])
                agent_obj = context["agent"]
                llm_obj = context["llm"]
                executor = context["executor"]

                # Separate suggested_tools into tools and sub-agents
                db_tools = [item for item in suggested_tools if isinstance(item, Tool)]
                db_agents = [item for item in suggested_tools if isinstance(item, Agent)]

                # Convert suggested tools to LangChain format
                langchain_tools = await executor._convert_tools_to_langchain(db_tools)

                # Add collaborator tools from router-selected sub-agents
                routed_agent_ids = {str(a.id) for a in db_agents}
                for collab in db_agents:
                    collab_tool = executor._create_collaborator_tool(collab, depth)
                    langchain_tools.append(collab_tool)

                # ALWAYS include ALL configured collaborators — they should never be
                # filtered by the neural router.  Only add those not already included
                # from the router selection to avoid duplicates.
                all_collaborators = context["collaborators"]
                for collab in all_collaborators:
                    if str(collab.id) not in routed_agent_ids:
                        collab_tool = executor._create_collaborator_tool(collab, depth)
                        langchain_tools.append(collab_tool)

                # Always make fetch_tools_for_task available if neural router is enabled
                if agent_obj.use_neural_router:
                    langchain_tools.append(executor._create_fetch_tools_tool())

                # Apply workflow dependency filtering for Claim Processing Agent
                def get_workflow_state(msgs) -> dict:
                    has_policy_info = False
                    has_billing_info = False
                    has_calculation_info = False
                    
                    for m in msgs:
                        m_class = m.__class__.__name__
                        if m_class == "SystemMessage":
                            continue
                        
                        content = getattr(m, "content", "") or ""
                        if not isinstance(content, str):
                            content = str(content)
                        content_lower = content.lower()
                        
                        m_name = getattr(m, "name", "") or ""
                        
                        # In LiteLLMChatOpenAI, ToolMessage is serialized as a User message with "[Tool Result - name]"
                        if m_class == "ToolMessage" or "[Tool Result" in content:
                            if m_name in ("get_policy_details", "check_coverage_limits", "delegate_to_policy_agent") or \
                               "[Tool Result - get_policy_details]" in content or \
                               "[Tool Result - check_coverage_limits]" in content or \
                               "[Tool Result - delegate_to_policy_agent]" in content:
                                if "error" not in content_lower:
                                    has_policy_info = True
                                    
                            if m_name in ("fetch_discharge_summary", "verify_hospital_bills", "delegate_to_billing_agent") or \
                               "[Tool Result - fetch_discharge_summary]" in content or \
                               "[Tool Result - verify_hospital_bills]" in content or \
                               "[Tool Result - delegate_to_billing_agent]" in content:
                                if "error" not in content_lower:
                                    has_billing_info = True
                                    
                            if m_name == "calculate_claimable_amount" or "[Tool Result - calculate_claimable_amount]" in content:
                                if "error" not in content_lower and "validation error" not in content_lower:
                                    has_calculation_info = True
                        else:
                            # Fallback check for text values in assistant/user messages
                            if "coverage_limit" in content_lower or "coverage limit" in content_lower:
                                has_policy_info = True
                            if "total_bill" in content_lower or "bill_details" in content_lower:
                                has_billing_info = True
                            if "calculate_claimable_amount" in content_lower and "result" in content_lower and "error" not in content_lower:
                                has_calculation_info = True
                                
                    return {
                        "has_policy_info": has_policy_info,
                        "has_billing_info": has_billing_info,
                        "has_calculation_info": has_calculation_info,
                    }

                w_state = get_workflow_state(messages)
                
                # Check which tools have already succeeded in the history to prevent loops
                successful_tools = set()
                for m in messages:
                    m_class = m.__class__.__name__
                    if m_class == "SystemMessage":
                        continue
                    
                    content = getattr(m, "content", "") or ""
                    if not isinstance(content, str):
                        content = str(content)
                    content_lower = content.lower()
                    
                    m_name = getattr(m, "name", "") or ""
                    
                    # Detect successful tool execution in the history
                    if m_class == "ToolMessage" or "[Tool Result" in content:
                        tool_name = None
                        if m_class == "ToolMessage" and m_name:
                            tool_name = m_name
                        else:
                            # Extract tool name from "[Tool Result - name]"
                            import re
                            match = re.search(r'\[Tool Result -\s*([a-zA-Z0-9_-]+)\]', content)
                            if match:
                                tool_name = match.group(1)
                                
                        if tool_name and "error" not in content_lower and "validation error" not in content_lower:
                            successful_tools.add(tool_name)

                filtered_langchain_tools = []
                for t in langchain_tools:
                    # Defer calculate_claimable_amount until policy and billing info are available
                    if t.name == "calculate_claimable_amount":
                        if not (w_state["has_policy_info"] and w_state["has_billing_info"]):
                            logger.info("Deferring calculate_claimable_amount tool as policy or billing info is not yet available.")
                            continue
                    # Defer submit_mediclaim until claimable amount has been calculated
                    if t.name == "submit_mediclaim":
                        if not w_state["has_calculation_info"]:
                            logger.info("Deferring submit_mediclaim tool as calculation has not yet been performed.")
                            continue
                    
                    # Remove from active binding if it has already succeeded in this execution session
                    if t.name in successful_tools and t.name != "fetch_tools_for_task":
                        logger.info(f"Removing successfully executed tool '{t.name}' from active binding.")
                        continue
                    
                    filtered_langchain_tools.append(t)

                
                langchain_tools = filtered_langchain_tools


                # Enhanced system prompt with Think, Plan, Act framework
                base_system_prompt = agent_obj.system_prompt or "You are a helpful AI assistant."
                
                # Check if all actual action tools have executed (only fetch_tools_for_task or nothing left)
                actual_tools = [t for t in langchain_tools if t.name != "fetch_tools_for_task"]
                
                if actual_tools:
                    tool_names = [t.name for t in langchain_tools]
                    tool_usage_instruction = f"""

IMPORTANT: You have access to the following tools: {', '.join(tool_names)}

**Think, Plan, Act Framework:**
1. **Think**: Analyze the user's request and identify what information you need
2. **Plan**: Determine which tools to use and in what order
3. **Act**: Execute the tools to gather information

You MUST use these tools to gather information before providing your final answer. Do not make assumptions or provide answers without using the available tools first.

For delegating to sub-agents (collaborators), use the delegate_to_* tools when the task requires specialized expertise.

Always use tools when they are relevant to the user's question."""

                    if agent_obj.use_neural_router:
                        tool_usage_instruction += """

**Dynamic Tool Retrieval & Planning Protocol:**
You are equipped with a virtual tool called `fetch_tools_for_task`. Since you only have a subset of all available tools loaded in your context at any time:
1. You MUST always start your response with a brief natural language paragraph explaining your thinking/reasoning and current plan.
2. You MUST explicitly state the current sub-task you are about to perform on a single line starting with "Current Task: <description>" (e.g., "Current Task: Retrieve insurance policy details for POL-999"). The platform reads this line to load the correct tools.
3. If the tools you need are not listed above, you MUST call the tool `fetch_tools_for_task(task="description of the task")` to dynamically retrieve and load them. Once you call this tool, the system will automatically refresh your available tools with the best candidates for that task in the next turn."""

                    # Instruction to present friendly response instead of raw JSON
                    tool_usage_instruction += """

**Final Response Formatting:**
When you have completed all tasks and have all the information required, present your final response to the user in a friendly, professional, natural language summary (using Markdown formatting or tables if appropriate). Do NOT output raw JSON blocks as your final response unless specifically requested."""

                    system_message_content = base_system_prompt + tool_usage_instruction
                else:
                    no_tools_instruction = """

All requested action tools have executed successfully and you have gathered all necessary information. 
Please present your final response to the user in a friendly, professional, natural language summary (using Markdown formatting, bullet points, or tables as appropriate). 
Do NOT output raw JSON blocks or tool call JSON structures since execution is complete."""
                    system_message_content = base_system_prompt + no_tools_instruction

                # Check if all actual action tools have executed
                actual_tools = [t for t in langchain_tools if t.name != "fetch_tools_for_task"]
                if not actual_tools:
                    logger.info("No action tools left (all executed successfully). Clearing langchain_tools to allow direct text response.")
                    langchain_tools = []

                # Dynamically bind tools to LLM
                if langchain_tools:
                    llm_with_tools = llm_obj.bind_tools(langchain_tools)
                else:
                    llm_with_tools = llm_obj

                # Update the system message to ensure the LLM sees the latest dynamically selected tools
                llm_messages = []
                system_msg_added = False
                for msg in messages:
                    if isinstance(msg, SystemMessage):
                        if not system_msg_added:
                            llm_messages.append(SystemMessage(content=system_message_content))
                            system_msg_added = True
                    else:
                        llm_messages.append(msg)
                if not system_msg_added:
                    llm_messages = [SystemMessage(content=system_message_content)] + llm_messages

                # Format full prompt history for debugging visibility in frontend
                full_prompt_str = ""
                for msg in llm_messages:
                    if isinstance(msg, SystemMessage):
                        full_prompt_str += f"=== System Prompt ===\n{msg.content}\n\n"
                    elif isinstance(msg, HumanMessage):
                        full_prompt_str += f"=== User Message ===\n{msg.content}\n\n"
                    elif isinstance(msg, AIMessage):
                        full_prompt_str += f"=== Assistant (AI) Message ===\n{msg.content}\n\n"
                    else:
                        full_prompt_str += f"=== {type(msg).__name__} ===\n{getattr(msg, 'content', str(msg))}\n\n"

                # Emit thinking event with complete LLM Prompt
                await executor.put_event(_sse_event(
                    "thought",
                    "Agent Thinking",
                    f"Analyzing request with {len(langchain_tools)} dynamically selected tools...",
                    status_value="running",
                    metadata={
                        "depth": depth,
                        "agent_id": str(agent_obj.id),
                        "agent_name": agent_obj.name,
                        "input": full_prompt_str,
                        "tool_count": len(langchain_tools),
                    },
                ))

                # Invoke LLM with streaming to show updates in real-time
                start_time = time.perf_counter()
                
                full_message = None
                async for chunk in llm_with_tools.astream(llm_messages):
                    if full_message is None:
                        full_message = chunk
                    else:
                        full_message += chunk
                    
                    if full_message.content:
                        # Emit reasoning streaming update
                        await executor.put_event(_sse_event(
                            "reasoning",
                            "Agent Reasoning",
                            full_message.content,
                            status_value="running",
                            metadata={
                                "depth": depth,
                                "agent_id": str(agent_obj.id),
                                "agent_name": agent_obj.name,
                            },
                        ))
                
                latency_ms = (time.perf_counter() - start_time) * 1000
                
                if full_message is None:
                    response = AIMessage(content="")
                else:
                    response = full_message

                # Fallback: Parse tool call from content if the model didn't
                # produce native tool_calls (e.g. WatsonX, models without
                # function-calling support).  Handles multiple formats:
                #   • {"name": "...", "arguments": {...}}
                #   • [{"name": "...", "arguments": {...}}, ...]
                #   • Mixed text with embedded JSON
                #   • <tool_call>{"name": "...", ...}</tool_call> XML wrapping
                if (not getattr(response, "tool_calls", None)) and response.content:
                    content_str = response.content.strip()
                    parsed_tool_calls = []
                    tool_names = {t.name for t in langchain_tools}

                    import re as _re
                    xml_tool_pattern = _re.compile(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', _re.DOTALL)
                    code_block_pattern = _re.compile(r'```(?:json)?\s*\n(.*?)\n\s*```', _re.DOTALL)
                    json_name_pattern = _re.compile(r'\{[^{}]*"name"\s*:\s*"[^"]+?"[^{}]*\}')
                    json_action_pattern = _re.compile(r'\{[^{}]*"action"\s*:\s*"[^"]+?"[^{}]*\}')
                    json_tool_pattern = _re.compile(r'\{[^{}]*"tool"\s*:\s*"[^"]+?"[^{}]*\}')

                    def extract_tool_calls_from_string(s: str) -> list:
                        s_str = s.strip()
                        if not s_str:
                            return []
                        
                        calls = []
                        # 1. XML tool calls
                        xml_matches = xml_tool_pattern.findall(s_str)
                        for match in xml_matches:
                            try:
                                parsed = json.loads(match)
                                calls.extend(extract_tool_calls(parsed))
                            except Exception:
                                pass
                        
                        # 2. Markdown code blocks
                        code_matches = code_block_pattern.findall(s_str)
                        for match in code_matches:
                            try:
                                parsed = json.loads(match.strip())
                                calls.extend(extract_tool_calls(parsed))
                            except Exception:
                                pass
                                
                        # 3. Try parsing the string directly as JSON
                        try:
                            clean_s = s_str
                            if clean_s.startswith("```"):
                                lines = clean_s.split("\n")
                                if len(lines) > 2:
                                    clean_s = "\n".join(lines[1:-1]).strip()
                            parsed = json.loads(clean_s)
                            calls.extend(extract_tool_calls(parsed))
                        except Exception:
                            pass
                            
                        # 4. Regex search for JSON objects with name/action/tool
                        for pattern in [json_name_pattern, json_action_pattern, json_tool_pattern]:
                            matches = pattern.findall(s_str)
                            for match in matches:
                                try:
                                    parsed = json.loads(match)
                                    calls.extend(extract_tool_calls(parsed))
                                except Exception:
                                    pass
                        return calls

                    def extract_tool_calls(parsed_obj):
                        calls = []
                        if isinstance(parsed_obj, dict):
                            # Standard tool call keys
                            name = (parsed_obj.get("name") or 
                                    parsed_obj.get("action") or 
                                    parsed_obj.get("tool") or 
                                    parsed_obj.get("tool_name") or 
                                    parsed_obj.get("function") or 
                                    parsed_obj.get("toolName"))
                            args = parsed_obj.get("arguments") or parsed_obj.get("args") or parsed_obj.get("action_input") or parsed_obj.get("parameters") or {}
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except Exception:
                                    pass
                            
                            if name and isinstance(name, str) and name in tool_names:
                                calls.append({"name": name, "args": args})
                            
                            # Recursively inspect all items in the dict (both values and nested structures)
                            for val in parsed_obj.values():
                                if isinstance(val, str):
                                    calls.extend(extract_tool_calls_from_string(val))
                                elif isinstance(val, (dict, list)):
                                    calls.extend(extract_tool_calls(val))
                        elif isinstance(parsed_obj, list):
                            for item in parsed_obj:
                                calls.extend(extract_tool_calls(item))
                        return calls

                    parsed_tool_calls.extend(extract_tool_calls_from_string(content_str))
                    
                    # Convert parsed tool calls to LangChain format
                    if parsed_tool_calls:
                        lc_tool_calls = []
                        for tc in parsed_tool_calls:
                            tool_name = tc["name"]
                            tool_args = tc["args"]
                            if isinstance(tool_args, str):
                                try:
                                    tool_args = json.loads(tool_args)
                                except Exception:
                                    pass
                            lc_tool_calls.append({
                                "name": tool_name,
                                "args": tool_args,
                                "id": str(uuid.uuid4()),
                                "type": "tool_call"
                            })
                        
                        # Clean up response.content by removing the parsed JSON and XML tool call patterns
                        cleaned_content = response.content
                        if cleaned_content:
                            # 1. Remove XML tool call wrappers
                            cleaned_content = _re.sub(r'</?tool_call>', '', cleaned_content)
                            
                            # 2. Remove successfully parsed JSON blocks using a brace-matching algorithm
                            idx = 0
                            while idx < len(cleaned_content):
                                if cleaned_content[idx] == '{':
                                    nesting = 1
                                    j = idx + 1
                                    in_string = False
                                    escape = False
                                    while j < len(cleaned_content):
                                        char = cleaned_content[j]
                                        if in_string:
                                            if escape:
                                                escape = False
                                            elif char == '\\':
                                                escape = True
                                            elif char == '"':
                                                in_string = False
                                        else:
                                            if char == '"':
                                                in_string = True
                                            elif char == '{':
                                                nesting += 1
                                            elif char == '}':
                                                nesting -= 1
                                                if nesting == 0:
                                                    candidate = cleaned_content[idx:j+1]
                                                    try:
                                                        json.loads(candidate)
                                                        cleaned_content = cleaned_content[:idx] + cleaned_content[j+1:]
                                                        idx -= 1
                                                        break
                                                    except Exception:
                                                        pass
                                        j += 1
                                idx += 1
                            
                            # 3. Clean up residual markdown code block structures and clean whitespace
                            cleaned_content = _re.sub(r'```(?:json)?\s*```', '', cleaned_content)
                            cleaned_content = _re.sub(r'```(?:json)?', '', cleaned_content)
                            cleaned_content = cleaned_content.strip()
                        
                        response = AIMessage(
                            content=cleaned_content,
                            tool_calls=lc_tool_calls
                        )
                        tool_names_parsed = [tc["name"] for tc in lc_tool_calls]
                        logger.info(f"Successfully parsed {len(lc_tool_calls)} tool call(s) from content: {tool_names_parsed}")

                # Check for tool calls and build signature for loop detection
                new_tool_signature = ""
                # Update tool call history (frequency tracking)
                history_raw = state.get("tool_call_history", "{}")
                try:
                    tool_call_counts = json.loads(history_raw) if history_raw else {}
                except Exception:
                    tool_call_counts = {}

                if hasattr(response, "tool_calls") and response.tool_calls:
                    sig_parts = []
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get("name", "unknown")
                        tool_args = tool_call.get("args", {})
                        sig_parts.append(json.dumps({"name": tool_name, "args": tool_args}, sort_keys=True, default=str))
                        
                        # Track per-tool call frequency
                        tool_call_counts[tool_name] = tool_call_counts.get(tool_name, 0) + 1
                        
                        detail = _safe_json({
                            "tool_name": tool_name,
                            "arguments": tool_args,
                        })
                        
                        await executor.put_event(_sse_event(
                            "tool_call",
                            f"Calling {tool_name}",
                            detail,
                            status_value="running",
                            metadata={
                                "depth": depth,
                                "agent_id": str(agent_obj.id),
                                "agent_name": agent_obj.name,
                                "tool_name": tool_name,
                                "tool_args": tool_args,
                            },
                        ))
                    new_tool_signature = "|".join(sorted(sig_parts))
                else:
                    # No tool calls — log content for debugging (especially WatsonX)
                    content_preview = (response.content or "")[:200]
                    logger.info(
                        f"LLM produced NO tool calls. Content preview: {content_preview!r}"
                    )

                return {
                    "messages": [response],
                    "last_tool_signature": new_tool_signature,
                    "tool_call_history": json.dumps(tool_call_counts),
                }

            # ================================================================
            # NODE 3: DYNAMIC TOOL EXECUTION NODE
            # ================================================================
            async def dynamic_tool_execution_node(state: DynamicAgentState) -> dict:
                """
                Execute tool calls from the LLM using the dynamically mapped tools.
                """
                messages = state["messages"]
                suggested_tools = state.get("suggested_tools", [])
                agent_obj = context["agent"]
                executor = context["executor"]

                # Get the last AI message with tool calls
                last_message = messages[-1]
                if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
                    return {"messages": []}

                # Separate suggested_tools into tools and sub-agents
                db_tools = [item for item in suggested_tools if isinstance(item, Tool)]
                db_agents = [item for item in suggested_tools if isinstance(item, Agent)]

                # Convert suggested tools to LangChain format for execution
                langchain_tools = await executor._convert_tools_to_langchain(db_tools)
                
                # Add collaborator tools from router-selected sub-agents
                routed_agent_ids = {str(a.id) for a in db_agents}
                for collab in db_agents:
                    collab_tool = executor._create_collaborator_tool(collab, depth)
                    langchain_tools.append(collab_tool)

                # ALWAYS include ALL configured collaborators for execution
                all_collaborators = context["collaborators"]
                for collab in all_collaborators:
                    if str(collab.id) not in routed_agent_ids:
                        collab_tool = executor._create_collaborator_tool(collab, depth)
                        langchain_tools.append(collab_tool)

                # Always make fetch_tools_for_task available if neural router is enabled
                if agent_obj.use_neural_router:
                    langchain_tools.append(executor._create_fetch_tools_tool())

                # Create tool map
                tool_map = {tool.name: tool for tool in langchain_tools}

                # Execute each tool call
                tool_messages = []
                for tool_call in last_message.tool_calls:
                    tool_name = tool_call.get("name")
                    tool_args = tool_call.get("args", {})
                    tool_call_id = tool_call.get("id", str(uuid.uuid4()))

                    if tool_name in tool_map:
                        tool = tool_map[tool_name]
                        tool_start_time = time.perf_counter()
                        try:
                            # Execute tool
                            if hasattr(tool, "coroutine") and tool.coroutine:
                                result = await tool.coroutine(**tool_args)
                            else:
                                result = await tool.ainvoke(tool_args)
                            
                            tool_latency_ms = (time.perf_counter() - tool_start_time) * 1000
                            result_str = str(result)
                            
                            # Emit tool result
                            await executor.put_event(_sse_event(
                                "tool_result",
                                f"{tool_name} Result",
                                result_str,
                                status_value="success",
                                latency_ms=tool_latency_ms,
                                metadata={
                                    "depth": depth,
                                    "agent_id": str(agent_obj.id),
                                    "agent_name": agent_obj.name,
                                    "tool_name": tool_name,
                                    "tool_args": tool_args,
                                    "result": result_str,
                                    "success": True,
                                    "execution_time": tool_latency_ms,
                                },
                            ))
                            
                            tool_messages.append(
                                ToolMessage(
                                    content=result_str,
                                    tool_call_id=tool_call_id,
                                    name=tool_name,
                                )
                            )
                        except Exception as e:
                            tool_latency_ms = (time.perf_counter() - tool_start_time) * 1000
                            error_msg = f"Tool execution failed: {str(e)}"
                            logger.error(f"Tool {tool_name} failed: {e}")
                            
                            await executor.put_event(_sse_event(
                                "tool_result",
                                f"{tool_name} Error",
                                error_msg,
                                status_value="error",
                                latency_ms=tool_latency_ms,
                                metadata={
                                    "depth": depth,
                                    "agent_id": str(agent_obj.id),
                                    "agent_name": agent_obj.name,
                                    "tool_name": tool_name,
                                    "tool_args": tool_args,
                                    "result": error_msg,
                                    "success": False,
                                    "execution_time": tool_latency_ms,
                                },
                            ))
                            
                            tool_messages.append(
                                ToolMessage(
                                    content=error_msg,
                                    tool_call_id=tool_call_id,
                                    name=tool_name,
                                )
                            )
                    else:
                        error_msg = f"Tool {tool_name} not found in suggested tools"
                        await executor.put_event(_sse_event(
                            "tool_result",
                            f"{tool_name} Error",
                            error_msg,
                            status_value="error",
                            latency_ms=0.0,
                            metadata={
                                "depth": depth,
                                "agent_id": str(agent_obj.id),
                                "agent_name": agent_obj.name,
                                "tool_name": tool_name,
                                "tool_args": tool_args,
                                "result": error_msg,
                                "success": False,
                                "execution_time": 0.0,
                            },
                        ))
                        tool_messages.append(
                            ToolMessage(
                                content=error_msg,
                                tool_call_id=tool_call_id,
                                name=tool_name,
                            )
                        )

                return {"messages": tool_messages}

            # ================================================================
            # CONDITIONAL EDGE: Should we continue or end?
            # ================================================================
            _prev_tool_sig: list[str] = [""]  # mutable closure for tracking
            MAX_CALLS_PER_TOOL = 3  # Maximum times any single tool can be called
            # Meta-tools that are exempt from frequency caps
            _FREQUENCY_EXEMPT_PREFIXES = ("fetch_tools_for_task", "delegate_to_")

            def should_continue(state: DynamicAgentState) -> Literal["continue", "end"]:
                """Determine if we should continue to tool execution or end.
                
                Two layers of loop detection:
                1. Exact duplicate: same tool call(s) with same args repeated consecutively
                2. Frequency cap: any single tool called more than MAX_CALLS_PER_TOOL times
                """
                messages = state["messages"]
                last_message = messages[-1]
                
                # If the last message has tool calls, continue to tool execution
                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    executor_ref = context["executor"]
                    agent_name = context["agent"].name
                    
                    # --- Check 1: Exact duplicate signature ---
                    current_sig = state.get("last_tool_signature", "")
                    if current_sig and current_sig == _prev_tool_sig[0]:
                        logger.warning(
                            "Loop detected: identical tool call signature repeated — "
                            "forcing END. Signature: %s", current_sig
                        )
                        import asyncio
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(executor_ref.put_event(_sse_event(
                                "error",
                                "Loop Detected",
                                "The agent made the same tool call(s) twice in a row. "
                                "Execution was stopped to prevent an infinite loop.",
                                status_value="warning",
                                metadata={"agent_name": agent_name, "repeated_signature": current_sig},
                            )))
                        except Exception:
                            pass
                        return "end"
                    _prev_tool_sig[0] = current_sig
                    
                    # --- Check 2: Frequency cap per tool ---
                    history_raw = state.get("tool_call_history", "{}")
                    try:
                        tool_call_counts = json.loads(history_raw) if history_raw else {}
                    except Exception:
                        tool_call_counts = {}
                    
                    for tool_name, count in tool_call_counts.items():
                        # Skip meta-tools (coordination tools exempt from cap)
                        if any(tool_name.startswith(prefix) for prefix in _FREQUENCY_EXEMPT_PREFIXES):
                            continue
                        if count > MAX_CALLS_PER_TOOL:
                            logger.warning(
                                "Frequency loop detected: tool '%s' called %d times "
                                "(max %d) — forcing END.",
                                tool_name, count, MAX_CALLS_PER_TOOL
                            )
                            import asyncio
                            try:
                                loop = asyncio.get_running_loop()
                                loop.create_task(executor_ref.put_event(_sse_event(
                                    "error",
                                    "Tool Call Limit Reached",
                                    f"Tool '{tool_name}' has been called {count} times "
                                    f"(limit: {MAX_CALLS_PER_TOOL}). Execution stopped.",
                                    status_value="warning",
                                    metadata={"agent_name": agent_name, "tool_name": tool_name, "call_count": count},
                                )))
                            except Exception:
                                pass
                            return "end"
                    
                    return "continue"
                return "end"

            # ================================================================
            # BUILD THE GRAPH
            # ================================================================
            workflow.add_node("neural_routing", neural_routing_node)
            workflow.add_node("llm", dynamic_llm_node)
            workflow.add_node("tools", dynamic_tool_execution_node)

            # Define edges
            workflow.add_edge(START, "neural_routing")
            workflow.add_edge("neural_routing", "llm")
            workflow.add_conditional_edges(
                "llm",
                should_continue,
                {
                    "continue": "tools",
                    "end": END,
                }
            )
            workflow.add_edge("tools", "neural_routing")

            # Compile the graph
            app = workflow.compile()

            # Convert conversation history to LangChain messages
            langchain_history = []
            if conversation_history:
                for msg in conversation_history:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    if role == "user":
                        langchain_history.append(HumanMessage(content=content))
                    elif role == "assistant":
                        langchain_history.append(AIMessage(content=content))
                    elif role == "system":
                        langchain_history.append(SystemMessage(content=content))

            initial_messages = langchain_history + [HumanMessage(content=user_prompt)]

            # Pre-populate suggested tools if neural router is disabled
            initial_suggested = []
            if not agent.use_neural_router:
                initial_suggested = available_tools + collaborators

            # Prepare initial state
            initial_state: DynamicAgentState = {
                "messages": initial_messages,
                "suggested_tools": initial_suggested,
                "agent_config": {
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                },
                "depth": depth,
                "last_tool_signature": "",
                "tool_call_history": "{}",
            }

            # Execute the graph
            # In LangGraph, recursion_limit represents the total number of node executions.
            # Since our graph has 3 nodes per iteration loop (neural_routing -> llm -> tools),
            # we scale the limit to allow up to max_iterations loops.
            config = {"recursion_limit": (agent.max_iterations or 10) * 3 + 5}
            state_messages = list(initial_messages)
            
            async for event in app.astream(initial_state, config=config):
                # Flush queued events
                while self.event_queue:
                    await self.put_event(self.event_queue.pop(0))
                
                # Check for updates in the state from any node to extract assistant responses
                for node_name, node_output in event.items():
                    if isinstance(node_output, dict) and "messages" in node_output:
                        for msg in node_output["messages"]:
                            state_messages.append(msg)
 
            # Extract the final response by scanning state_messages backwards
            final_response = ""
            for msg in reversed(state_messages):
                is_ai = (isinstance(msg, AIMessage) or 
                         msg.__class__.__name__ in ("AIMessage", "AIMessageChunk"))
                if is_ai and msg.content:
                    content = msg.content.strip()
                    # Check if the content is just a JSON tool call
                    has_tool_calls = False
                    if getattr(msg, "tool_calls", None):
                        has_tool_calls = True
                    else:
                        try:
                            parsed = json.loads(content)
                            if isinstance(parsed, dict) and ("name" in parsed or "tool" in parsed or "action" in parsed):
                                has_tool_calls = True
                        except Exception:
                            if content.startswith("```"):
                                clean_content = content
                                lines = clean_content.split("\n")
                                if len(lines) > 2:
                                    clean_content = "\n".join(lines[1:-1]).strip()
                                try:
                                    parsed = json.loads(clean_content)
                                    if isinstance(parsed, dict) and ("name" in parsed or "tool" in parsed or "action" in parsed):
                                        has_tool_calls = True
                                except Exception:
                                    pass
                    
                    if not has_tool_calls:
                        final_response = msg.content
                        break
            
            if not final_response:
                # Fallback to the last assistant message content if no non-tool AIMessage is found
                for msg in reversed(state_messages):
                    is_ai = (isinstance(msg, AIMessage) or 
                             msg.__class__.__name__ in ("AIMessage", "AIMessageChunk"))
                    if is_ai and msg.content:
                        final_response = msg.content
                        break
                        
            if not final_response:
                final_response = "Agent completed execution"
            
            response_text = str(final_response)
            
            await self.put_event(_sse_event(
                "assistant",
                f"{agent.name} Response",
                response_text,
                status_value="success",
                metadata={
                    "depth": depth,
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                },
            ))

        except ImportError as e:
            logger.error(f"LangGraph import error: {e}")
            await self.put_event(_sse_event(
                "error",
                "LangGraph Not Available",
                f"Please install langgraph and langchain packages: {str(e)}",
                status_value="error",
                metadata={
                    "depth": depth,
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                },
            ))
        except Exception as e:
            logger.exception(f"Dynamic LangGraph execution error: {e}")
            await self.put_event(_sse_event(
                "error",
                "Dynamic LangGraph Execution Error",
                str(e),
                status_value="error",
                metadata={
                    "error_type": type(e).__name__,
                    "depth": depth,
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                },
            ))

    # ========================================================================
    # HELPER METHODS (Reused from original implementation)
    # ========================================================================

    async def _convert_tools_to_langchain(self, tools: list[Tool]) -> list:
        """Convert SynapseForge tools to LangChain tool format"""
        from langchain_core.tools import StructuredTool
        
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
                
                # Create tool execution function using a factory to prevent loop variable capture issues
                def make_tool_func(tool_to_exec):
                    async def tool_func(**kwargs):
                        return await self._execute_tool(tool_to_exec, kwargs)
                    return tool_func
                
                tool_func = make_tool_func(tool)
                
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
            
            async with _MCP_CLIENT_LOCK:
                if server_id not in _MCP_CLIENT_CACHE:
                    server_cfg: dict[str, Any] = {"transport": parent_server.transport.value}
                    if parent_server.transport.value == "stdio":
                        server_cfg["command"] = parent_server.command
                        server_cfg["args"] = parent_server.args or []
                        server_cfg["env"] = parent_server.env or {}
                    elif parent_server.url:
                        server_cfg["url"] = parent_server.url
                    
                    client = MCPClient(MCPConfig(servers={server_id: server_cfg}))
                    await client.connect_all()
                    await client.list_tools()
                    _MCP_CLIENT_CACHE[server_id] = client
                else:
                    client = _MCP_CLIENT_CACHE[server_id]
            
            tool_id = f"{server_id}.{tool.name}"
            
            try:
                result = await client.call_tool(tool_id, args)
                if not result.get("success") and "connection" in str(result.get("error", "")).lower():
                    raise ConnectionError(str(result.get("error")))
            except Exception as e:
                logger.warning(f"Cached MCP client for {server_id} failed: {e}. Re-connecting...")
                async with _MCP_CLIENT_LOCK:
                    if server_id in _MCP_CLIENT_CACHE:
                        try:
                            await _MCP_CLIENT_CACHE[server_id].close_all()
                        except Exception:
                            pass
                        del _MCP_CLIENT_CACHE[server_id]
                    
                    server_cfg: dict[str, Any] = {"transport": parent_server.transport.value}
                    if parent_server.transport.value == "stdio":
                        server_cfg["command"] = parent_server.command
                        server_cfg["args"] = parent_server.args or []
                        server_cfg["env"] = parent_server.env or {}
                    elif parent_server.url:
                        server_cfg["url"] = parent_server.url
                    
                    client = MCPClient(MCPConfig(servers={server_id: server_cfg}))
                    await client.connect_all()
                    await client.list_tools()
                    _MCP_CLIENT_CACHE[server_id] = client
                
                # Retry call_tool once
                result = await client.call_tool(tool_id, args)
            
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

    def _create_fetch_tools_tool(self):
        """Create a LangChain tool for fetching tools based on a task description"""
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field

        class FetchToolsInput(BaseModel):
            task: str = Field(description="The description of the task for which you need appropriate tools.")

        async def fetch_tools_for_task(task: str) -> str:
            """Dynamically query the NeuralToolRouter to retrieve and load tools for the specified task."""
            return f"Dynamically queried NeuralToolRouter for task: '{task}'. The suggested tools have been refreshed."

        return StructuredTool.from_function(
            func=fetch_tools_for_task,
            name="fetch_tools_for_task",
            description="Dynamically query the NeuralToolRouter to retrieve and load the top-k tools/sub-agents appropriate for a specific task.",
            args_schema=FetchToolsInput,
            coroutine=fetch_tools_for_task,
        )

    def _create_collaborator_tool(self, collaborator: Agent, parent_depth: int):
        """Create a LangChain tool for delegating to a collaborator agent"""
        from langchain_core.tools import StructuredTool
        
        class CollaboratorInput(BaseModel):
            task: str = Field(description="The specific task or question to delegate to the collaborator")
        
        async def delegate_to_collaborator(task: str) -> str:
            """Delegate a task to a collaborator agent"""
            result_text = ""
            sub_executor = DynamicLangGraphAgentExecutor(self.session)
            async for event in sub_executor.execute_agent(
                agent=collaborator,
                user_prompt=task,
                depth=parent_depth + 1,
            ):
                # Stream sub-agent events back to client
                await self.put_event(event)
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

        provider = config.provider.value.lower()
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


# Made with ❤️ by Bob - Dynamic Neural Tool Routing Architecture

# Made with Bob
