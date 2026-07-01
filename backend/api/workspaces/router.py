"""
api.workspaces.router
~~~~~~~~~~~~~~~~~~~~~
Route handlers for all workspace operations.

Routes:
  GET    /api/workspaces                                  — list workspaces
  POST   /api/workspaces                                  — create workspace
  GET    /api/workspaces/{id}                             — get workspace
  PUT    /api/workspaces/{id}                             — update workspace
  DELETE /api/workspaces/{id}                             — delete workspace
  POST   /api/workspaces/{id}/environment/start           — start Docker env
  POST   /api/workspaces/{id}/environment/stop            — stop Docker env
  POST   /api/clone/tools                                 — batch clone tools
  POST   /api/clone/agents                                — batch clone agents
  POST   /api/clone/{resource_type}/{resource_id}         — clone single resource
  POST   /api/clone/workflow-resources                    — clone phase resources
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.auth import get_current_user
from api.common.utils import model_from_doc
from api.dependencies import require_workspace_access
from api.workspaces.helpers import get_docker_service, resolve_source_workspace
from api.workspaces.schemas import (
    CloneBatchRequest,
    CloneResult,
    CloneSingleRequest,
    CloneWorkflowResourcesRequest,
    EnvironmentActionResponse,
)
from api.workspaces.service import clone_agent, clone_tool
from db.engine import get_db, prepare_document, utcnow
from db.models import Agent, LLMConfig, Orchestration, Tool, ToolType, Workspace, WorkspaceStatus
from db.schemas import WorkspaceCreate, WorkspaceRead, WorkspaceUpdate

logger = logging.getLogger("ntr.api.workspaces")

router = APIRouter()

# ===========================================================================
# Workspace CRUD  —  /api/workspaces
# ===========================================================================

_workspaces_router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])


@_workspaces_router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(db: AsyncIOMotorDatabase = Depends(get_db)):
    """Return all workspaces."""
    cursor = db.workspaces.find().sort("created_at", -1)
    workspaces: list[WorkspaceRead] = []
    async for document in cursor:
        workspace = model_from_doc(document, Workspace)
        if workspace is not None:
            workspaces.append(WorkspaceRead.model_validate(workspace))
    return workspaces


@_workspaces_router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new workspace."""
    existing = await db.workspaces.find_one({"name": body.name})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workspace with name '{body.name}' already exists",
        )

    email = user.get("email")
    workspace = Workspace(
        name=body.name,
        description=body.description,
        embedding_model=body.embedding_model,
        embedding_dim=body.embedding_dim,
        created_by=email,
        updated_by=email,
    )
    await db.workspaces.insert_one(prepare_document(workspace.model_dump()))
    logger.info("Created workspace %s (%s) by %s", workspace.id, workspace.name, email)
    return WorkspaceRead.model_validate(workspace)


@_workspaces_router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a single workspace by ID."""
    workspace = model_from_doc(await db.workspaces.find_one({"_id": str(workspace_id)}), Workspace)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceRead.model_validate(workspace)


@_workspaces_router.put("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update workspace fields (partial update — only provided fields change)."""
    existing = model_from_doc(await db.workspaces.find_one({"_id": str(workspace_id)}), Workspace)
    if existing is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != existing.name:
        duplicate = await db.workspaces.find_one({"name": update_data["name"]})
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workspace name '{body.name}' already exists",
            )

    updated_payload = existing.model_dump()
    updated_payload.update(update_data)
    updated_payload["updated_by"] = user.get("email")
    updated_payload["updated_at"] = utcnow()

    updated_workspace = Workspace.model_validate(updated_payload)
    await db.workspaces.replace_one(
        {"_id": str(workspace_id)},
        prepare_document(updated_workspace.model_dump()),
    )
    logger.info("Updated workspace %s by %s", updated_workspace.id, user.get("email"))
    return WorkspaceRead.model_validate(updated_workspace)


@_workspaces_router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete a workspace and all its children."""
    workspace_key = str(workspace_id)
    existing = await db.workspaces.find_one({"_id": workspace_key})
    if existing is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    await db.tools.delete_many({"workspace_id": workspace_key})
    await db.agents.delete_many({"workspace_id": workspace_key})
    await db.orchestrations.delete_many({"workspace_id": workspace_key})
    await db.llm_configs.delete_many({"workspace_id": workspace_key})
    await db.pipeline_artifacts.delete_many({"workspace_id": workspace_key})
    await db.workspaces.delete_one({"_id": workspace_key})
    logger.info("Deleted workspace %s by %s", workspace_key, user.get("email"))


# ===========================================================================
# Workspace environment  —  /api/workspaces/{id}/environment
# ===========================================================================

@_workspaces_router.post(
    "/{workspace_id}/environment/start",
    response_model=EnvironmentActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Start workspace environment",
    description="Spin up an isolated Docker container for the workspace Data Plane.",
)
async def start_workspace_environment(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
    docker_svc=Depends(get_docker_service),
):
    """Start the Docker container for a workspace."""
    ws = await require_workspace_access(workspace_id, db, user, require_write=True)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot start an environment for the read-only Default Workspace.",
        )
    if ws.status == WorkspaceStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace environment is already running.",
        )

    try:
        container_info = docker_svc.start_workspace_environment(str(workspace_id))
    except RuntimeError as exc:
        ws.status = WorkspaceStatus.RUNNING
        await db.workspaces.replace_one({"_id": ws.id}, prepare_document(ws.model_dump()))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception as exc:
        ws.status = WorkspaceStatus.FAILED
        await db.workspaces.replace_one({"_id": ws.id}, prepare_document(ws.model_dump()))
        logger.error("Failed to start container for workspace %s: %s", workspace_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start workspace environment: {exc}",
        )

    ws.status = WorkspaceStatus.RUNNING
    ws.updated_by = user.get("email")
    ws.touch(user.get("email"))
    await db.workspaces.replace_one({"_id": ws.id}, prepare_document(ws.model_dump()))
    logger.info("Workspace %s environment started by %s", workspace_id, user.get("email"))
    return EnvironmentActionResponse(
        workspace_id=workspace_id,
        status="RUNNING",
        message="Workspace environment started successfully.",
        container_info=container_info,
    )


@_workspaces_router.post(
    "/{workspace_id}/environment/stop",
    response_model=EnvironmentActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Stop workspace environment",
    description="Gracefully stop and remove the Docker container for the workspace.",
)
async def stop_workspace_environment(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
    docker_svc=Depends(get_docker_service),
):
    """Stop and remove the Docker container for a workspace."""
    ws = await require_workspace_access(workspace_id, db, user, require_write=True)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot stop the read-only Default Workspace.",
        )

    try:
        container_info = docker_svc.stop_workspace_environment(str(workspace_id))
    except RuntimeError as exc:
        ws.status = WorkspaceStatus.STOPPED
        await db.workspaces.replace_one({"_id": ws.id}, prepare_document(ws.model_dump()))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        ws.status = WorkspaceStatus.FAILED
        await db.workspaces.replace_one({"_id": ws.id}, prepare_document(ws.model_dump()))
        logger.error("Failed to stop container for workspace %s: %s", workspace_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop workspace environment: {exc}",
        )

    ws.status = WorkspaceStatus.STOPPED
    ws.updated_by = user.get("email")
    ws.touch(user.get("email"))
    await db.workspaces.replace_one({"_id": ws.id}, prepare_document(ws.model_dump()))
    logger.info("Workspace %s environment stopped by %s", workspace_id, user.get("email"))
    return EnvironmentActionResponse(
        workspace_id=workspace_id,
        status="STOPPED",
        message="Workspace environment stopped and container removed.",
        container_info=container_info,
    )


# ===========================================================================
# Workspace cloning  —  /api/clone
# ===========================================================================

_clone_router = APIRouter(prefix="/api/clone", tags=["Cloning"])


@_clone_router.post("/tools", response_model=CloneResult)
async def clone_tools(
    body: CloneBatchRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Clone selected tools from a source workspace into a destination workspace.

    If source_workspace_id is omitted, the System Default Workspace is used.
    """
    email = user.get("email")
    source_ws = await resolve_source_workspace(db, body.source_workspace_id)
    target_ws = await require_workspace_access(body.destination_workspace_id, db, user, require_write=True)

    if source_ws.id == target_ws.id:
        raise HTTPException(status_code=400, detail="Source and destination must be different workspaces")

    source_tool_docs = await db.tools.find(
        {"workspace_id": source_ws.id, "_id": {"$in": [str(rid) for rid in body.resource_ids]}}
    ).to_list(length=None)
    source_tools = [t for t in (model_from_doc(doc, Tool) for doc in source_tool_docs) if t is not None]

    if not source_tools:
        raise HTTPException(status_code=404, detail="No matching tools found in source workspace")

    parent_ids = [t.id for t in source_tools if t.type == ToolType.MCP_SERVER]
    child_tools: list[Tool] = []
    if parent_ids:
        child_docs = await db.tools.find(
            {"workspace_id": source_ws.id, "parent_id": {"$in": parent_ids}}
        ).to_list(length=None)
        child_tools = [t for t in (model_from_doc(doc, Tool) for doc in child_docs) if t is not None]

    old_to_new: dict[str, str] = {}
    cloned_count = skipped_count = 0
    errors: list[str] = []

    for tool in source_tools:
        try:
            result = await clone_tool(db, tool, target_ws, email, old_to_new)
            if result:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            errors.append(f"Failed to clone '{tool.name}': {exc}")

    for child in child_tools:
        try:
            result = await clone_tool(db, child, target_ws, email, old_to_new)
            if result:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            errors.append(f"Failed to clone child '{child.name}': {exc}")

    logger.info(
        "Cloned %d tools (%d skipped) from workspace %s → %s by %s",
        cloned_count, skipped_count, source_ws.id, target_ws.id, email,
    )
    return CloneResult(cloned=cloned_count, skipped=skipped_count, errors=errors)


@_clone_router.post("/agents", response_model=CloneResult)
async def clone_agents(
    body: CloneBatchRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Clone selected agents from a source workspace into a destination workspace.

    If source_workspace_id is omitted, the System Default Workspace is used.
    """
    email = user.get("email")
    source_ws = await resolve_source_workspace(db, body.source_workspace_id)
    target_ws = await require_workspace_access(body.destination_workspace_id, db, user, require_write=True)

    if source_ws.id == target_ws.id:
        raise HTTPException(status_code=400, detail="Source and destination must be different workspaces")

    source_agent_docs = await db.agents.find(
        {"workspace_id": source_ws.id, "_id": {"$in": [str(rid) for rid in body.resource_ids]}}
    ).to_list(length=None)
    source_agents = [a for a in (model_from_doc(doc, Agent) for doc in source_agent_docs) if a is not None]

    if not source_agents:
        raise HTTPException(status_code=404, detail="No matching agents found in source workspace")

    src_tools = {
        t.id: t
        for t in (model_from_doc(doc, Tool) for doc in await db.tools.find({"workspace_id": source_ws.id}).to_list(length=None))
        if t is not None
    }
    tgt_tools_by_name = {
        t.name: t
        for t in (model_from_doc(doc, Tool) for doc in await db.tools.find({"workspace_id": target_ws.id}).to_list(length=None))
        if t is not None
    }

    tool_id_mapping: dict[str, str] = {
        src_id: tgt_tools_by_name[src_tool.name].id
        for src_id, src_tool in src_tools.items()
        if src_tool.name in tgt_tools_by_name
    }

    cloned_count = skipped_count = 0
    errors: list[str] = []

    for agent in source_agents:
        try:
            result = await clone_agent(db, agent, target_ws, email, tool_id_mapping)
            if result:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            errors.append(f"Failed to clone '{agent.name}': {exc}")

    logger.info(
        "Cloned %d agents (%d skipped) from workspace %s → %s by %s",
        cloned_count, skipped_count, source_ws.id, target_ws.id, email,
    )
    return CloneResult(cloned=cloned_count, skipped=skipped_count, errors=errors)


@_clone_router.post("/{resource_type}/{resource_id}", response_model=CloneResult)
async def clone_single_resource(
    resource_type: Literal["tool", "agent", "orchestration"],
    resource_id: uuid.UUID,
    body: CloneSingleRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Clone a single resource by type and ID into a destination workspace."""
    email = user.get("email")
    target_ws = await require_workspace_access(body.destination_workspace_id, db, user, require_write=True)

    if resource_type == "tool":
        source = model_from_doc(await db.tools.find_one({"_id": str(resource_id)}), Tool)
        if not source:
            raise HTTPException(status_code=404, detail="Tool not found")
        old_to_new: dict[str, str] = {}
        cloned = await clone_tool(db, source, target_ws, email, old_to_new)
        return CloneResult(cloned=1 if cloned else 0, skipped=0 if cloned else 1)

    elif resource_type == "agent":
        source = model_from_doc(await db.agents.find_one({"_id": str(resource_id)}), Agent)
        if not source:
            raise HTTPException(status_code=404, detail="Agent not found")
        cloned = await clone_agent(db, source, target_ws, email)
        return CloneResult(cloned=1 if cloned else 0, skipped=0 if cloned else 1)

    elif resource_type == "orchestration":
        source = model_from_doc(
            await db.orchestrations.find_one({"_id": str(resource_id)}), Orchestration
        )
        if not source:
            raise HTTPException(status_code=404, detail="Orchestration not found")

        exists = await db.orchestrations.find_one({"workspace_id": target_ws.id, "name": source.name})
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


@_clone_router.post("/workflow-resources", response_model=CloneResult)
async def clone_workflow_resources(
    body: CloneWorkflowResourcesRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Clone resources required for a specific workflow phase from the Default Workspace."""
    email = user.get("email")
    source_ws = await resolve_source_workspace(db, None)
    target_ws = await require_workspace_access(body.destination_workspace_id, db, user, require_write=True)

    if source_ws.id == target_ws.id:
        raise HTTPException(status_code=400, detail="Cannot clone into the default workspace")

    cloned_count = skipped_count = 0
    errors: list[str] = []

    source_tools = [
        t for t in (model_from_doc(doc, Tool) for doc in await db.tools.find({"workspace_id": source_ws.id}).to_list(length=None))
        if t is not None
    ]

    old_to_new: dict[str, str] = {}
    for tool in [t for t in source_tools if t.parent_id is None]:
        try:
            res = await clone_tool(db, tool, target_ws, email, old_to_new)
            if res:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            errors.append(f"Tool clone failed: {exc}")

    for tool in [t for t in source_tools if t.parent_id is not None]:
        try:
            res = await clone_tool(db, tool, target_ws, email, old_to_new)
            if res:
                cloned_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            errors.append(f"Child tool clone failed: {exc}")

    source_llms = [
        l for l in (model_from_doc(doc, LLMConfig) for doc in await db.llm_configs.find({"workspace_id": source_ws.id}).to_list(length=None))
        if l is not None
    ]
    for llm in source_llms:
        exists = await db.llm_configs.find_one({"workspace_id": target_ws.id, "name": llm.name})
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
            updated_by=email,
        )
        await db.llm_configs.insert_one(prepare_document(cloned_llm.model_dump()))
        cloned_count += 1

    logger.info(
        "Workflow resources cloned for phase %s to workspace %s by %s",
        body.phase, target_ws.id, email,
    )
    return CloneResult(cloned=cloned_count, skipped=skipped_count, errors=errors)


# Combine sub-routers into the single exported `router`
router.include_router(_workspaces_router)
router.include_router(_clone_router)
