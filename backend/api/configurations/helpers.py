"""
api.configurations.helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~
Utility functions shared within the configurations domain.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.common.utils import model_from_doc
from db.models import LLMConfig, Workspace


def llm_config_from_doc(document: dict | None) -> LLMConfig | None:
    """Convert a MongoDB document into an LLMConfig model."""
    return model_from_doc(document, LLMConfig)


async def get_workspace(workspace_id: uuid.UUID, db: AsyncIOMotorDatabase) -> Workspace:
    """Fetch workspace by ID or raise HTTP 404."""
    document = await db.workspaces.find_one({"_id": str(workspace_id)})
    workspace = model_from_doc(document, Workspace)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return workspace
