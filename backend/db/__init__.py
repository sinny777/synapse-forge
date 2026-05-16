"""
SynapseForge — Database Package

Provides async SQLAlchemy engine, session factory, Redis connection pool,
and all ORM models for the Agentic AI Platform.
"""

from db.engine import (
    get_async_engine,
    get_async_session,
    AsyncSessionDep,
    init_db,
    close_db,
    reset_db,
)
from db.redis_pool import (
    get_redis_pool,
    get_redis,
    init_redis,
    close_redis,
)
from db.models import Base, Workspace, Tool, Agent, Orchestration, WorkspaceStatus

__all__ = [
    # Engine / Sessions
    "get_async_engine",
    "get_async_session",
    "AsyncSessionDep",
    "init_db",
    "close_db",
    # Redis
    "get_redis_pool",
    "get_redis",
    "init_redis",
    "close_redis",
    # DB Reset
    "reset_db",
    # ORM Models
    "Base",
    "Workspace",
    "Tool",
    "Agent",
    "Orchestration",
    "WorkspaceStatus",
]
