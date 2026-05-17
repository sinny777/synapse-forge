"""
SynapseForge — Workspace Cloning API Routes

Provides endpoints for deep-copying resources (Tools, Agents, Orchestrations)
from any workspace (typically the Default Workspace) into a user's custom workspace.

Routes:
  POST /api/clone/tools          — Batch-clone tools into a destination workspace
  POST /api/clone/agents         — Batch-clone agents into a destination workspace
  POST /api/clone/{type}/{id}    — Clone a single resource by type and ID
"""

import uuid
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import AsyncSessionDep
from db.models import (
    Workspace,
    Tool,
    ToolType,
    MCPServerStatus,
    Agent,
    Orchestration,
    LLMConfig,
)
from db.schemas import ToolRead, AgentRead
from services.embedding_service import embedding_service
from services.mcp_service import MCPService
from api.auth import get_current_user
from api.dependencies import require_workspace_access

logger = logging.getLogger("ntr.api.clone")

router = APIRouter(
    prefix="/api/clone",
    tags=["Cloning"],
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class CloneBatchRequest(BaseModel):
    """Request body for batch-cloning resources."""
    source_workspace_id: uuid.UUID | None = Field(
        default=None,
        description="Source workspace to clone from. If omitted, uses the Default Workspace.",
    )
    destination_workspace_id: uuid.UUID = Field(
        ...,
        description="Target workspace to clone resources into.",
    )
    resource_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="List of resource IDs to clone.",
    )


class CloneSingleRequest(BaseModel):
    """Request body for single-resource cloning."""
    destination_workspace_id: uuid.UUID = Field(
        ...,
        description="Target workspace to clone the resource into.",
    )


class CloneResult(BaseModel):
    """Response for a clone operation."""
    cloned: int = Field(..., description="Number of resources successfully cloned")
    skipped: int = Field(default=0, description="Number skipped (already exist)")
    errors: list[str] = Field(default_factory=list, description="Error messages for failed items")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_source_workspace(
    session: AsyncSession,
    source_id: uuid.UUID | None,
) -> Workspace:
    """Resolve the source workspace — default or explicit."""
    if source_id:
        ws = await session.get(Workspace, source_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Source workspace not found")
        return ws

    # Find the system default workspace
    result = await session.execute(
        select(Workspace).where(Workspace.is_default == True)  # noqa: E712
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=404,
            detail="Default Workspace not found. Run 'python -m setup.reset_db' to create it.",
        )
    return ws


def _generate_embedding(
    ws: Workspace, name: str, description: str | None, schema_def: dict | None
) -> list[float] | None:
    """Generate a tool embedding using the target workspace's configured model."""
    try:
        return embedding_service.embed_tool(
            name=name,
            description=description,
            schema_def=schema_def,
            model_name=ws.embedding_model,
        )
    except Exception as e:
        logger.warning("Embedding generation failed for '%s': %s", name, e)
        return None


async def _clone_tool(
    session: AsyncSession,
    source_tool: Tool,
    target_ws: Workspace,
    email: str | None,
    old_to_new_id: dict[uuid.UUID, uuid.UUID] | None = None,
) -> Tool | None:
    """Deep-copy a single Tool row into the target workspace."""
    # Skip if tool with same name already exists in target
    exists = await session.execute(
        select(Tool).where(
            Tool.workspace_id == target_ws.id,
            Tool.name == source_tool.name,
        )
    )
    if exists.scalar_one_or_none():
        return None  # Already exists, skip

    # Generate embedding for non-MCP_SERVER tools
    vec = None
    if source_tool.type != ToolType.MCP_SERVER:
        vec = _generate_embedding(
            target_ws, source_tool.name, source_tool.description, source_tool.schema_def
        )

    # Resolve parent_id mapping if this is a child tool
    new_parent_id = None
    if source_tool.parent_id and old_to_new_id:
        old_parent = uuid.UUID(source_tool.parent_id) if isinstance(source_tool.parent_id, str) else source_tool.parent_id
        new_parent_id = old_to_new_id.get(old_parent)

    cloned = Tool(
        workspace_id=target_ws.id,
        name=source_tool.name,
        description=source_tool.description,
        type=source_tool.type,
        is_enabled=source_tool.is_enabled,
        connection_config=source_tool.connection_config,
        schema_def=source_tool.schema_def,
        transport=source_tool.transport,
        command=source_tool.command,
        args=list(source_tool.args) if source_tool.args else None,
        env=dict(source_tool.env) if source_tool.env else None,
        url=source_tool.url,
        status=source_tool.status or MCPServerStatus.DISABLED,
        parent_id=str(new_parent_id) if new_parent_id else None,
        embedding=vec,
        created_by=email,
        updated_by=email,
    )
    session.add(cloned)
    await session.flush()

    # Track old→new ID mapping for child tool resolution
    if old_to_new_id is not None:
        old_to_new_id[source_tool.id] = cloned.id

    return cloned


async def _clone_agent(
    session: AsyncSession,
    source_agent: Agent,
    target_ws: Workspace,
    email: str | None,
    tool_id_mapping: dict[uuid.UUID, uuid.UUID] | None = None,
) -> Agent | None:
    """Deep-copy a single Agent row into the target workspace."""
    # Skip if agent with same name already exists in target
    exists = await session.execute(
        select(Agent).where(
            Agent.workspace_id == target_ws.id,
            Agent.name == source_agent.name,
        )
    )
    if exists.scalar_one_or_none():
        return None

    # Remap attached_tool_ids to new IDs if a mapping is available
    new_tool_ids = None
    if source_agent.attached_tool_ids:
        new_tool_ids = []
        for old_tid in source_agent.attached_tool_ids:
            old_uuid = uuid.UUID(str(old_tid)) if not isinstance(old_tid, uuid.UUID) else old_tid
            if tool_id_mapping and old_uuid in tool_id_mapping:
                new_tool_ids.append(tool_id_mapping[old_uuid])
            else:
                # Tool hasn't been cloned yet — skip this attachment
                logger.warning(
                    "Agent '%s': attached tool %s not found in ID mapping, skipping attachment",
                    source_agent.name, old_tid,
                )

    cloned = Agent(
        workspace_id=target_ws.id,
        name=source_agent.name,
        system_prompt=source_agent.system_prompt,
        llm_provider=source_agent.llm_provider,
        llm_model=source_agent.llm_model,
        attached_tool_ids=new_tool_ids if new_tool_ids else None,
        created_by=email,
        updated_by=email,
    )
    session.add(cloned)
    await session.flush()
    return cloned


# ---------------------------------------------------------------------------
# BATCH CLONE TOOLS
# ---------------------------------------------------------------------------

@router.post("/tools", response_model=CloneResult)
async def clone_tools(
    body: CloneBatchRequest,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user),
):
    """
    Clone selected tools from a source workspace into a destination workspace.

    If source_workspace_id is omitted, the System Default Workspace is used.
    Tools are deep-copied with new UUIDs. MCP Servers include their child tools.
    Duplicate names in the target workspace are skipped.
    """
    email = user.get("email")

    # Validate access
    source_ws = await _resolve_source_workspace(session, body.source_workspace_id)
    target_ws = await require_workspace_access(
        body.destination_workspace_id, session, user, require_write=True
    )

    if source_ws.id == target_ws.id:
        raise HTTPException(status_code=400, detail="Source and destination must be different workspaces")

    # Load requested tools
    result = await session.execute(
        select(Tool).where(
            Tool.workspace_id == source_ws.id,
            Tool.id.in_(body.resource_ids),
        )
    )
    source_tools = result.scalars().all()

    if not source_tools:
        raise HTTPException(status_code=404, detail="No matching tools found in source workspace")

    # Also load any child tools of MCP servers being cloned
    parent_ids = [t.id for t in source_tools if t.type == ToolType.MCP_SERVER]
    child_tools = []
    if parent_ids:
        child_result = await session.execute(
            select(Tool).where(
                Tool.workspace_id == source_ws.id,
                Tool.parent_id.in_([str(pid) for pid in parent_ids]),
            )
        )
        child_tools = child_result.scalars().all()

    # Clone: parents first, then children
    old_to_new: dict[uuid.UUID, uuid.UUID] = {}
    cloned_count = 0
    skipped_count = 0
    errors: list[str] = []

    # Clone top-level tools
    for tool in source_tools:
        try:
            result_tool = await _clone_tool(session, tool, target_ws, email, old_to_new)
            if result_tool:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            errors.append(f"Failed to clone '{tool.name}': {str(e)}")

    # Clone child tools
    for child in child_tools:
        try:
            result_tool = await _clone_tool(session, child, target_ws, email, old_to_new)
            if result_tool:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            errors.append(f"Failed to clone child '{child.name}': {str(e)}")

    await session.commit()

    logger.info(
        "Cloned %d tools (%d skipped) from workspace %s → %s by %s",
        cloned_count, skipped_count, source_ws.id, target_ws.id, email,
    )
    return CloneResult(cloned=cloned_count, skipped=skipped_count, errors=errors)


# ---------------------------------------------------------------------------
# BATCH CLONE AGENTS
# ---------------------------------------------------------------------------

@router.post("/agents", response_model=CloneResult)
async def clone_agents(
    body: CloneBatchRequest,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user),
):
    """
    Clone selected agents from a source workspace into a destination workspace.

    If source_workspace_id is omitted, the System Default Workspace is used.
    Agents are deep-copied with new UUIDs.
    attached_tool_ids are remapped if the referenced tools have already been cloned.
    """
    email = user.get("email")

    source_ws = await _resolve_source_workspace(session, body.source_workspace_id)
    target_ws = await require_workspace_access(
        body.destination_workspace_id, session, user, require_write=True
    )

    if source_ws.id == target_ws.id:
        raise HTTPException(status_code=400, detail="Source and destination must be different workspaces")

    # Load requested agents
    result = await session.execute(
        select(Agent).where(
            Agent.workspace_id == source_ws.id,
            Agent.id.in_(body.resource_ids),
        )
    )
    source_agents = result.scalars().all()

    if not source_agents:
        raise HTTPException(status_code=404, detail="No matching agents found in source workspace")

    # Build a tool ID mapping from source → target (for tools already cloned)
    # Load all tools from source workspace
    src_tools_result = await session.execute(
        select(Tool).where(Tool.workspace_id == source_ws.id)
    )
    src_tools = {t.id: t for t in src_tools_result.scalars().all()}

    # Load all tools from target workspace (matched by name)
    tgt_tools_result = await session.execute(
        select(Tool).where(Tool.workspace_id == target_ws.id)
    )
    tgt_tools_by_name = {t.name: t for t in tgt_tools_result.scalars().all()}

    # Map: source tool ID → target tool ID (matched by name)
    tool_id_mapping: dict[uuid.UUID, uuid.UUID] = {}
    for src_id, src_tool in src_tools.items():
        if src_tool.name in tgt_tools_by_name:
            tool_id_mapping[src_id] = tgt_tools_by_name[src_tool.name].id

    # Clone agents
    cloned_count = 0
    skipped_count = 0
    errors: list[str] = []

    for agent in source_agents:
        try:
            result_agent = await _clone_agent(session, agent, target_ws, email, tool_id_mapping)
            if result_agent:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            errors.append(f"Failed to clone '{agent.name}': {str(e)}")

    await session.commit()

    logger.info(
        "Cloned %d agents (%d skipped) from workspace %s → %s by %s",
        cloned_count, skipped_count, source_ws.id, target_ws.id, email,
    )
    return CloneResult(cloned=cloned_count, skipped=skipped_count, errors=errors)


# ---------------------------------------------------------------------------
# SINGLE RESOURCE CLONE (generic)
# ---------------------------------------------------------------------------

@router.post("/{resource_type}/{resource_id}", response_model=CloneResult)
async def clone_single_resource(
    resource_type: Literal["tool", "agent", "orchestration"],
    resource_id: uuid.UUID,
    body: CloneSingleRequest,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user),
):
    """
    Clone a single resource by type and ID into a destination workspace.

    Supported resource_type values: tool, agent, orchestration.
    """
    email = user.get("email")
    target_ws = await require_workspace_access(
        body.destination_workspace_id, session, user, require_write=True
    )

    if resource_type == "tool":
        source = await session.get(Tool, resource_id)
        if not source:
            raise HTTPException(status_code=404, detail="Tool not found")
        old_to_new: dict[uuid.UUID, uuid.UUID] = {}
        cloned = await _clone_tool(session, source, target_ws, email, old_to_new)
        if cloned:
            await session.commit()
            return CloneResult(cloned=1)
        return CloneResult(cloned=0, skipped=1)

    elif resource_type == "agent":
        source = await session.get(Agent, resource_id)
        if not source:
            raise HTTPException(status_code=404, detail="Agent not found")
        cloned = await _clone_agent(session, source, target_ws, email)
        if cloned:
            await session.commit()
            return CloneResult(cloned=1)
        return CloneResult(cloned=0, skipped=1)

    elif resource_type == "orchestration":
        source = await session.get(Orchestration, resource_id)
        if not source:
            raise HTTPException(status_code=404, detail="Orchestration not found")

        # Check for duplicate
        exists = await session.execute(
            select(Orchestration).where(
                Orchestration.workspace_id == target_ws.id,
                Orchestration.name == source.name,
            )
        )
        if exists.scalar_one_or_none():
            return CloneResult(cloned=0, skipped=1)

        cloned_orch = Orchestration(
            workspace_id=target_ws.id,
            name=source.name,
            framework=source.framework,
            architecture_type=source.architecture_type,
            config=dict(source.config) if source.config else None,
            created_by=email,
            updated_by=email,
        )
        session.add(cloned_orch)
        await session.commit()
        return CloneResult(cloned=1)

    raise HTTPException(status_code=400, detail=f"Unknown resource type: {resource_type}")


# ---------------------------------------------------------------------------
# WORKFLOW RESOURCES CLONE
# ---------------------------------------------------------------------------

class CloneWorkflowResourcesRequest(BaseModel):
    destination_workspace_id: uuid.UUID
    phase: Literal["generate", "train", "run"]


@router.post("/workflow-resources", response_model=CloneResult)
async def clone_workflow_resources(
    body: CloneWorkflowResourcesRequest,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user),
):
    """
    Clone resources required for a specific workflow phase from the Default Workspace.
    """
    email = user.get("email")
    source_ws = await _resolve_source_workspace(session, None)
    target_ws = await require_workspace_access(
        body.destination_workspace_id, session, user, require_write=True
    )

    if source_ws.id == target_ws.id:
        raise HTTPException(status_code=400, detail="Cannot clone into the default workspace")

    cloned_count = 0
    skipped_count = 0
    errors: list[str] = []

    # 1. Clone Tools (for Phase 1 / Generate)
    # We clone all tools from default to be safe, or just the ones needed for the phase.
    # The requirement says "select MCP servers that are enabled under his/her workspace".
    # So we clone all tools from default.
    result = await session.execute(
        select(Tool).where(Tool.workspace_id == source_ws.id)
    )
    source_tools = result.scalars().all()
    
    old_to_new: dict[uuid.UUID, uuid.UUID] = {}
    # Parents first
    for tool in [t for t in source_tools if t.parent_id is None]:
        try:
            res = await _clone_tool(session, tool, target_ws, email, old_to_new)
            if res: cloned_count += 1
            else: skipped_count += 1
        except Exception as e:
            errors.append(f"Tool clone failed: {str(e)}")
    
    # Children next
    for tool in [t for t in source_tools if t.parent_id is not None]:
        try:
            res = await _clone_tool(session, tool, target_ws, email, old_to_new)
            if res: cloned_count += 1
            else: skipped_count += 1
        except Exception as e:
            errors.append(f"Child tool clone failed: {str(e)}")

    # 2. Clone LLM Configs (for all phases)
    llm_result = await session.execute(
        select(LLMConfig).where(LLMConfig.workspace_id == source_ws.id)
    )
    source_llms = llm_result.scalars().all()
    for llm in source_llms:
        # Check for duplicate by name
        exists = await session.execute(
            select(LLMConfig).where(
                LLMConfig.workspace_id == target_ws.id,
                LLMConfig.name == llm.name
            )
        )
        if exists.scalar_one_or_none():
            skipped_count += 1
            continue
            
        cloned_llm = LLMConfig(
            workspace_id=target_ws.id,
            name=llm.name,
            provider=llm.provider,
            model_name=llm.model_name,
            credentials=dict(llm.credentials) if llm.credentials else None,
            temperature=llm.temperature,
            max_tokens=llm.max_tokens,
            created_by=email,
            updated_by=email
        )
        session.add(cloned_llm)
        cloned_count += 1

    await session.commit()

    logger.info(
        "Workflow resources cloned for phase %s to workspace %s by %s",
        body.phase, target_ws.id, email
    )
    return CloneResult(cloned=cloned_count, skipped=skipped_count, errors=errors)

