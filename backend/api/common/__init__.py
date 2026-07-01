"""
api.common
~~~~~~~~~~
Shared utilities used across all domain packages.
"""
from api.common.utils import (
    model_from_doc,
    get_workspace_or_404,
    sse_event,
    generate_embedding,
    safe_json,
    utc_iso,
)

__all__ = [
    "model_from_doc",
    "get_workspace_or_404",
    "sse_event",
    "generate_embedding",
    "safe_json",
    "utc_iso",
]
