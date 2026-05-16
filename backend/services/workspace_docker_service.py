"""
SynapseForge — Workspace Docker Service (Control Plane)

Manages the lifecycle of isolated Docker containers for each workspace.
Each workspace runs in its own "Data Plane" container that receives the
workspace_id, database URL, and Redis URL as environment variables, and
is attached to the shared SynapseForge Docker network.

Reference: PLATFORM_REQUIREMENTS_V2.md §3.2, §6.2
"""

import os
import logging
from typing import Any

import docker
from docker.errors import NotFound, APIError, ImageNotFound

logger = logging.getLogger("ntr.services.workspace_docker")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Docker image used for workspace Data Plane containers.
# Override with WORKSPACE_CONTAINER_IMAGE env var to use a custom image.
DEFAULT_CONTAINER_IMAGE = "python:3.11-slim"

# Shared Docker network name for inter-container communication.
# This network connects workspace containers to PostgreSQL, Redis, etc.
DOCKER_NETWORK_NAME = os.getenv("DOCKER_NETWORK_NAME", "synapse-forge_default")

# Naming convention for workspace containers
CONTAINER_NAME_PREFIX = "sf-workspace-"


def _container_name(workspace_id: str) -> str:
    """Generate a deterministic container name from a workspace UUID."""
    return f"{CONTAINER_NAME_PREFIX}{workspace_id}"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class WorkspaceDockerService:
    """
    Control Plane service for managing workspace Docker containers.

    Responsibilities:
      • start_workspace_environment — pull image, create & start container
      • stop_workspace_environment  — gracefully stop & remove container
      • get_container_status        — inspect a running container

    All operations are synchronous (Docker SDK is sync) and should be called
    from FastAPI endpoints via ``run_in_executor`` or directly since they are
    I/O-bound blocking calls wrapped in async route handlers.
    """

    def __init__(self) -> None:
        """Initialise a connection to the local Docker daemon."""
        try:
            self._client = docker.from_env()
            self._client.ping()
            logger.info("Docker daemon connected ✓")
        except docker.errors.DockerException as exc:
            logger.error("Failed to connect to Docker daemon: %s", exc)
            raise RuntimeError(
                "Cannot connect to Docker. Ensure Docker Desktop is running "
                "and the current user has permission to access the Docker socket."
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_database_url(self) -> str:
        """
        Build the PostgreSQL connection URL that workspace containers will use.

        Inside the Docker network, the DB host is the container name
        (e.g. 'ntr_postgres') rather than 'localhost'.
        """
        user = os.getenv("POSTGRES_USER", "ntr_user")
        password = os.getenv("POSTGRES_PASSWORD", "ntr_secret_2026")
        host = os.getenv("WORKSPACE_DB_HOST", os.getenv("POSTGRES_HOST", "localhost"))
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "synapse_forge")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    def _build_redis_url(self) -> str:
        """
        Build the Redis connection URL that workspace containers will use.

        Inside the Docker network, the Redis host is the container name
        (e.g. 'ntr_redis') rather than 'localhost'.
        """
        host = os.getenv("WORKSPACE_REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
        port = os.getenv("REDIS_PORT", "6379")
        password = os.getenv("REDIS_PASSWORD", "ntr_redis_2026")
        db = os.getenv("REDIS_DB", "0")
        return f"redis://:{password}@{host}:{port}/{db}"

    def _ensure_network(self) -> None:
        """Create the shared Docker network if it does not already exist."""
        try:
            self._client.networks.get(DOCKER_NETWORK_NAME)
            logger.debug("Docker network '%s' exists ✓", DOCKER_NETWORK_NAME)
        except NotFound:
            logger.info("Creating Docker network '%s'", DOCKER_NETWORK_NAME)
            self._client.networks.create(DOCKER_NETWORK_NAME, driver="bridge")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_workspace_environment(self, workspace_id: str) -> dict[str, Any]:
        """
        Spin up an isolated Docker container for the given workspace.

        The container:
          • Runs the Data Plane image (configurable via WORKSPACE_CONTAINER_IMAGE)
          • Receives WORKSPACE_ID, DATABASE_URL, and REDIS_URL as env vars
          • Is attached to the shared Docker network for DB/Redis access
          • Is named deterministically: ``sf-workspace-<workspace_id>``

        Returns a dict with container metadata (id, name, status, ports).

        Raises:
            RuntimeError: if a container for this workspace is already running.
        """
        container_name = _container_name(workspace_id)
        image = os.getenv("WORKSPACE_CONTAINER_IMAGE", DEFAULT_CONTAINER_IMAGE)

        # Check if a container already exists for this workspace
        try:
            existing = self._client.containers.get(container_name)
            if existing.status == "running":
                raise RuntimeError(
                    f"Container '{container_name}' is already running "
                    f"(status={existing.status}, id={existing.short_id})"
                )
            # Container exists but is stopped — remove it before recreating
            logger.info(
                "Removing stopped container '%s' (status=%s) before restart",
                container_name, existing.status,
            )
            existing.remove(force=True)
        except NotFound:
            pass  # No existing container — proceed to create

        # Ensure the shared network exists
        self._ensure_network()

        # Build environment variables for the Data Plane
        env_vars = {
            "WORKSPACE_ID": str(workspace_id),
            "DATABASE_URL": self._build_database_url(),
            "REDIS_URL": self._build_redis_url(),
        }

        # Pull image if not available locally
        try:
            self._client.images.get(image)
            logger.debug("Image '%s' found locally ✓", image)
        except ImageNotFound:
            logger.info("Pulling image '%s' (this may take a moment)...", image)
            self._client.images.pull(image)

        # Create and start the container
        logger.info(
            "Starting workspace container '%s' with image '%s'",
            container_name, image,
        )

        container = self._client.containers.run(
            image=image,
            name=container_name,
            environment=env_vars,
            network=DOCKER_NETWORK_NAME,
            detach=True,
            # Keep the container alive with a long-running process.
            # In production, this would be replaced with the actual
            # Data Plane entrypoint (e.g. `python -m data_plane.main`).
            command="tail -f /dev/null",
            labels={
                "synapse-forge.role": "data-plane",
                "synapse-forge.workspace-id": str(workspace_id),
            },
            restart_policy={"Name": "unless-stopped"},
        )

        container.reload()  # Refresh state after start

        result = {
            "container_id": container.short_id,
            "container_name": container.name,
            "status": container.status,
            "image": image,
            "workspace_id": str(workspace_id),
        }
        logger.info("Workspace container started: %s", result)
        return result

    def stop_workspace_environment(self, workspace_id: str) -> dict[str, Any]:
        """
        Gracefully stop and remove the Docker container for a workspace.

        Sends SIGTERM first (10s timeout), then SIGKILL if still running.

        Returns a dict confirming the teardown.

        Raises:
            RuntimeError: if no container is found for this workspace.
        """
        container_name = _container_name(workspace_id)

        try:
            container = self._client.containers.get(container_name)
        except NotFound:
            raise RuntimeError(
                f"No container found for workspace '{workspace_id}' "
                f"(expected name: '{container_name}')"
            )

        logger.info(
            "Stopping workspace container '%s' (status=%s)",
            container_name, container.status,
        )

        # Graceful stop with 10-second timeout, then force remove
        container.stop(timeout=10)
        container.remove(force=True)

        result = {
            "container_name": container_name,
            "workspace_id": str(workspace_id),
            "action": "stopped_and_removed",
        }
        logger.info("Workspace container removed: %s", result)
        return result

    def get_container_status(self, workspace_id: str) -> dict[str, Any] | None:
        """
        Inspect the container for a workspace.

        Returns container info dict, or None if no container exists.
        """
        container_name = _container_name(workspace_id)

        try:
            container = self._client.containers.get(container_name)
            container.reload()
            return {
                "container_id": container.short_id,
                "container_name": container.name,
                "status": container.status,
                "image": container.image.tags[0] if container.image.tags else "unknown",
                "workspace_id": str(workspace_id),
            }
        except NotFound:
            return None

    def cleanup(self) -> None:
        """Close the Docker client connection."""
        if self._client:
            self._client.close()
