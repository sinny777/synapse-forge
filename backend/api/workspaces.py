"""
NeuralToolRouter — Workspace API Routes

CRUD operations for workspaces (the multi-tenant root entity).
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.engine import AsyncSessionDep
from db.models import Workspace
from db.schemas import WorkspaceCreate, WorkspaceUpdate, WorkspaceRead

logger = logging.getLogger("ntr.api.workspaces")

router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(session: AsyncSessionDep):
    """Return all workspaces."""
    result = await session.execute(
        select(Workspace).order_by(Workspace.created_at.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceCreate, session: AsyncSessionDep):
    """Create a new workspace."""
    ws = Workspace(
        name=body.name,
        description=body.description,
        embedding_model=body.embedding_model,
        embedding_dim=body.embedding_dim,
    )
    session.add(ws)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workspace with name '{body.name}' already exists",
        )
    await session.refresh(ws)
    logger.info("Created workspace %s (%s)", ws.id, ws.name)
    return ws


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(workspace_id: uuid.UUID, session: AsyncSessionDep):
    """Get a single workspace by ID."""
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: uuid.UUID, body: WorkspaceUpdate, session: AsyncSessionDep
):
    """Update workspace fields (partial update — only provided fields change)."""
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ws, field, value)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workspace name '{body.name}' already exists",
        )
    await session.refresh(ws)
    logger.info("Updated workspace %s", ws.id)
    return ws


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: uuid.UUID, session: AsyncSessionDep):
    """Delete a workspace and all its children (cascade)."""
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    await session.delete(ws)
    logger.info("Deleted workspace %s", workspace_id)
