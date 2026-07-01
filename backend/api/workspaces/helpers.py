"""
api.workspaces.helpers
~~~~~~~~~~~~~~~~~~~~~~
Utility functions for workspace CRUD, cloning, and environment operations.
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.common.utils import model_from_doc
from db.models import Workspace

logger = logging.getLogger("ntr.api.workspaces")


async def resolve_source_workspace(
    db: AsyncIOMotorDatabase,
    source_id: uuid.UUID | None,
) -> Workspace:
    """Resolve the source workspace — explicit or default."""
    if source_id:
        ws = model_from_doc(await db.workspaces.find_one({"_id": str(source_id)}), Workspace)
        if ws is None:
            raise HTTPException(status_code=404, detail="Source workspace not found")
        return ws

    ws = model_from_doc(await db.workspaces.find_one({"is_default": True}), Workspace)
    if ws is None:
        raise HTTPException(
            status_code=404,
            detail="Default Workspace not found. Run 'python -m setup.reset_db' to create it.",
        )
    return ws


@lru_cache(maxsize=1)
def _get_docker_service():
    """
    Lazily initialise the WorkspaceDockerService singleton.

    Cached so the Docker client is created once and reused across requests.
    Returns None if Docker is not available (graceful degradation).
    """
    try:
        from services.workspace_docker_service import WorkspaceDockerService
        return WorkspaceDockerService()
    except RuntimeError as exc:
        logger.warning("Docker service unavailable: %s", exc)
        return None


def get_docker_service():
    """FastAPI dependency that provides the Docker service."""
    svc = _get_docker_service()
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Docker service is not available. "
                "Ensure Docker Desktop is running and accessible."
            ),
        )
    return svc
