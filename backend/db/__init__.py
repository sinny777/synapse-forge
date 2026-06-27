"""
SynapseForge — Database Package

Provides the MongoDB client lifecycle, Redis connection pool, and document
models for the Phase 1 MongoDB migration.
"""

from db.engine import (
    get_database,
    get_db,
    init_db,
    close_db,
    reset_db,
    prepare_document,
    normalize_mongo_document,
)
from db.redis_pool import (
    get_redis_pool,
    get_redis,
    init_redis,
    close_redis,
)
from db.models import (
    Workspace,
    Tool,
    Agent,
    Orchestration,
    LLMConfig,
    PipelineArtifact,
    WorkspaceStatus,
    ToolType,
    MCPTransportType,
    MCPServerStatus,
    OrchestrationFramework,
    ArchitectureType,
    LLMProviderEnum,
)

__all__ = [
    "get_database",
    "get_db",
    "init_db",
    "close_db",
    "reset_db",
    "prepare_document",
    "normalize_mongo_document",
    "get_redis_pool",
    "get_redis",
    "init_redis",
    "close_redis",
    "Workspace",
    "Tool",
    "Agent",
    "Orchestration",
    "LLMConfig",
    "PipelineArtifact",
    "WorkspaceStatus",
    "ToolType",
    "MCPTransportType",
    "MCPServerStatus",
    "OrchestrationFramework",
    "ArchitectureType",
    "LLMProviderEnum",
]

# Made with Bob
