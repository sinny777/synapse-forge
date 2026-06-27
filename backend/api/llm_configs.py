"""
SynapseForge — LLM Configuration API Routes

CRUD operations for workspace LLM configurations using MongoDB.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.engine import get_db, normalize_mongo_document, prepare_document, utcnow
from db.models import LLMConfig, Workspace
from db.schemas import LLMConfigCreate, LLMConfigRead, LLMConfigUpdate

logger = logging.getLogger("ntr.api.llm_configs")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/llm-configs",
    tags=["LLM Configurations"],
)


def _llm_config_from_doc(document: dict | None) -> LLMConfig | None:
    """Convert a MongoDB document into an LLMConfig model."""
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return LLMConfig.model_validate(normalized)


async def _get_workspace(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase,
) -> Workspace:
    """Fetch workspace or 404."""
    document = await db.workspaces.find_one({"_id": str(workspace_id)})
    normalized = normalize_mongo_document(document)
    if normalized is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return Workspace.model_validate(normalized)


@router.get("", response_model=list[LLMConfigRead])
async def list_llm_configs(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all LLM configurations for a workspace."""
    await _get_workspace(workspace_id, db)
    cursor = db.llm_configs.find({"workspace_id": str(workspace_id)}).sort("created_at", 1)

    configs: list[LLMConfigRead] = []
    async for document in cursor:
        config = _llm_config_from_doc(document)
        if config is not None:
            configs.append(LLMConfigRead.model_validate(config))
    return configs


@router.post("", response_model=LLMConfigRead, status_code=status.HTTP_201_CREATED)
async def create_llm_config(
    workspace_id: uuid.UUID,
    body: LLMConfigCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Create a new LLM configuration in a workspace."""
    ws = await _get_workspace(workspace_id, db)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create LLM configurations in the default workspace",
        )

    config = LLMConfig(
        workspace_id=str(workspace_id),
        name=body.name,
        provider=body.provider.value if hasattr(body.provider, "value") else body.provider,
        model_name=body.model_name,
        credentials=body.credentials,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        created_by="system",
        updated_by="system",
    )
    await db.llm_configs.insert_one(prepare_document(config.model_dump()))

    logger.info("Created LLM config '%s' in workspace %s", config.name, workspace_id)
    return LLMConfigRead.model_validate(config)


@router.get("/{config_id}", response_model=LLMConfigRead)
async def get_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a specific LLM configuration."""
    await _get_workspace(workspace_id, db)
    config = _llm_config_from_doc(await db.llm_configs.find_one({"_id": str(config_id)}))
    if config is None or config.workspace_id != str(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found in workspace {workspace_id}",
        )
    return LLMConfigRead.model_validate(config)


@router.put("/{config_id}", response_model=LLMConfigRead)
async def update_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    body: LLMConfigUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update an LLM configuration."""
    ws = await _get_workspace(workspace_id, db)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify LLM configurations in the default workspace",
        )

    config = _llm_config_from_doc(await db.llm_configs.find_one({"_id": str(config_id)}))
    if config is None or config.workspace_id != str(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "provider" and value is not None and hasattr(value, "value"):
            setattr(config, field, value.value)
        else:
            setattr(config, field, value)

    config.updated_by = "system"
    config.updated_at = utcnow()

    await db.llm_configs.replace_one(
        {"_id": str(config_id)},
        prepare_document(config.model_dump()),
    )

    logger.info("Updated LLM config '%s' (%s)", config.name, config_id)
    return LLMConfigRead.model_validate(config)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete an LLM configuration."""
    ws = await _get_workspace(workspace_id, db)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete LLM configurations from the default workspace",
        )

    config = _llm_config_from_doc(await db.llm_configs.find_one({"_id": str(config_id)}))
    if config is None or config.workspace_id != str(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found",
        )

    await db.llm_configs.delete_one({"_id": str(config_id)})
    logger.info("Deleted LLM config '%s' (%s)", config.name, config_id)
