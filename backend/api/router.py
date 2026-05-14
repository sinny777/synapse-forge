"""
NeuralToolRouter — Router Predict API Route

POST /api/router/predict — Semantic tool retrieval using pgvector.

Flow:
  1. Check Redis cache for hash(workspace_id + prompt).
  2. Embed the user prompt using the workspace's embedding model.
  3. Query pgvector for the top-K nearest tools by cosine similarity.
  4. Cache the result in Redis.
  5. Return the ranked tool list.
"""

import logging

from fastapi import APIRouter, HTTPException

from db.engine import AsyncSessionDep
from db.schemas import RouterPredictRequest, RouterPredictResponse, ToolRead
from services.router_service import RouterService

logger = logging.getLogger("ntr.api.router")

router = APIRouter(prefix="/api/router", tags=["Router"])


# ---------------------------------------------------------------------------
# Attempt to get the Redis client (optional dependency)
# ---------------------------------------------------------------------------

async def _get_redis_or_none():
    """
    Return the shared Redis client if available, or None.
    The router service degrades gracefully without Redis (no caching).
    """
    try:
        from db.redis_pool import _redis
        return _redis
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PREDICT
# ---------------------------------------------------------------------------

@router.post("/predict")
async def router_predict(body: RouterPredictRequest, session: AsyncSessionDep):
    """
    Semantic tool retrieval for a user prompt.

    Accepts a natural-language prompt and workspace_id, and returns
    the top-K most relevant tools from the workspace's pgvector index.

    Redis caching is used when available:
      - cache key: ``sha256(workspace_id + prompt)``
      - TTL: 5 minutes
    """
    redis = await _get_redis_or_none()

    try:
        result = await RouterService.predict(
            session=session,
            workspace_id=body.workspace_id,
            user_prompt=body.user_prompt,
            top_k=body.top_k,
            redis=redis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Router predict failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal router error")

    return result
