"""
SynapseForge — Router Predict API Route

POST /api/router/predict — semantic tool retrieval using MongoDB-stored
embeddings during Phase 1, to be replaced by Milvus-backed search later.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.engine import get_db
from db.schemas import RouterPredictRequest
from services.router_service import RouterService

logger = logging.getLogger("ntr.api.router")

router = APIRouter(prefix="/api/router", tags=["SynapseForge"])


async def _get_redis_or_none():
    """Return the shared Redis client if available, or None."""
    try:
        from db.redis_pool import _redis
        return _redis
    except Exception:
        return None


@router.post("/predict")
async def router_predict(
    body: RouterPredictRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Semantic tool retrieval for a user prompt.

    Accepts a natural-language prompt and workspace_id, and returns
    the top-K most relevant tools from the workspace's current embedding index.
    """
    redis = await _get_redis_or_none()

    try:
        result = await RouterService.predict(
            db=db,
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
