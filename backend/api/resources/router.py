"""
api.resources.router
~~~~~~~~~~~~~~~~~~~~
Route handlers for the resources domain: Tools, Agents, and Orchestrations.

All routes are registered under a single APIRouter named `router` that is
included by api/__init__.py.  URL prefixes are identical to the previous
flat-package layout.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.auth import get_current_user
from api.common.utils import sse_event
from api.dependencies import require_workspace_access
from api.resources.helpers import (
    agent_from_doc,
    build_agent_read_payload,
    get_workspace,
    load_agent_llm_config,
    load_agent_tools,
    load_agent_with_workspace_guard,
    load_collaborator_agents,
    mask_tool_secrets,
    orchestration_from_doc,
    tool_from_doc,
    validate_collaborators,
)
from api.resources.service import execute_single_agent
from db.engine import get_db, prepare_document, utcnow
from db.models import Agent, Orchestration, Tool, ToolType
from db.schemas import (
    AgentCreate,
    AgentExecuteRequest,
    AgentRead,
    AgentUpdate,
    OrchestrationCreate,
    OrchestrationRead,
    OrchestrationUpdate,
    ToolCreate,
    ToolRead,
    ToolUpdate,
)
from services.embedding_service import embedding_service
from services.mcp_service import MCPService

logger = logging.getLogger("ntr.api.resources")

router = APIRouter()


# ===========================================================================
# Tools  —  /api/workspaces/{workspace_id}/tools
# ===========================================================================

_tools_router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/tools",
    tags=["Tools"],
)


def _generate_embedding(ws, name: str, description: str | None, schema_def: dict | None) -> list[float]:
    return embedding_service.embed_tool(
        name=name,
        description=description,
        schema_def=schema_def,
        model_name=ws.embedding_model,
    )


@_tools_router.get("", response_model=list[ToolRead])
async def list_tools(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    category: str | None = None,
    sub_category: str | None = None,
    tags: str | None = None,
    search: str | None = None,
):
    """List all tools in a workspace with optional filtering."""
    await get_workspace(workspace_id, db)
    query: dict = {"workspace_id": str(workspace_id)}

    if category:
        query["category"] = category
    if sub_category:
        query["sub_category"] = sub_category
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            query["tags"] = {"$all": tag_list}

    cursor = db.tools.find(query).sort("created_at", -1)
    tools: list[ToolRead] = []
    async for document in cursor:
        tool = tool_from_doc(document)
        if tool is None:
            continue
        if search:
            search_lower = search.lower()
            if not any(
                search_lower in (field or "").lower()
                for field in [tool.name, tool.description, tool.category, tool.sub_category]
            ) and not any(search_lower in (tag or "").lower() for tag in (tool.tags or [])):
                continue
        tools.append(ToolRead.model_validate(mask_tool_secrets(tool)))
    return tools


@_tools_router.post("", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
async def create_tool(
    workspace_id: uuid.UUID,
    body: ToolCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Register a new tool or MCP server."""
    ws = await require_workspace_access(workspace_id, db, user, require_write=True)
    email = user.get("email")

    vec = None
    if body.type != ToolType.MCP_SERVER:
        vec = _generate_embedding(ws, body.name, body.description, body.schema_def)

    tool = Tool(
        workspace_id=str(workspace_id),
        name=body.name,
        description=body.description,
        type=ToolType(body.type.value) if hasattr(body.type, "value") else ToolType(body.type),
        is_enabled=body.is_enabled,
        connection_config=body.connection_config,
        schema_def=body.schema_def,
        transport=(None if body.transport is None else body.transport.value),
        command=body.command,
        args=body.args,
        env=body.env,
        url=body.url,
        status=(body.status.value if hasattr(body.status, "value") else body.status),
        parent_id=str(body.parent_id) if body.parent_id else None,
        embedding=vec,
        category=body.category,
        sub_category=body.sub_category,
        tags=body.tags,
        created_by=email,
        updated_by=email,
    )

    await db.tools.insert_one(prepare_document(tool.model_dump()))

    if tool.type == ToolType.MCP_SERVER:
        try:
            await MCPService.discover_tools(db, workspace_id, tool)
        except Exception as exc:
            logger.warning("Initial tool discovery failed for %s: %s", tool.name, exc)

    return ToolRead.model_validate(mask_tool_secrets(tool))


@_tools_router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a single tool by ID."""
    await get_workspace(workspace_id, db)
    tool = tool_from_doc(await db.tools.find_one({"_id": str(tool_id)}))
    if tool is None or tool.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Tool not found")
    return ToolRead.model_validate(mask_tool_secrets(tool))


@_tools_router.put("/{tool_id}", response_model=ToolRead)
async def update_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: ToolUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update a tool or MCP server configuration."""
    ws = await require_workspace_access(workspace_id, db, user, require_write=True)
    tool = tool_from_doc(await db.tools.find_one({"_id": str(tool_id)}))
    if tool is None or tool.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Tool not found")

    update_data = body.model_dump(exclude_unset=True)

    meta_fields = {"name", "description", "schema_def"}
    needs_reembed = any(k in update_data for k in meta_fields) and tool.type != ToolType.MCP_SERVER

    discovery_fields = {"transport", "command", "args", "env", "url"}
    needs_rediscovery = any(k in update_data for k in discovery_fields) and tool.type == ToolType.MCP_SERVER

    for field, value in update_data.items():
        if field == "parent_id" and value is not None:
            setattr(tool, field, str(value))
        elif field in {"transport", "status"} and value is not None and hasattr(value, "value"):
            setattr(tool, field, value.value)
        else:
            setattr(tool, field, value)

    tool.updated_by = user.get("email")
    tool.updated_at = utcnow()

    if "is_enabled" in update_data and tool.type == ToolType.MCP_SERVER:
        await db.tools.update_many(
            {"parent_id": str(tool_id)},
            {"$set": {"is_enabled": update_data["is_enabled"], "updated_at": utcnow(), "updated_by": user.get("email")}},
        )

    if needs_reembed:
        tool.embedding = _generate_embedding(ws, tool.name, tool.description, tool.schema_def)
        logger.info("Re-embedded tool %s", tool_id)

    await db.tools.replace_one({"_id": str(tool_id)}, prepare_document(tool.model_dump()))

    if needs_rediscovery:
        try:
            await MCPService.discover_tools(db, workspace_id, tool)
        except Exception as exc:
            logger.warning("Re-discovery failed for %s: %s", tool.name, exc)

    return ToolRead.model_validate(mask_tool_secrets(tool))


@_tools_router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete a tool (cascades to children for MCP servers)."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    tool = tool_from_doc(await db.tools.find_one({"_id": str(tool_id)}))
    if tool is None or tool.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Tool not found")

    await db.tools.delete_many(
        {"$or": [{"_id": str(tool_id)}, {"parent_id": str(tool_id)}]}
    )
    logger.info("Deleted tool %s", tool_id)


@_tools_router.post("/{tool_id}/test")
async def test_tool_connection(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Test connectivity for an MCP_SERVER tool."""
    from db.models import MCPServerStatus

    await require_workspace_access(workspace_id, db, user, require_write=True)
    tool = tool_from_doc(await db.tools.find_one({"_id": str(tool_id)}))
    if not tool or tool.type != ToolType.MCP_SERVER:
        raise HTTPException(status_code=400, detail="Not an MCP server")

    if tool.transport is None:
        raise HTTPException(status_code=400, detail="MCP server transport is not configured")

    try:
        from tool_router.config import MCPConfig
        from tool_router.mcp_client import MCPClient

        server_config: dict = {"transport": tool.transport.value}
        if tool.transport.value == "stdio":
            server_config["command"] = tool.command or ""
            server_config["args"] = tool.args or []
            server_config["env"] = tool.env or {}
        else:
            if not tool.url:
                raise HTTPException(status_code=400, detail="MCP server URL is not configured")
            server_config["url"] = tool.url

        mcp_id = str(tool.id)
        client = MCPClient(MCPConfig(servers={mcp_id: server_config}))

        success = await client.connect_server(mcp_id, server_config)
        if success:
            tools = await client.list_tools(mcp_id)
            await client.close_all()
            tool.status = MCPServerStatus.ACTIVE
            tool.last_error = None
            tool.updated_by = user.get("email")
            tool.updated_at = utcnow()
            await db.tools.replace_one({"_id": str(tool_id)}, prepare_document(tool.model_dump()))
            return {"success": True, "tools_count": len(tools)}

        tool.status = MCPServerStatus.ERROR
        tool.last_error = "Failed to connect"
        tool.updated_by = user.get("email")
        tool.updated_at = utcnow()
        await db.tools.replace_one({"_id": str(tool_id)}, prepare_document(tool.model_dump()))
        return {"success": False, "error": "Connection failed"}
    except Exception as exc:
        tool.status = MCPServerStatus.ERROR
        tool.last_error = str(exc)
        tool.updated_by = user.get("email")
        tool.updated_at = utcnow()
        await db.tools.replace_one({"_id": str(tool_id)}, prepare_document(tool.model_dump()))
        return {"success": False, "error": str(exc)}


# ===========================================================================
# Agents  —  /api/workspaces/{workspace_id}/agents
# ===========================================================================

_agents_router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/agents",
    tags=["Agents"],
)


@_agents_router.get("", response_model=list[AgentRead])
async def list_agents(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    category: str | None = None,
    sub_category: str | None = None,
    tags: str | None = None,
    search: str | None = None,
):
    """List all agents in a workspace with optional filtering."""
    await get_workspace(workspace_id, db)
    query: dict = {"workspace_id": str(workspace_id)}

    if category:
        query["category"] = category
    if sub_category:
        query["sub_category"] = sub_category
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            query["tags"] = {"$all": tag_list}

    agent_docs = await db.agents.find(query).sort("created_at", -1).to_list(length=None)
    agents = [a for a in (agent_from_doc(doc) for doc in agent_docs) if a is not None]

    if search:
        search_lower = search.lower()
        agents = [
            a for a in agents
            if any(
                search_lower in (field or "").lower()
                for field in [a.name, a.description, a.category, a.sub_category]
            ) or any(search_lower in (tag or "").lower() for tag in (a.tags or []))
        ]

    return [await build_agent_read_payload(db, a) for a in agents]


@_agents_router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    workspace_id: uuid.UUID,
    body: AgentCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new agent definition in the workspace."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    email = user.get("email")

    collaborator_agent_ids = await validate_collaborators(
        db, workspace_id, body.collaborator_agent_ids
    )

    agent = Agent(
        workspace_id=str(workspace_id),
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        llm_config_id=str(body.llm_config_id) if body.llm_config_id else None,
        use_neural_router=body.use_neural_router,
        router_model_id=body.router_model_id,
        router_top_k=body.router_top_k,
        memory_type=body.memory_type,
        memory_window=body.memory_window,
        max_iterations=body.max_iterations,
        timeout_seconds=body.timeout_seconds,
        attached_tool_ids=[str(tid) for tid in body.attached_tool_ids] if body.attached_tool_ids else None,
        collaborator_agent_ids=(
            [str(aid) for aid in collaborator_agent_ids] if collaborator_agent_ids else None
        ),
        category=body.category,
        sub_category=body.sub_category,
        tags=body.tags,
        created_by=email,
        updated_by=email,
    )
    await db.agents.insert_one(prepare_document(agent.model_dump()))
    logger.info("Created agent %s (%s) in workspace %s", agent.id, agent.name, workspace_id)
    return await build_agent_read_payload(db, agent)


@_agents_router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a single agent by ID."""
    await get_workspace(workspace_id, db)
    agent = agent_from_doc(await db.agents.find_one({"_id": str(agent_id)}))
    if agent is None or agent.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return await build_agent_read_payload(db, agent)


@_agents_router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update an agent definition (partial update)."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    agent = agent_from_doc(await db.agents.find_one({"_id": str(agent_id)}))
    if agent is None or agent.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)

    if "collaborator_agent_ids" in update_data:
        validated = await validate_collaborators(
            db, workspace_id, update_data["collaborator_agent_ids"],
            agent_id=uuid.UUID(str(agent.id)),
        )
        update_data["collaborator_agent_ids"] = (
            [str(cid) for cid in validated] if validated is not None else None
        )

    if "llm_config_id" in update_data and update_data["llm_config_id"] is not None:
        update_data["llm_config_id"] = str(update_data["llm_config_id"])

    if "attached_tool_ids" in update_data and update_data["attached_tool_ids"] is not None:
        update_data["attached_tool_ids"] = [str(tid) for tid in update_data["attached_tool_ids"]]

    for field, value in update_data.items():
        setattr(agent, field, value)

    agent.updated_by = user.get("email")
    agent.updated_at = datetime.now(timezone.utc)

    await db.agents.replace_one({"_id": str(agent_id)}, prepare_document(agent.model_dump()))
    logger.info("Updated agent %s", agent_id)
    return await build_agent_read_payload(db, agent)


@_agents_router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete an agent from the workspace."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    agent = agent_from_doc(await db.agents.find_one({"_id": str(agent_id)}))
    if agent is None or agent.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Agent not found")

    await db.agents.delete_one({"_id": str(agent_id)})
    logger.info("Deleted agent %s from workspace %s", agent_id, workspace_id)


@_agents_router.post("/{agent_id}/execute")
async def execute_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentExecuteRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Execute a workspace agent with SSE streaming.

    Supports multi-turn conversations via session_id parameter.
    """
    await require_workspace_access(workspace_id, db, user, require_write=False)
    agent = await load_agent_with_workspace_guard(db, workspace_id, agent_id)

    session_id = body.session_id or str(uuid.uuid4())

    from db.redis_pool import get_redis_pool
    import redis.asyncio as aioredis

    redis_pool = get_redis_pool()
    redis_client = aioredis.Redis(connection_pool=redis_pool)

    async def event_stream():
        try:
            from services.conversation_service import ConversationService

            conv_service = ConversationService(redis_client)
            await conv_service.get_or_create_session(session_id, uuid.UUID(str(agent.id)))

            history = await conv_service.get_history(
                session_id=session_id,
                limit=agent.memory_window or 10,
                memory_type=agent.memory_type or "buffer",
            )

            yield sse_event(
                "thought",
                "User Prompt Received",
                body.user_prompt,
                status_value="success",
                metadata={
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "workspace_id": str(workspace_id),
                    "session_id": session_id,
                    "history_length": len(history),
                },
            )

            from services.langgraph_dynamic_agent_executor import DynamicLangGraphAgentExecutor

            executor = DynamicLangGraphAgentExecutor(db)
            assistant_response = ""

            async for event in executor.execute_agent(
                agent=agent,
                user_prompt=body.user_prompt,
                conversation_history=history,
                depth=0,
                router_top_k_override=body.top_k,
            ):
                yield event
                event_data = json.loads(event.replace("data: ", "").strip())
                if event_data.get("type") == "assistant":
                    assistant_response = event_data.get("detail", "")

            await conv_service.add_message(session_id=session_id, role="user", content=body.user_prompt)
            if assistant_response:
                await conv_service.add_message(session_id=session_id, role="assistant", content=assistant_response)

            yield sse_event(
                "complete",
                "Agent Execution Complete",
                "Streaming finished",
                status_value="success",
                metadata={"session_id": session_id, "agent_id": str(agent.id), "agent_name": agent.name},
            )

        except Exception as exc:
            logger.error("Agent execution error: %s", exc, exc_info=True)
            yield sse_event("error", "Agent Execution Failed", str(exc), status_value="error")
            yield sse_event("complete", "Agent Execution Complete", "Completed with errors", status_value="error")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ===========================================================================
# Orchestrations  —  /api/workspaces/{workspace_id}/orchestrations
# ===========================================================================

_orchestrations_router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/orchestrations",
    tags=["Orchestrations"],
)


@_orchestrations_router.get("", response_model=list[OrchestrationRead])
async def list_orchestrations(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all orchestrations in a workspace."""
    await get_workspace(workspace_id, db)
    cursor = db.orchestrations.find({"workspace_id": str(workspace_id)}).sort("created_at", -1)

    orchestrations: list[OrchestrationRead] = []
    async for document in cursor:
        orch = orchestration_from_doc(document)
        if orch is not None:
            orchestrations.append(OrchestrationRead.model_validate(orch))
    return orchestrations


@_orchestrations_router.post("", response_model=OrchestrationRead, status_code=status.HTTP_201_CREATED)
async def create_orchestration(
    workspace_id: uuid.UUID,
    body: OrchestrationCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new orchestration definition in the workspace."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    email = user.get("email")

    orch = Orchestration(
        workspace_id=str(workspace_id),
        name=body.name,
        framework=body.framework.value if hasattr(body.framework, "value") else body.framework,
        architecture_type=(
            body.architecture_type.value
            if hasattr(body.architecture_type, "value")
            else body.architecture_type
        ),
        config=body.config,
        created_by=email,
        updated_by=email,
    )
    await db.orchestrations.insert_one(prepare_document(orch.model_dump()))
    logger.info("Created orchestration %s (%s) in workspace %s", orch.id, orch.name, workspace_id)
    return OrchestrationRead.model_validate(orch)


@_orchestrations_router.get("/{orchestration_id}", response_model=OrchestrationRead)
async def get_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a single orchestration by ID."""
    await get_workspace(workspace_id, db)
    orch = orchestration_from_doc(await db.orchestrations.find_one({"_id": str(orchestration_id)}))
    if orch is None or orch.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return OrchestrationRead.model_validate(orch)


@_orchestrations_router.put("/{orchestration_id}", response_model=OrchestrationRead)
async def update_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    body: OrchestrationUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update an orchestration definition."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    orch = orchestration_from_doc(await db.orchestrations.find_one({"_id": str(orchestration_id)}))
    if orch is None or orch.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Orchestration not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in {"framework", "architecture_type"} and value is not None and hasattr(value, "value"):
            setattr(orch, field, value.value)
        else:
            setattr(orch, field, value)

    orch.updated_by = user.get("email")
    orch.updated_at = utcnow()

    await db.orchestrations.replace_one(
        {"_id": str(orchestration_id)},
        prepare_document(orch.model_dump()),
    )
    logger.info("Updated orchestration %s", orchestration_id)
    return OrchestrationRead.model_validate(orch)


@_orchestrations_router.delete("/{orchestration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete an orchestration from the workspace."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    orch = orchestration_from_doc(await db.orchestrations.find_one({"_id": str(orchestration_id)}))
    if orch is None or orch.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Orchestration not found")

    await db.orchestrations.delete_one({"_id": str(orchestration_id)})
    logger.info("Deleted orchestration %s from workspace %s", orchestration_id, workspace_id)


# ===========================================================================
# Combine all sub-routers into the single exported `router`
# ===========================================================================

router.include_router(_tools_router)
router.include_router(_agents_router)
router.include_router(_orchestrations_router)
