"""
SynapseForge — Services Package

Business-logic services that sit between the API routes and the
database / cache layers.
"""

from services.embedding_service import EmbeddingService
from services.router_service import RouterService
from services.ibm_cos_service import IBMCOSService, cos_service
from services.artifact_manager import ArtifactManager

__all__ = [
    "EmbeddingService",
    "RouterService",
    "IBMCOSService",
    "cos_service",
    "ArtifactManager",
]

# WorkspaceDockerService is imported lazily (requires Docker daemon)
# from services.workspace_docker_service import WorkspaceDockerService

