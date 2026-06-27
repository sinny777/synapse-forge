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

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from db.engine import get_db, normalize_mongo_document, prepare_document
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

def _workspace_from_doc(document: dict | None) -> Workspace | None:
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return Workspace.model_validate(normalized)


def _tool_from_doc(document: dict | None) -> Tool | None:
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return Tool.model_validate(normalized)


def _agent_from_doc(document: dict | None) -> Agent | None:
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return Agent.model_validate(normalized)


def _orchestration_from_doc(document: dict | None) -> Orchestration | None:
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return Orchestration.model_validate(normalized)


def _llm_config_from_doc(document: dict | None) -> LLMConfig | None:
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return LLMConfig.model_validate(normalized)


async def _resolve_source_workspace(
    db: AsyncIOMotorDatabase,
    source_id: uuid.UUID | None,
) -> Workspace:
    """Resolve the source workspace — default or explicit."""
    if source_id:
        ws = _workspace_from_doc(await db.workspaces.find_one({"_id": str(source_id)}))
        if ws is None:
            raise HTTPException(status_code=404, detail="Source workspace not found")
        return ws

    ws = _workspace_from_doc(await db.workspaces.find_one({"is_default": True}))
    if ws is None:
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
    db: AsyncIOMotorDatabase,
    source_tool: Tool,
    target_ws: Workspace,
    email: str | None,
    old_to_new_id: dict[str, str] | None = None,
) -> Tool | None:
    """Deep-copy a single Tool document into the target workspace."""
    exists = await db.tools.find_one(
        {"workspace_id": target_ws.id, "name": source_tool.name}
    )
    if exists:
        return None

    vec = None
    if source_tool.type != ToolType.MCP_SERVER:
        vec = _generate_embedding(
            target_ws, source_tool.name, source_tool.description, source_tool.schema_def
        )

    new_parent_id = None
    if source_tool.parent_id and old_to_new_id:
        new_parent_id = old_to_new_id.get(str(source_tool.parent_id))

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
        parent_id=new_parent_id,
        embedding=vec,
        created_by=email,
        updated_by=email,
    )
    await db.tools.insert_one(prepare_document(cloned.model_dump()))

    if old_to_new_id is not None:
        old_to_new_id[str(source_tool.id)] = str(cloned.id)

    return cloned


async def _clone_agent(
    db: AsyncIOMotorDatabase,
    source_agent: Agent,
    target_ws: Workspace,
    email: str | None,
    tool_id_mapping: dict[str, str] | None = None,
) -> Agent | None:
    """Deep-copy a single Agent document into the target workspace."""
    exists = await db.agents.find_one(
        {"workspace_id": target_ws.id, "name": source_agent.name}
    )
    if exists:
        return None

    new_tool_ids = None
    if source_agent.attached_tool_ids:
        new_tool_ids = []
        for old_tid in source_agent.attached_tool_ids:
            old_id = str(old_tid)
            if tool_id_mapping and old_id in tool_id_mapping:
                new_tool_ids.append(tool_id_mapping[old_id])
            else:
                logger.warning(
                    "Agent '%s': attached tool %s not found in ID mapping, skipping attachment",
                    source_agent.name,
                    old_tid,
                )

    cloned = Agent(
        workspace_id=target_ws.id,
        name=source_agent.name,
        description=source_agent.description,
        system_prompt=source_agent.system_prompt,
        use_neural_router=source_agent.use_neural_router,
        router_top_k=source_agent.router_top_k,
        memory_type=source_agent.memory_type,
        memory_window=source_agent.memory_window,
        max_iterations=source_agent.max_iterations,
        timeout_seconds=source_agent.timeout_seconds,
        attached_tool_ids=new_tool_ids if new_tool_ids else None,
        collaborator_agent_ids=source_agent.collaborator_agent_ids,
        created_by=email,
        updated_by=email,
    )
    await db.agents.insert_one(prepare_document(cloned.model_dump()))
    return cloned


# ---------------------------------------------------------------------------
# BATCH CLONE TOOLS
# ---------------------------------------------------------------------------

@router.post("/tools", response_model=CloneResult)
async def clone_tools(
    body: CloneBatchRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
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
    source_ws = await _resolve_source_workspace(db, body.source_workspace_id)
    target_ws = await require_workspace_access(
        body.destination_workspace_id, db, user, require_write=True
    )

    if source_ws.id == target_ws.id:
        raise HTTPException(status_code=400, detail="Source and destination must be different workspaces")

    # Load requested tools
    source_tool_docs = await db.tools.find(
        {
            "workspace_id": source_ws.id,
            "_id": {"$in": [str(resource_id) for resource_id in body.resource_ids]},
        }
    ).to_list(length=None)
    source_tools = [_tool_from_doc(doc) for doc in source_tool_docs]
    source_tools = [tool for tool in source_tools if tool is not None]

    if not source_tools:
        raise HTTPException(status_code=404, detail="No matching tools found in source workspace")

    # Also load any child tools of MCP servers being cloned
    parent_ids = [tool.id for tool in source_tools if tool.type == ToolType.MCP_SERVER]
    child_tools: list[Tool] = []
    if parent_ids:
        child_tool_docs = await db.tools.find(
            {
                "workspace_id": source_ws.id,
                "parent_id": {"$in": parent_ids},
            }
        ).to_list(length=None)
        child_tools = [_tool_from_doc(doc) for doc in child_tool_docs]
        child_tools = [tool for tool in child_tools if tool is not None]

    # Clone: parents first, then children
    old_to_new: dict[str, str] = {}
    cloned_count = 0
    skipped_count = 0
    errors: list[str] = []

    # Clone top-level tools
    for tool in source_tools:
        try:
            result_tool = await _clone_tool(db, tool, target_ws, email, old_to_new)
            if result_tool:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            errors.append(f"Failed to clone '{tool.name}': {str(e)}")

    # Clone child tools
    for child in child_tools:
        try:
            result_tool = await _clone_tool(db, child, target_ws, email, old_to_new)
            if result_tool:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            errors.append(f"Failed to clone child '{child.name}': {str(e)}")

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
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Clone selected agents from a source workspace into a destination workspace.

    If source_workspace_id is omitted, the System Default Workspace is used.
    Agents are deep-copied with new UUIDs.
    attached_tool_ids are remapped if the referenced tools have already been cloned.
    """
    email = user.get("email")

    source_ws = await _resolve_source_workspace(db, body.source_workspace_id)
    target_ws = await require_workspace_access(
        body.destination_workspace_id, db, user, require_write=True
    )

    if source_ws.id == target_ws.id:
        raise HTTPException(status_code=400, detail="Source and destination must be different workspaces")

    # Load requested agents
    source_agent_docs = await db.agents.find(
        {
            "workspace_id": source_ws.id,
            "_id": {"$in": [str(resource_id) for resource_id in body.resource_ids]},
        }
    ).to_list(length=None)
    source_agents = [_agent_from_doc(doc) for doc in source_agent_docs]
    source_agents = [agent for agent in source_agents if agent is not None]

    if not source_agents:
        raise HTTPException(status_code=404, detail="No matching agents found in source workspace")

    src_tool_docs = await db.tools.find({"workspace_id": source_ws.id}).to_list(length=None)
    src_tools = {
        tool.id: tool
        for tool in (_tool_from_doc(doc) for doc in src_tool_docs)
        if tool is not None
    }

    tgt_tool_docs = await db.tools.find({"workspace_id": target_ws.id}).to_list(length=None)
    tgt_tools_by_name = {
        tool.name: tool
        for tool in (_tool_from_doc(doc) for doc in tgt_tool_docs)
        if tool is not None
    }

    tool_id_mapping: dict[str, str] = {}
    for src_id, src_tool in src_tools.items():
        if src_tool.name in tgt_tools_by_name:
            tool_id_mapping[src_id] = tgt_tools_by_name[src_tool.name].id

    # Clone agents
    cloned_count = 0
    skipped_count = 0
    errors: list[str] = []

    for agent in source_agents:
        try:
            result_agent = await _clone_agent(db, agent, target_ws, email, tool_id_mapping)
            if result_agent:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            errors.append(f"Failed to clone '{agent.name}': {str(e)}")

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
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Clone a single resource by type and ID into a destination workspace.

    Supported resource_type values: tool, agent, orchestration.
    """
    email = user.get("email")
    target_ws = await require_workspace_access(
        body.destination_workspace_id, db, user, require_write=True
    )

    if resource_type == "tool":
        source = _tool_from_doc(await db.tools.find_one({"_id": str(resource_id)}))
        if not source:
            raise HTTPException(status_code=404, detail="Tool not found")
        old_to_new: dict[str, str] = {}
        cloned = await _clone_tool(db, source, target_ws, email, old_to_new)
        if cloned:
            return CloneResult(cloned=1)
        return CloneResult(cloned=0, skipped=1)

    elif resource_type == "agent":
        source = _agent_from_doc(await db.agents.find_one({"_id": str(resource_id)}))
        if not source:
            raise HTTPException(status_code=404, detail="Agent not found")
        cloned = await _clone_agent(db, source, target_ws, email)
        if cloned:
            return CloneResult(cloned=1)
        return CloneResult(cloned=0, skipped=1)

    elif resource_type == "orchestration":
        source = _orchestration_from_doc(
            await db.orchestrations.find_one({"_id": str(resource_id)})
        )
        if not source:
            raise HTTPException(status_code=404, detail="Orchestration not found")

        exists = await db.orchestrations.find_one(
            {"workspace_id": target_ws.id, "name": source.name}
        )
        if exists:
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
        await db.orchestrations.insert_one(prepare_document(cloned_orch.model_dump()))
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
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Clone resources required for a specific workflow phase from the Default Workspace.
    """
    email = user.get("email")
    source_ws = await _resolve_source_workspace(db, None)
    target_ws = await require_workspace_access(
        body.destination_workspace_id, db, user, require_write=True
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
    source_tool_docs = await db.tools.find({"workspace_id": source_ws.id}).to_list(length=None)
    source_tools = [_tool_from_doc(doc) for doc in source_tool_docs]
    source_tools = [tool for tool in source_tools if tool is not None]

    old_to_new: dict[str, str] = {}
    # Parents first
    for tool in [t for t in source_tools if t.parent_id is None]:
        try:
            res = await _clone_tool(db, tool, target_ws, email, old_to_new)
            if res: cloned_count += 1
            else: skipped_count += 1
        except Exception as e:
            errors.append(f"Tool clone failed: {str(e)}")
    
    # Children next
    for tool in [t for t in source_tools if t.parent_id is not None]:
        try:
            res = await _clone_tool(db, tool, target_ws, email, old_to_new)
            if res: cloned_count += 1
            else: skipped_count += 1
        except Exception as e:
            errors.append(f"Child tool clone failed: {str(e)}")

    # 2. Clone LLM Configs (for all phases)
    source_llm_docs = await db.llm_configs.find({"workspace_id": source_ws.id}).to_list(length=None)
    source_llms = [_llm_config_from_doc(doc) for doc in source_llm_docs]
    source_llms = [llm for llm in source_llms if llm is not None]
    for llm in source_llms:
        exists = await db.llm_configs.find_one(
            {"workspace_id": target_ws.id, "name": llm.name}
        )
        if exists:
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
        await db.llm_configs.insert_one(prepare_document(cloned_llm.model_dump()))
        cloned_count += 1

    logger.info(
        "Workflow resources cloned for phase %s to workspace %s by %s",
        body.phase, target_ws.id, email
    )
    return CloneResult(cloned=cloned_count, skipped=skipped_count, errors=errors)

