"""
NeuralToolRouter — Orchestration API Routes

CRUD operations for multi-agent orchestration definitions within a workspace.
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import AsyncSessionDep
from db.models import Orchestration, Workspace
from db.schemas import (
    OrchestrationCreate,
    OrchestrationUpdate,
    OrchestrationRead,
)
from api.auth import get_current_user
from api.dependencies import require_workspace_access

logger = logging.getLogger("ntr.api.orchestrations")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/orchestrations",
    tags=["Orchestrations"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_workspace_or_404(
    session: AsyncSession, workspace_id: uuid.UUID
) -> Workspace:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("", response_model=list[OrchestrationRead])
async def list_orchestrations(workspace_id: uuid.UUID, session: AsyncSessionDep):
    """List all orchestrations in a workspace."""
    await _get_workspace_or_404(session, workspace_id)
    result = await session.execute(
        select(Orchestration)
        .where(Orchestration.workspace_id == workspace_id)
        .order_by(Orchestration.created_at.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=OrchestrationRead, status_code=status.HTTP_201_CREATED)
async def create_orchestration(
    workspace_id: uuid.UUID, body: OrchestrationCreate, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """Create a new orchestration definition in the workspace."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    email = user.get("email")

    orch = Orchestration(
        workspace_id=workspace_id,
        name=body.name,
        framework=body.framework,
        architecture_type=body.architecture_type,
        config=body.config,
        created_by=email,
        updated_by=email,
    )
    session.add(orch)
    await session.flush()
    await session.refresh(orch)
    logger.info(
        "Created orchestration %s (%s) in workspace %s",
        orch.id, orch.name, workspace_id,
    )
    return orch


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@router.get("/{orchestration_id}", response_model=OrchestrationRead)
async def get_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    session: AsyncSessionDep,
):
    """Get a single orchestration by ID."""
    await _get_workspace_or_404(session, workspace_id)
    orch = await session.get(Orchestration, orchestration_id)
    if orch is None or orch.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return orch


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{orchestration_id}", response_model=OrchestrationRead)
async def update_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    body: OrchestrationUpdate,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user)
):
    """Update an orchestration definition (partial update)."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    orch = await session.get(Orchestration, orchestration_id)
    if orch is None or orch.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Orchestration not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(orch, field, value)
        
    orch.updated_by = user.get("email")

    await session.flush()
    await session.refresh(orch)
    logger.info("Updated orchestration %s", orchestration_id)
    return orch


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{orchestration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_orchestration(
    workspace_id: uuid.UUID,
    orchestration_id: uuid.UUID,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user)
):
    """Delete an orchestration from the workspace."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    orch = await session.get(Orchestration, orchestration_id)
    if orch is None or orch.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Orchestration not found")

    await session.delete(orch)
    logger.info("Deleted orchestration %s from workspace %s", orchestration_id, workspace_id)
