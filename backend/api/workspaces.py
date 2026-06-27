"""
SynapseForge — Workspace API Routes

CRUD operations for workspaces (the multi-tenant root entity) using MongoDB.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, status, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.auth import get_current_user
from db.engine import get_db, normalize_mongo_document, prepare_document, utcnow
from db.models import Workspace
from db.schemas import WorkspaceCreate, WorkspaceUpdate, WorkspaceRead

logger = logging.getLogger("ntr.api.workspaces")

router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])


def _workspace_from_doc(document: dict | None) -> Workspace | None:
    """Convert a MongoDB document into a Workspace model."""
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return Workspace.model_validate(normalized)


@router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(db: AsyncIOMotorDatabase = Depends(get_db)):
    """Return all workspaces."""
    cursor = db.workspaces.find().sort("created_at", -1)
    workspaces: list[WorkspaceRead] = []
    async for document in cursor:
        workspace = _workspace_from_doc(document)
        if workspace is not None:
            workspaces.append(WorkspaceRead.model_validate(workspace))
    return workspaces


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
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


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a single workspace by ID."""
    workspace = _workspace_from_doc(await db.workspaces.find_one({"_id": str(workspace_id)}))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceRead.model_validate(workspace)


@router.put("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update workspace fields (partial update — only provided fields change)."""
    existing = _workspace_from_doc(await db.workspaces.find_one({"_id": str(workspace_id)}))
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


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
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

# Made with Bob
