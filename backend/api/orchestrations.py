"""
SynapseForge — Orchestration API Routes

CRUD operations for multi-agent orchestration definitions within a workspace
using MongoDB.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.auth import get_current_user
from api.dependencies import require_workspace_access
from db.engine import get_db, normalize_mongo_document, prepare_document, utcnow
from db.models import Orchestration, Workspace
from db.schemas import OrchestrationCreate, OrchestrationRead, OrchestrationUpdate

logger = logging.getLogger("ntr.api.orchestrations")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/orchestrations",
    tags=["Orchestrations"],
)


def _orchestration_from_doc(document: dict | None) -> Orchestration | None:
    """Convert a MongoDB document into an Orchestration model."""
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return Orchestration.model_validate(normalized)


async def _get_workspace_or_404(
    db: AsyncIOMotorDatabase,
    workspace_id: uuid.UUID,
) -> Workspace:
    document = await db.workspaces.find_one({"_id": str(workspace_id)})
    normalized = normalize_mongo_document(document)
    if normalized is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return Workspace.model_validate(normalized)


@router.get("", response_model=list[OrchestrationRead])
async def list_orchestrations(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all orchestrations in a workspace."""
    await _get_workspace_or_404(db, workspace_id)
    cursor = db.orchestrations.find({"workspace_id": str(workspace_id)}).sort("created_at", -1)

    orchestrations: list[OrchestrationRead] = []
    async for document in cursor:
        orchestration = _orchestration_from_doc(document)
        if orchestration is not None:
            orchestrations.append(OrchestrationRead.model_validate(orchestration))
    return orchestrations


@router.post("", response_model=OrchestrationRead, status_code=status.HTTP_201_CREATED)
async def create_orchestration(
    workspace_id: uuid.UUID,
    body: OrchestrationCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new orchestration definition in the workspace."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    email = user.get("email")

    orchestration = Orchestration(
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
    await db.orchestrations.insert_one(prepare_document(orchestration.model_dump()))
    logger.info(
        "Created orchestration %s (%s) in workspace %s",
        orchestration.id,
        orchestration.name,
        workspace_id,
    )
    return OrchestrationRead.model_validate(orchestration)


@router.get("/{orchestration_id}", response_model=OrchestrationRead)
async def get_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a single orchestration by ID."""
    await _get_workspace_or_404(db, workspace_id)
    orchestration = _orchestration_from_doc(
        await db.orchestrations.find_one({"_id": str(orchestration_id)})
    )
    if orchestration is None or orchestration.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return OrchestrationRead.model_validate(orchestration)


@router.put("/{orchestration_id}", response_model=OrchestrationRead)
async def update_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    body: OrchestrationUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update an orchestration definition."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    orchestration = _orchestration_from_doc(
        await db.orchestrations.find_one({"_id": str(orchestration_id)})
    )
    if orchestration is None or orchestration.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Orchestration not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in {"framework", "architecture_type"} and value is not None and hasattr(value, "value"):
            setattr(orchestration, field, value.value)
        else:
            setattr(orchestration, field, value)

    orchestration.updated_by = user.get("email")
    orchestration.updated_at = utcnow()

    await db.orchestrations.replace_one(
        {"_id": str(orchestration_id)},
        prepare_document(orchestration.model_dump()),
    )
    logger.info("Updated orchestration %s", orchestration_id)
    return OrchestrationRead.model_validate(orchestration)


@router.delete("/{orchestration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete an orchestration from the workspace."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    orchestration = _orchestration_from_doc(
        await db.orchestrations.find_one({"_id": str(orchestration_id)})
    )
    if orchestration is None or orchestration.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Orchestration not found")

    await db.orchestrations.delete_one({"_id": str(orchestration_id)})
    logger.info("Deleted orchestration %s from workspace %s", orchestration_id, workspace_id)
