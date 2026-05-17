"""
SynapseForge — Data Management API Routes

Endpoints for synthetic training data and cached tool schema management:
  • GET/POST  /api/data/synthetic  — read/write synthetic query data
  • GET       /api/data/tools      — read cached MCP tool schemas
"""

import json
import logging
import os

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
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
async def get_synthetic_data(workspace_id: Optional[str] = Query(None)):
    """Return the current synthetic training data (JSONL)."""
    from tool_router.config import config

    path = config.data_generation.output_path
    if workspace_id:
        path = config.project_root / "data" / "workspaces" / workspace_id / "data" / "synthetic_queries.jsonl"
        
        # Download from IBM COS on demand if not present locally
        import uuid
        from services.artifact_manager import ArtifactManager
        await ArtifactManager.download_file_if_needed(
            workspace_id=uuid.UUID(workspace_id),
            phase="generate",
            artifact_type="dataset",
            local_file_path=path
        )

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
    finally:
        # Clean up local file copy if it was downloaded/created locally to ensure no files are stored on local filesystem
        if workspace_id and os.path.exists(path):
            try:
                import uuid
                from services.artifact_manager import ArtifactManager
                os.remove(path)
                logger.info(f"✓ Cleaned up local copy of downloaded synthetic data at {path}")
                ArtifactManager.cleanup_empty_workspace_directories(uuid.UUID(workspace_id))
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up synthetic data local file or dirs: {cleanup_err}")


@router.post("/synthetic")
async def save_synthetic_data(update: SyntheticDataUpdate, workspace_id: Optional[str] = Query(None)):
    """Overwrite the synthetic training data file."""
    from tool_router.config import config

    path = config.data_generation.output_path
    if workspace_id:
        path = config.project_root / "data" / "workspaces" / workspace_id / "data" / "synthetic_queries.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for item in update.data:
                f.write(json.dumps(item) + "\n")
                
        # Upload to IBM COS and clean up local copy immediately
        if workspace_id:
            import uuid
            from services.artifact_manager import ArtifactManager
            await ArtifactManager.upload_and_register_file(
                workspace_id=uuid.UUID(workspace_id),
                phase="generate",
                artifact_type="dataset",
                local_file_path=path
            )
            try:
                ArtifactManager.cleanup_empty_workspace_directories(uuid.UUID(workspace_id))
            except:
                pass
            
        return {"status": "success", "message": "Synthetic data saved and synced to IBM COS."}
    except Exception as e:
        logger.error(f"Error saving synthetic data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# TOOL CACHE
# ---------------------------------------------------------------------------

@router.get("/tools")
async def get_cached_tools(workspace_id: Optional[str] = Query(None)):
    """Return the cached MCP tool schemas (id + name only)."""
    from tool_router.config import config

    path = config.mcp.tool_cache_path
    if workspace_id:
        path = config.project_root / "data" / "workspaces" / workspace_id / "data" / "tool_cache.json"
        
        # Download from IBM COS on demand if not present locally
        import uuid
        from services.artifact_manager import ArtifactManager
        await ArtifactManager.download_file_if_needed(
            workspace_id=uuid.UUID(workspace_id),
            phase="generate",
            artifact_type="tool_cache",
            local_file_path=path
        )

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
    finally:
        # Clean up local file copy if it was downloaded/created locally to ensure no files are stored on local filesystem
        if workspace_id and os.path.exists(path):
            try:
                import uuid
                from services.artifact_manager import ArtifactManager
                os.remove(path)
                logger.info(f"✓ Cleaned up local copy of downloaded tool cache at {path}")
                ArtifactManager.cleanup_empty_workspace_directories(uuid.UUID(workspace_id))
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up tool cache local file or dirs: {cleanup_err}")
