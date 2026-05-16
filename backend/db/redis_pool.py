"""
SynapseForge — Async Redis Connection Pool

Provides a shared ``redis.asyncio`` connection pool used for:
  • Router prediction caching  (hash(prompt + workspace_id) → tool schemas)
  • LangGraph session checkpointing

The pool is initialised / closed via FastAPI lifespan hooks.
"""

import os
import logging
from typing import AsyncGenerator, Annotated

import redis.asyncio as aioredis
from fastapi import Depends

logger = logging.getLogger("ntr.redis")

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_pool: aioredis.ConnectionPool | None = None
_redis: aioredis.Redis | None = None


def _build_redis_url() -> str:
    """
    Construct the Redis URL from environment variables.

    Expected env vars (defaults match docker-compose.yml):
        REDIS_HOST     (default: localhost)
        REDIS_PORT     (default: 6379)
        REDIS_PASSWORD (default: empty — no auth)
        REDIS_DB       (default: 0)
    """
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    password = os.getenv("REDIS_PASSWORD", "")
    db = os.getenv("REDIS_DB", "0")
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------

async def init_redis() -> None:
    """
    Create the async Redis connection pool.  Call once during startup.
    """
    global _pool, _redis

    url = os.getenv("REDIS_URL") or _build_redis_url()
    logger.info("Connecting to Redis at %s", url.split("@")[-1] if "@" in url else url)

    _pool = aioredis.ConnectionPool.from_url(
        url,
        max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
        decode_responses=True,
    )
    _redis = aioredis.Redis(connection_pool=_pool)

    # Smoke-test
    pong = await _redis.ping()
    if pong:
        logger.info("Redis connection verified ✓  (PONG)")
    else:
        logger.warning("Redis ping did not return expected PONG")


async def close_redis() -> None:
    """Close the Redis client and underlying pool."""
    global _pool, _redis
    if _redis is not None:
        await _redis.aclose()
        logger.info("Redis connection closed.")
        _redis = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


# ---------------------------------------------------------------------------
# Dependency injection helpers
# ---------------------------------------------------------------------------

def get_redis_pool() -> aioredis.ConnectionPool:
    """Return the current connection pool (raises if uninitialised)."""
    if _pool is None:
        raise RuntimeError("Redis not initialised. Call init_redis() first.")
    return _pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """
    FastAPI dependency that yields a shared ``Redis`` client.

    Usage::

        @app.get("/cached")
        async def cached_route(redis: RedisDep):
            val = await redis.get("my_key")
            ...
    """
    if _redis is None:
        raise RuntimeError("Redis not initialised. Call init_redis() first.")
    yield _redis


# Shorthand type alias for route signatures
RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]
