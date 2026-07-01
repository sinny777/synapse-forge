"""
api.common.utils
~~~~~~~~~~~~~~~~
Shared utility functions used across all API domain packages.

Every function here is pure (no side-effects on the database) or
is a thin, consistent wrapper so that each domain package does not
re-implement its own version.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.engine import normalize_mongo_document
from db.models import Workspace
from services.embedding_service import embedding_service

T = TypeVar("T")


# ---------------------------------------------------------------------------
# MongoDB document helpers
# ---------------------------------------------------------------------------

def model_from_doc(document: dict | None, model_class: Type[T]) -> T | None:
    """
    Convert a raw MongoDB document into a Pydantic model instance.

    Applies ``normalize_mongo_document`` (converts ``_id`` → ``id``) then
    validates against *model_class*.  Returns ``None`` when the document is
    ``None`` or empty.
    """
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return model_class.model_validate(normalized)


async def get_workspace_or_404(
    db: AsyncIOMotorDatabase,
    workspace_id: Any,
) -> Workspace:
    """
    Fetch a workspace document by ID or raise HTTP 404.

    *workspace_id* is stringified before querying so callers can pass a
    ``uuid.UUID`` or a plain string interchangeably.
    """
    document = await db.workspaces.find_one({"_id": str(workspace_id)})
    workspace = model_from_doc(document, Workspace)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


# ---------------------------------------------------------------------------
# SSE formatting
# ---------------------------------------------------------------------------

def sse_event(
    event_type: str,
    label: str,
    detail: str = "",
    *,
    status_value: str = "success",
    latency_ms: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Format a single Server-Sent Events data frame.

    The returned string is ready to be ``yield``-ed directly from a
    ``StreamingResponse`` generator.
    """
    payload: dict[str, Any] = {
        "type": event_type,
        "label": label,
        "detail": detail,
        "timestamp": utc_iso(),
        "status": status_value,
    }
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    if metadata:
        payload["metadata"] = metadata
        payload["data"] = metadata
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------

def generate_embedding(
    ws: Workspace,
    name: str,
    description: str | None,
    schema_def: dict | None,
) -> list[float]:
    """
    Generate a tool/agent embedding using the workspace's configured model.

    Delegates to :class:`services.embedding_service.EmbeddingService`.
    """
    return embedding_service.embed_tool(
        name=name,
        description=description,
        schema_def=schema_def,
        model_name=ws.embedding_model,
    )


# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------

def safe_json(value: Any) -> str:
    """Serialize *value* to a JSON string; falls back to ``str()`` on error."""
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def utc_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
