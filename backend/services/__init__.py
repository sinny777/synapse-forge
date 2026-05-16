"""
SynapseForge — Services Package

Business-logic services that sit between the API routes and the
database / cache layers.
"""

from services.embedding_service import EmbeddingService
from services.router_service import RouterService

__all__ = [
    "EmbeddingService",
    "RouterService",
]

# WorkspaceDockerService is imported lazily (requires Docker daemon)
# from services.workspace_docker_service import WorkspaceDockerService

