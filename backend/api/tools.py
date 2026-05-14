"""
NeuralToolRouter — Tool API Routes

CRUD operations for tools within a workspace.
On creation (and update when description changes), an embedding is
generated via the workspace's configured embedding model and stored
in the pgvector ``embedding`` column for semantic search.
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import AsyncSessionDep
from db.models import Tool, Workspace
from db.schemas import ToolCreate, ToolUpdate, ToolRead
from services.embedding_service import embedding_service

logger = logging.getLogger("ntr.api.tools")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/tools",
    tags=["Tools"],
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


def _generate_embedding(
    ws: Workspace, name: str, description: str | None, schema_def: dict | None
) -> list[float]:
    """Generate a tool embedding using the workspace's configured model."""
    return embedding_service.embed_tool(
        name=name,
        description=description,
        schema_def=schema_def,
        model_name=ws.embedding_model,
    )


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ToolRead])
async def list_tools(workspace_id: uuid.UUID, session: AsyncSessionDep):
    """List all tools in a workspace."""
    await _get_workspace_or_404(session, workspace_id)
    result = await session.execute(
        select(Tool)
        .where(Tool.workspace_id == workspace_id)
        .order_by(Tool.created_at.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
async def create_tool(
    workspace_id: uuid.UUID, body: ToolCreate, session: AsyncSessionDep
):
    """
    Register a new tool in the workspace.

    An embedding is automatically generated from the tool's
    ``name``, ``description``, and ``schema_def`` using the
    workspace's embedding model and stored for pgvector search.
    """
    ws = await _get_workspace_or_404(session, workspace_id)

    # Generate embedding
    vec = _generate_embedding(ws, body.name, body.description, body.schema_def)

    tool = Tool(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        type=body.type,
        connection_config=body.connection_config,
        schema_def=body.schema_def,
        embedding=vec,
    )
    session.add(tool)
    await session.flush()
    await session.refresh(tool)
    logger.info("Created tool %s (%s) in workspace %s", tool.id, tool.name, workspace_id)
    return tool


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(
    workspace_id: uuid.UUID, tool_id: uuid.UUID, session: AsyncSessionDep
):
    """Get a single tool by ID."""
    await _get_workspace_or_404(session, workspace_id)
    tool = await session.get(Tool, tool_id)
    if tool is None or tool.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{tool_id}", response_model=ToolRead)
async def update_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: ToolUpdate,
    session: AsyncSessionDep,
):
    """
    Update a tool.

    If ``name``, ``description``, or ``schema_def`` change, the
    embedding is regenerated automatically.
    """
    ws = await _get_workspace_or_404(session, workspace_id)
    tool = await session.get(Tool, tool_id)
    if tool is None or tool.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Tool not found")

    update_data = body.model_dump(exclude_unset=True)
    needs_reembed = any(k in update_data for k in ("name", "description", "schema_def"))

    for field, value in update_data.items():
        setattr(tool, field, value)

    if needs_reembed:
        tool.embedding = _generate_embedding(
            ws, tool.name, tool.description, tool.schema_def
        )
        logger.info("Re-embedded tool %s after metadata change", tool_id)

    await session.flush()
    await session.refresh(tool)
    logger.info("Updated tool %s", tool_id)
    return tool


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    workspace_id: uuid.UUID, tool_id: uuid.UUID, session: AsyncSessionDep
):
    """Delete a tool from the workspace."""
    await _get_workspace_or_404(session, workspace_id)
    tool = await session.get(Tool, tool_id)
    if tool is None or tool.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Tool not found")

    await session.delete(tool)
    logger.info("Deleted tool %s from workspace %s", tool_id, workspace_id)
