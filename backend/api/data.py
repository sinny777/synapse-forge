"""
SynapseForge — Data Management API Routes

Endpoints for synthetic training data and cached tool schema management:
  • GET/POST  /api/data/synthetic  — read/write synthetic query data
  • GET       /api/data/tools      — read cached MCP tool schemas
"""

import json
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("ntr.api.data")

router = APIRouter(prefix="/api/data", tags=["Data"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SyntheticDataUpdate(BaseModel):
    data: list


# ---------------------------------------------------------------------------
# SYNTHETIC DATA
# ---------------------------------------------------------------------------

@router.get("/synthetic")
async def get_synthetic_data():
    """Return the current synthetic training data (JSONL)."""
    from tool_router.config import config

    path = config.data_generation.output_path
    if not os.path.exists(path):
        return {"data": []}

    try:
        data = []
        with open(path, "r") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
        return {"data": data}
    except Exception as e:
        logger.error(f"Error reading synthetic data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/synthetic")
async def save_synthetic_data(update: SyntheticDataUpdate):
    """Overwrite the synthetic training data file."""
    from tool_router.config import config

    path = config.data_generation.output_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for item in update.data:
                f.write(json.dumps(item) + "\n")
        return {"status": "success", "message": "Synthetic data saved."}
    except Exception as e:
        logger.error(f"Error saving synthetic data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# TOOL CACHE
# ---------------------------------------------------------------------------

@router.get("/tools")
async def get_cached_tools():
    """Return the cached MCP tool schemas (id + name only)."""
    from tool_router.config import config

    path = config.mcp.tool_cache_path
    if not os.path.exists(path):
        return {"tools": []}

    try:
        with open(path, "r") as f:
            data = json.load(f)
            tools = [
                {"id": t["id"], "name": t.get("name", t["id"])}
                for t in data.get("tools", [])
            ]
            return {"tools": tools}
    except Exception as e:
        logger.error(f"Error reading tool cache: {e}")
        return {"tools": []}
