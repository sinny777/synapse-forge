"""
SynapseForge — Execution domain: shared helpers.
"""


async def _get_redis_or_none():
    """Return the shared Redis client if available, or None."""
    try:
        from db.redis_pool import _redis
        return _redis
    except Exception:
        return None
