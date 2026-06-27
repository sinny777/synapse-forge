"""
SynapseForge — Router Service (Platform Mode)

Performs semantic tool retrieval from MongoDB-stored embeddings with an optional
Redis cache layer. This is an interim Phase 1 implementation until Milvus-backed
vector search is wired in.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
import uuid
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from db.engine import normalize_mongo_document
from db.models import Tool, ToolType, Workspace
from services.embedding_service import embedding_service

logger = logging.getLogger("ntr.router")

_CACHE_PREFIX = "ntr:predict:"
_CACHE_TTL_SECONDS = 300


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class RouterService:
    """Semantic tool retrieval using MongoDB documents and in-app similarity."""

    @staticmethod
    def _cache_key(workspace_id: uuid.UUID | str, prompt: str) -> str:
        raw = f"{workspace_id}:{prompt}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{_CACHE_PREFIX}{digest}"

    @staticmethod
    async def _get_cached(redis, key: str) -> list[dict[str, Any]] | None:
        """Attempt to read cached prediction from Redis."""
        if redis is None:
            return None
        try:
            raw = await redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("Redis cache read failed: %s", exc)
        return None

    @staticmethod
    async def _set_cached(redis, key: str, data: list[dict[str, Any]]) -> None:
        """Store prediction result in Redis."""
        if redis is None:
            return
        try:
            await redis.setex(key, _CACHE_TTL_SECONDS, json.dumps(data))
        except Exception as exc:
            logger.debug("Redis cache write failed: %s", exc)

    @staticmethod
    async def predict(
        db: AsyncIOMotorDatabase,
        workspace_id: uuid.UUID | str,
        user_prompt: str,
        top_k: int = 5,
        redis=None,
    ) -> dict[str, Any]:
        """
        Predict the top-K tools for a user prompt within a workspace.

        Phase 1 note:
        This uses embeddings stored on tool documents and computes cosine
        similarity in application code. Milvus integration will replace this.
        """
        t0 = time.perf_counter()
        workspace_key = str(workspace_id)

        cache_key = RouterService._cache_key(workspace_key, user_prompt)
        cached = await RouterService._get_cached(redis, cache_key)
        if cached is not None:
            latency = (time.perf_counter() - t0) * 1000
            logger.info("Cache HIT for workspace=%s (%.1f ms)", workspace_key, latency)
            return {"tools": cached, "cached": True, "latency_ms": round(latency, 2)}

        workspace_doc = await db.workspaces.find_one({"_id": workspace_key})
        workspace_data = normalize_mongo_document(workspace_doc)
        if workspace_data is None:
            raise ValueError(f"Workspace {workspace_key} not found")

        workspace = Workspace.model_validate(workspace_data)
        prompt_vec = embedding_service.embed_text(user_prompt, workspace.embedding_model)

        cursor = db.tools.find(
            {
                "workspace_id": workspace_key,
                "is_enabled": True,
                "embedding": {"$ne": None},
                "type": {"$ne": ToolType.MCP_SERVER.value},
            }
        )

        ranked_tools: list[dict[str, Any]] = []
        async for document in cursor:
            tool_data = normalize_mongo_document(document)
            if tool_data is None:
                continue

            tool = Tool.model_validate(tool_data)
            if not tool.embedding:
                continue

            similarity = _cosine_similarity(prompt_vec, tool.embedding)
            ranked_tools.append(
                {
                    "id": str(tool.id),
                    "workspace_id": tool.workspace_id,
                    "name": tool.name,
                    "description": tool.description,
                    "type": tool.type.value,
                    "connection_config": tool.connection_config,
                    "schema_def": tool.schema_def,
                    "similarity": round(float(similarity), 4),
                    "created_at": tool.created_at.isoformat() if tool.created_at else None,
                    "updated_at": tool.updated_at.isoformat() if tool.updated_at else None,
                }
            )

        ranked_tools.sort(key=lambda item: item["similarity"], reverse=True)
        tools_out = ranked_tools[:top_k]

        await RouterService._set_cached(redis, cache_key, tools_out)

        latency = (time.perf_counter() - t0) * 1000
        logger.info(
            "Cache MISS for workspace=%s → %d tools (%.1f ms)",
            workspace_key,
            len(tools_out),
            latency,
        )
        return {"tools": tools_out, "cached": False, "latency_ms": round(latency, 2)}

    @staticmethod
    async def invalidate_workspace_cache(redis, workspace_id: uuid.UUID | str) -> None:
        """Delete cached predictions for a workspace when tracking keys is available."""
        if redis is None:
            return
        try:
            ws_set_key = f"ntr:ws_keys:{workspace_id}"
            members = await redis.smembers(ws_set_key)
            if members:
                await redis.delete(*members, ws_set_key)
                logger.info(
                    "Invalidated %d cached predictions for workspace=%s",
                    len(members),
                    workspace_id,
                )
        except Exception as exc:
            logger.debug("Cache invalidation failed: %s", exc)
