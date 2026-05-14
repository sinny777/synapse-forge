"""
NeuralToolRouter — Agent API Routes

CRUD operations for agent definitions within a workspace.
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import AsyncSessionDep
from db.models import Agent, Workspace
from db.schemas import AgentCreate, AgentUpdate, AgentRead

logger = logging.getLogger("ntr.api.agents")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/agents",
    tags=["Agents"],
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

@router.get("", response_model=list[AgentRead])
async def list_agents(workspace_id: uuid.UUID, session: AsyncSessionDep):
    """List all agents in a workspace."""
    await _get_workspace_or_404(session, workspace_id)
    result = await session.execute(
        select(Agent)
        .where(Agent.workspace_id == workspace_id)
        .order_by(Agent.created_at.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    workspace_id: uuid.UUID, body: AgentCreate, session: AsyncSessionDep
):
    """Create a new agent definition in the workspace."""
    await _get_workspace_or_404(session, workspace_id)

    agent = Agent(
        workspace_id=workspace_id,
        name=body.name,
        system_prompt=body.system_prompt,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model,
        attached_tool_ids=body.attached_tool_ids,
    )
    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    logger.info("Created agent %s (%s) in workspace %s", agent.id, agent.name, workspace_id)
    return agent


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, session: AsyncSessionDep
):
    """Get a single agent by ID."""
    await _get_workspace_or_404(session, workspace_id)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentUpdate,
    session: AsyncSessionDep,
):
    """Update an agent definition (partial update)."""
    await _get_workspace_or_404(session, workspace_id)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    await session.flush()
    await session.refresh(agent)
    logger.info("Updated agent %s", agent_id)
    return agent


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, session: AsyncSessionDep
):
    """Delete an agent from the workspace."""
    await _get_workspace_or_404(session, workspace_id)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    await session.delete(agent)
    logger.info("Deleted agent %s from workspace %s", agent_id, workspace_id)
