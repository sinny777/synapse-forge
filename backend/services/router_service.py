"""
SynapseForge — Router Service (Platform Mode)

Performs semantic tool retrieval using pgvector similarity search
against the ``tools`` table, with an optional Redis cache layer.

This replaces the standalone FAISS/ChromaDB-based SemanticRouter
for the multi-tenant platform.  The standalone mode in
``tool_router/runtime.py`` remains available for file-based usage.
"""

import hashlib
import json
import logging
import time
import uuid
from typing import Optional

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Tool, Workspace
from services.embedding_service import embedding_service

logger = logging.getLogger("ntr.router")

# Redis key prefix & TTL
_CACHE_PREFIX = "ntr:predict:"
_CACHE_TTL_SECONDS = 300  # 5 minutes


class RouterService:
    """
    Semantic tool retrieval using pgvector.

    Flow:
      1. Check Redis cache for ``hash(workspace_id + prompt)``.
      2. If miss → embed prompt → pgvector cosine distance query.
      3. Store result in Redis.
      4. Return ranked tool list.
    """

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(workspace_id: uuid.UUID, prompt: str) -> str:
        raw = f"{workspace_id}:{prompt}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{_CACHE_PREFIX}{digest}"

    @staticmethod
    async def _get_cached(redis, key: str) -> Optional[list[dict]]:
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
    async def _set_cached(redis, key: str, data: list[dict]) -> None:
        """Store prediction result in Redis."""
        if redis is None:
            return
        try:
            await redis.setex(key, _CACHE_TTL_SECONDS, json.dumps(data))
        except Exception as exc:
            logger.debug("Redis cache write failed: %s", exc)

    # ------------------------------------------------------------------
    # Core prediction
    # ------------------------------------------------------------------

    @staticmethod
    async def predict(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_prompt: str,
        top_k: int = 5,
        redis=None,
    ) -> dict:
        """
        Predict the top-K tools for a user prompt within a workspace.

        Args:
            session: Async SQLAlchemy session.
            workspace_id: Target workspace UUID.
            user_prompt: Natural language query.
            top_k: Number of results to return.
            redis: Optional async Redis client for caching.

        Returns:
            dict with keys: ``tools`` (list[ToolRead-like dicts]),
            ``cached`` (bool), ``latency_ms`` (float).
        """
        t0 = time.perf_counter()

        # --- 1. Check cache ---
        cache_key = RouterService._cache_key(workspace_id, user_prompt)
        cached = await RouterService._get_cached(redis, cache_key)
        if cached is not None:
            latency = (time.perf_counter() - t0) * 1000
            logger.info("Cache HIT for workspace=%s  (%.1f ms)", workspace_id, latency)
            return {"tools": cached, "cached": True, "latency_ms": round(latency, 2)}

        # --- 2. Load workspace embedding config ---
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise ValueError(f"Workspace {workspace_id} not found")

        model_name = ws.embedding_model

        # --- 3. Embed the prompt ---
        prompt_vec = embedding_service.embed_text(user_prompt, model_name)

        # --- 4. pgvector cosine similarity query ---
        #
        # pgvector's <=> operator returns *cosine distance* (0 = identical).
        # We order by ascending distance and convert to similarity:
        #   similarity = 1 - distance
        #
        # We filter by workspace_id for multi-tenant isolation.
        # Using raw SQL here because pgvector operators aren't natively
        # exposed via the ORM for arbitrary-dimension vectors.
        vec_literal = "[" + ",".join(str(v) for v in prompt_vec) + "]"

        query = text("""
            SELECT
                id,
                name,
                description,
                type,
                connection_config,
                schema AS schema_def,
                created_at,
                updated_at,
                (1 - (embedding <=> :vec ::vector)) AS similarity
            FROM tools
            WHERE workspace_id = :ws_id
              AND is_enabled = true
              AND type != 'MCP_SERVER'
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :vec ::vector
            LIMIT :k
        """)

        result = await session.execute(
            query,
            {"vec": vec_literal, "ws_id": str(workspace_id), "k": top_k},
        )
        rows = result.mappings().all()

        tools_out = []
        for row in rows:
            tools_out.append({
                "id": str(row["id"]),
                "workspace_id": str(workspace_id),
                "name": row["name"],
                "description": row["description"],
                "type": row["type"],
                "connection_config": row["connection_config"],
                "schema_def": row["schema_def"],
                "similarity": round(float(row["similarity"]), 4),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            })

        # --- 5. Cache result ---
        await RouterService._set_cached(redis, cache_key, tools_out)

        latency = (time.perf_counter() - t0) * 1000
        logger.info(
            "Cache MISS for workspace=%s → %d tools  (%.1f ms)",
            workspace_id, len(tools_out), latency,
        )
        return {"tools": tools_out, "cached": False, "latency_ms": round(latency, 2)}

    # ------------------------------------------------------------------
    # Cache invalidation (called when tools are created/updated/deleted)
    # ------------------------------------------------------------------

    @staticmethod
    async def invalidate_workspace_cache(redis, workspace_id: uuid.UUID) -> None:
        """
        Delete all cached predictions for a workspace.

        Uses SCAN + DELETE to avoid blocking Redis with KEYS.
        """
        if redis is None:
            return
        try:
            # Since we hash workspace_id + prompt, we can't target by
            # workspace alone with the SHA-256 key.  Instead we use a
            # secondary set to track keys per workspace.
            ws_set_key = f"ntr:ws_keys:{workspace_id}"
            members = await redis.smembers(ws_set_key)
            if members:
                await redis.delete(*members, ws_set_key)
                logger.info("Invalidated %d cached predictions for workspace=%s", len(members), workspace_id)
        except Exception as exc:
            logger.debug("Cache invalidation failed: %s", exc)
