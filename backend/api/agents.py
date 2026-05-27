"""
SynapseForge — Agent API Routes

CRUD operations for agent definitions within a workspace.
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import AsyncSessionDep
from db.models import Agent, Workspace
from db.schemas import AgentCreate, AgentUpdate, AgentRead, CollaboratorAgentRead
from api.auth import get_current_user
from api.dependencies import require_workspace_access

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
# Helpers
# ---------------------------------------------------------------------------

async def _validate_collaborators(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    collaborator_ids: list[uuid.UUID] | None,
    agent_id: uuid.UUID | None = None,
) -> list[uuid.UUID] | None:
    if collaborator_ids is None:
        return None

    normalized_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for collaborator_id in collaborator_ids:
        collaborator_uuid = collaborator_id if isinstance(collaborator_id, uuid.UUID) else uuid.UUID(str(collaborator_id))
        if agent_id is not None and collaborator_uuid == agent_id:
            raise HTTPException(status_code=400, detail="An agent cannot collaborate with itself")
        if collaborator_uuid not in seen:
            seen.add(collaborator_uuid)
            normalized_ids.append(collaborator_uuid)

    if not normalized_ids:
        return []

    result = await session.execute(
        select(Agent.id).where(
            Agent.workspace_id == workspace_id,
            Agent.id.in_(normalized_ids),
        )
    )
    valid_ids = {row[0] for row in result.all()}
    missing = [str(collaborator_id) for collaborator_id in normalized_ids if collaborator_id not in valid_ids]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid collaborator agents for this workspace: {', '.join(missing)}",
        )

    return normalized_ids


async def _build_agent_read_payload(
    session: AsyncSession,
    agent: Agent,
) -> AgentRead:
    collaborator_ids = agent.collaborator_agent_ids or []
    collaborators: list[Agent] = []

    if collaborator_ids:
        collaborator_alias = aliased(Agent)
        result = await session.execute(
            select(collaborator_alias).where(
                collaborator_alias.workspace_id == agent.workspace_id,
                collaborator_alias.id.in_(collaborator_ids),
            )
        )
        collaborators_by_id = {collaborator.id: collaborator for collaborator in result.scalars().all()}
        collaborators = [collaborators_by_id[collaborator_id] for collaborator_id in collaborator_ids if collaborator_id in collaborators_by_id]

    payload = AgentRead.model_validate(agent)
    payload.collaborators = [
        CollaboratorAgentRead(
            id=collaborator.id,
            workspace_id=collaborator.workspace_id,
            name=collaborator.name,
            description=collaborator.description,
            system_prompt=collaborator.system_prompt,
        )
        for collaborator in collaborators
    ]
    return payload


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
    agents = result.scalars().all()
    return [await _build_agent_read_payload(session, agent) for agent in agents]


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    workspace_id: uuid.UUID, body: AgentCreate, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """Create a new agent definition in the workspace."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    email = user.get("email")

    collaborator_agent_ids = await _validate_collaborators(
        session,
        workspace_id,
        body.collaborator_agent_ids,
    )

    agent = Agent(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        llm_config_id=body.llm_config_id,
        use_neural_router=body.use_neural_router,
        router_model_id=body.router_model_id,
        router_top_k=body.router_top_k,
        memory_type=body.memory_type,
        memory_window=body.memory_window,
        max_iterations=body.max_iterations,
        timeout_seconds=body.timeout_seconds,
        attached_tool_ids=body.attached_tool_ids,
        collaborator_agent_ids=collaborator_agent_ids,
        created_by=email,
        updated_by=email,
    )
    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    logger.info("Created agent %s (%s) in workspace %s", agent.id, agent.name, workspace_id)
    return await _build_agent_read_payload(session, agent)


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
    return await _build_agent_read_payload(session, agent)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentUpdate,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user)
):
    """Update an agent definition (partial update)."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)

    if "collaborator_agent_ids" in update_data:
        update_data["collaborator_agent_ids"] = await _validate_collaborators(
            session,
            workspace_id,
            update_data["collaborator_agent_ids"],
            agent_id=agent.id,
        )

    for field, value in update_data.items():
        setattr(agent, field, value)

    agent.updated_by = user.get("email")

    await session.flush()
    await session.refresh(agent)
    logger.info("Updated agent %s", agent_id)
    return await _build_agent_read_payload(session, agent)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """Delete an agent from the workspace."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    await session.delete(agent)
    logger.info("Deleted agent %s from workspace %s", agent_id, workspace_id)
