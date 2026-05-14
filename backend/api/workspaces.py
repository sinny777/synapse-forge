"""
NeuralToolRouter — Workspace API Routes

CRUD operations for workspaces (the multi-tenant root entity).
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.engine import AsyncSessionDep
from db.models import Workspace
from db.schemas import WorkspaceCreate, WorkspaceUpdate, WorkspaceRead
from api.auth import get_current_user
from api.dependencies import require_workspace_access

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
async def create_workspace(body: WorkspaceCreate, session: AsyncSessionDep, user: dict = Depends(get_current_user)):
    """Create a new workspace."""
    email = user.get("email")
    ws = Workspace(
        name=body.name,
        description=body.description,
        embedding_model=body.embedding_model,
        embedding_dim=body.embedding_dim,
        created_by=email,
        updated_by=email,
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
    logger.info("Created workspace %s (%s) by %s", ws.id, ws.name, email)
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
    workspace_id: uuid.UUID, body: WorkspaceUpdate, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """Update workspace fields (partial update — only provided fields change)."""
    ws = await require_workspace_access(workspace_id, session, user, require_write=True)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ws, field, value)
        
    ws.updated_by = user.get("email")

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workspace name '{body.name}' already exists",
        )
    await session.refresh(ws)
    logger.info("Updated workspace %s by %s", ws.id, user.get("email"))
    return ws


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: uuid.UUID, session: AsyncSessionDep, user: dict = Depends(get_current_user)):
    """Delete a workspace and all its children (cascade)."""
    ws = await require_workspace_access(workspace_id, session, user, require_write=True)

    await session.delete(ws)
    logger.info("Deleted workspace %s by %s", workspace_id, user.get("email"))
