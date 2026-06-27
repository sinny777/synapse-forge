"""
SynapseForge — Async MongoDB Engine & Repository Helpers

Provides a Motor-based MongoDB client lifecycle plus a lightweight repository
API used during the Phase 1 migration away from PostgreSQL/SQLAlchemy.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger("ntr.db")

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def _build_mongodb_url() -> str:
    """
    Construct the MongoDB URL from environment variables.

    Expected env vars:
        MONGODB_URL
        MONGODB_HOST     (default: localhost)
        MONGODB_PORT     (default: 27017)
        MONGODB_USER     (optional)
        MONGODB_PASSWORD (optional)
        MONGODB_DATABASE (default: synapse_forge)
    """
    explicit_url = os.getenv("MONGODB_URL")
    if explicit_url:
        return explicit_url

    host = os.getenv("MONGODB_HOST", "localhost")
    port = os.getenv("MONGODB_PORT", "27017")
    user = os.getenv("MONGODB_USER", "")
    password = os.getenv("MONGODB_PASSWORD", "")
    database = os.getenv("MONGODB_DATABASE", "synapse_forge")
    auth_db = os.getenv("MONGODB_AUTH_DATABASE", "admin")

    if user and password:
        return f"mongodb://{user}:{password}@{host}:{port}/{database}?authSource={auth_db}"
    return f"mongodb://{host}:{port}/{database}"


async def init_db() -> None:
    """Initialise the shared MongoDB client and verify connectivity."""
    global _client, _database

    url = _build_mongodb_url()
    db_name = os.getenv("MONGODB_DATABASE", "synapse_forge")
    logger.info("Connecting to MongoDB at %s/%s", url.rsplit("/", 1)[0], db_name)

    client = AsyncIOMotorClient(url)
    await client.admin.command("ping")
    _client = client
    _database = client[db_name]

    await _ensure_indexes()
    logger.info("MongoDB connection verified ✓")


async def _ensure_indexes() -> None:
    """Create the minimum indexes required for Phase 1 CRUD behavior."""
    db = get_database()

    await db.workspaces.create_index("name", unique=True)
    await db.tools.create_index([("workspace_id", 1), ("name", 1)])
    await db.tools.create_index([("workspace_id", 1), ("parent_id", 1)])
    await db.agents.create_index([("workspace_id", 1), ("name", 1)])
    await db.orchestrations.create_index([("workspace_id", 1), ("name", 1)])
    await db.llm_configs.create_index([("workspace_id", 1), ("name", 1)])
    await db.pipeline_artifacts.create_index(
        [("workspace_id", 1), ("phase", 1), ("artifact_type", 1), ("name", 1)]
    )


async def reset_db() -> None:
    """Drop all application collections in MongoDB."""
    db = get_database()
    for collection_name in [
        "workspaces",
        "tools",
        "agents",
        "orchestrations",
        "llm_configs",
        "pipeline_artifacts",
    ]:
        await db[collection_name].drop()
    await _ensure_indexes()
    logger.warning("All MongoDB collections dropped and recreated.")


async def close_db() -> None:
    """Close the MongoDB client."""
    global _client, _database
    if _client is not None:
        _client.close()
        logger.info("Database connections closed.")
        _client = None
        _database = None


def get_database() -> AsyncIOMotorDatabase:
    """Return the current MongoDB database handle."""
    if _database is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _database


async def get_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """FastAPI dependency yielding the shared MongoDB database."""
    yield get_database()


def _normalize_id(value: Any) -> str:
    """Normalize IDs to string form for MongoDB documents."""
    return str(value)


def _serialize_for_mongo(value: Any) -> Any:
    """Recursively convert enums/UUID-like values into Mongo-safe primitives."""
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool, dict, list)):
        return value.value
    if isinstance(value, dict):
        return {key: _serialize_for_mongo(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_for_mongo(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_for_mongo(item) for item in value]
    if value.__class__.__name__ == "UUID":
        return str(value)
    return value


def prepare_document(payload: dict[str, Any]) -> dict[str, Any]:
    """Prepare a Pydantic payload for MongoDB persistence."""
    document = _serialize_for_mongo(payload)
    document["_id"] = _normalize_id(document["id"])
    return document


def normalize_mongo_document(document: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert MongoDB document shape into API/model shape."""
    if document is None:
        return None
    normalized = dict(document)
    mongo_id = normalized.pop("_id", None)
    if mongo_id is not None and "id" not in normalized:
        normalized["id"] = str(mongo_id)
    return normalized

# Made with Bob
