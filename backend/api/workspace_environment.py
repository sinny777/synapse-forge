"""
SynapseForge — Workspace Environment API Routes

Exposes Control Plane endpoints to start and stop isolated Docker
containers for each workspace (Data Plane instances).

Routes:
  POST /api/workspaces/{workspace_id}/environment/start
  POST /api/workspaces/{workspace_id}/environment/stop

Reference: PLATFORM_REQUIREMENTS_V2.md §6.2
"""

import uuid
import logging
from functools import lru_cache

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, ConfigDict

from db.engine import AsyncSessionDep
from db.models import Workspace, WorkspaceStatus
from api.auth import get_current_user
from api.dependencies import require_workspace_access

logger = logging.getLogger("ntr.api.workspace_environment")

router = APIRouter(
    prefix="/api/workspaces",
    tags=["Workspace Environment"],
)


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

class EnvironmentActionResponse(BaseModel):
    """Response returned by start/stop environment endpoints."""
    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    status: str
    message: str
    container_info: dict | None = None


# ---------------------------------------------------------------------------
# Docker Service Singleton
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/{workspace_id}/environment/start",
    response_model=EnvironmentActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Start workspace environment",
    description="Spin up an isolated Docker container for the workspace Data Plane.",
)
async def start_workspace_environment(
    workspace_id: uuid.UUID,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user),
    docker_svc=Depends(get_docker_service),
):
    """
    Start the Docker container for a workspace.

    1. Validates the workspace exists and the user has write access.
    2. Ensures the workspace is not the read-only Default Workspace.
    3. Uses the Docker SDK to spin up an isolated container.
    4. Updates the workspace status to RUNNING in the database.
    """
    # 1. Validate workspace access
    ws = await require_workspace_access(workspace_id, session, user, require_write=True)

    # 2. Block starting the Default Workspace
    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot start an environment for the read-only Default Workspace.",
        )

    # 3. Check if already running
    if ws.status == WorkspaceStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace environment is already running.",
        )

    # 4. Start the container
    try:
        container_info = docker_svc.start_workspace_environment(str(workspace_id))
    except RuntimeError as exc:
        # Container already running at Docker level — sync DB status
        ws.status = WorkspaceStatus.RUNNING
        await session.flush()
        await session.refresh(ws)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except Exception as exc:
        # Unexpected failure — mark workspace as FAILED
        ws.status = WorkspaceStatus.FAILED
        await session.flush()
        logger.error("Failed to start container for workspace %s: %s", workspace_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start workspace environment: {exc}",
        )

    # 5. Update workspace status in DB
    ws.status = WorkspaceStatus.RUNNING
    ws.updated_by = user.get("email")
    await session.flush()
    await session.refresh(ws)

    logger.info(
        "Workspace %s environment started by %s", workspace_id, user.get("email")
    )

    return EnvironmentActionResponse(
        workspace_id=workspace_id,
        status="RUNNING",
        message="Workspace environment started successfully.",
        container_info=container_info,
    )


@router.post(
    "/{workspace_id}/environment/stop",
    response_model=EnvironmentActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Stop workspace environment",
    description="Gracefully stop and remove the Docker container for the workspace.",
)
async def stop_workspace_environment(
    workspace_id: uuid.UUID,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user),
    docker_svc=Depends(get_docker_service),
):
    """
    Stop and remove the Docker container for a workspace.

    1. Validates the workspace exists and the user has write access.
    2. Gracefully stops the container (SIGTERM → 10s → SIGKILL).
    3. Removes the container.
    4. Updates the workspace status to STOPPED in the database.
    """
    # 1. Validate workspace access
    ws = await require_workspace_access(workspace_id, session, user, require_write=True)

    # 2. Block stopping the Default Workspace (it should never be running)
    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot stop the read-only Default Workspace.",
        )

    # 3. Stop the container
    try:
        container_info = docker_svc.stop_workspace_environment(str(workspace_id))
    except RuntimeError as exc:
        # No container found — ensure DB status is STOPPED
        ws.status = WorkspaceStatus.STOPPED
        await session.flush()
        await session.refresh(ws)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        ws.status = WorkspaceStatus.FAILED
        await session.flush()
        logger.error("Failed to stop container for workspace %s: %s", workspace_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop workspace environment: {exc}",
        )

    # 4. Update workspace status in DB
    ws.status = WorkspaceStatus.STOPPED
    ws.updated_by = user.get("email")
    await session.flush()
    await session.refresh(ws)

    logger.info(
        "Workspace %s environment stopped by %s", workspace_id, user.get("email")
    )

    return EnvironmentActionResponse(
        workspace_id=workspace_id,
        status="STOPPED",
        message="Workspace environment stopped and container removed.",
        container_info=container_info,
    )
