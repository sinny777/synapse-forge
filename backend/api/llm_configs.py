"""
SynapseForge — LLM Configuration API Routes

  • GET    /api/workspaces/{workspace_id}/llm-configs       — list configs
  • POST   /api/workspaces/{workspace_id}/llm-configs       — create config
  • GET    /api/workspaces/{workspace_id}/llm-configs/{id}   — get config
  • PUT    /api/workspaces/{workspace_id}/llm-configs/{id}   — update config
  • DELETE /api/workspaces/{workspace_id}/llm-configs/{id}   — delete config
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import AsyncSessionDep
from db.models import LLMConfig, Workspace
from db.schemas import LLMConfigCreate, LLMConfigUpdate, LLMConfigRead

logger = logging.getLogger("ntr.api.llm_configs")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/llm-configs",
    tags=["LLM Configurations"],
)


async def _get_workspace(
    workspace_id: uuid.UUID, session: AsyncSession
) -> Workspace:
    """Fetch workspace or 404."""
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return ws


@router.get("", response_model=list[LLMConfigRead])
async def list_llm_configs(
    workspace_id: uuid.UUID,
    session: AsyncSessionDep,
):
    """List all LLM configurations for a workspace."""
    await _get_workspace(workspace_id, session)
    result = await session.execute(
        select(LLMConfig)
        .where(LLMConfig.workspace_id == workspace_id)
        .order_by(LLMConfig.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=LLMConfigRead, status_code=status.HTTP_201_CREATED)
async def create_llm_config(
    workspace_id: uuid.UUID,
    body: LLMConfigCreate,
    session: AsyncSessionDep,
):
    """Create a new LLM configuration in a workspace."""
    ws = await _get_workspace(workspace_id, session)

    # Prevent modifications to the default workspace
    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create LLM configurations in the default workspace",
        )

    config = LLMConfig(
        workspace_id=workspace_id,
        name=body.name,
        provider=body.provider,
        model_name=body.model_name,
        credentials=body.credentials,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        created_by="system",
        updated_by="system",
    )
    session.add(config)
    await session.flush()
    await session.refresh(config)

    logger.info("Created LLM config '%s' in workspace %s", config.name, workspace_id)
    return config


@router.get("/{config_id}", response_model=LLMConfigRead)
async def get_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    session: AsyncSessionDep,
):
    """Get a specific LLM configuration."""
    await _get_workspace(workspace_id, session)
    result = await session.execute(
        select(LLMConfig).where(
            LLMConfig.id == config_id,
            LLMConfig.workspace_id == workspace_id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found in workspace {workspace_id}",
        )
    return config


@router.put("/{config_id}", response_model=LLMConfigRead)
async def update_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    body: LLMConfigUpdate,
    session: AsyncSessionDep,
):
    """Update an LLM configuration."""
    ws = await _get_workspace(workspace_id, session)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify LLM configurations in the default workspace",
        )

    result = await session.execute(
        select(LLMConfig).where(
            LLMConfig.id == config_id,
            LLMConfig.workspace_id == workspace_id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)
    config.updated_by = "system"

    await session.flush()
    await session.refresh(config)

    logger.info("Updated LLM config '%s' (%s)", config.name, config_id)
    return config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    session: AsyncSessionDep,
):
    """Delete an LLM configuration."""
    ws = await _get_workspace(workspace_id, session)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete LLM configurations from the default workspace",
        )

    result = await session.execute(
        select(LLMConfig).where(
            LLMConfig.id == config_id,
            LLMConfig.workspace_id == workspace_id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found",
        )

    await session.delete(config)

    logger.info("Deleted LLM config '%s' (%s)", config.name, config_id)
