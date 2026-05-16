"""
SynapseForge — Model Management API Routes

Endpoints for managing trained embedding model archives:
  • GET    /api/models              — list archived models
  • POST   /api/models/archive      — archive a trained model
  • DELETE /api/models/{model_name} — delete an archived model
"""

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger("ntr.api.models")

router = APIRouter(prefix="/api/models", tags=["Models"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ArchiveModelRequest(BaseModel):
    name: str
    version: str
    source_dir: str


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("")
async def list_models():
    """List all archived embedding models."""
    from tool_router.config import config

    models_dir = config.models_dir
    models = []
    if models_dir.exists():
        for item in models_dir.iterdir():
            if item.is_dir():
                models.append({"name": item.name, "path": str(item)})
    return {"status": "success", "models": models}


# ---------------------------------------------------------------------------
# ARCHIVE
# ---------------------------------------------------------------------------

@router.post("/archive")
async def archive_model(req: ArchiveModelRequest):
    """Copy a trained model directory into the models archive."""
    from tool_router.config import config

    models_dir = config.models_dir
    source_path = Path(req.source_dir)
    if not source_path.is_absolute():
        source_path = config.project_root / req.source_dir

    if not source_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source model directory not found",
        )

    target_name = f"{req.name}_v{req.version}"
    target_path = models_dir / target_name

    try:
        if target_path.exists():
            shutil.rmtree(target_path)
        shutil.copytree(source_path, target_path)
        return {
            "status": "success",
            "message": f"Model archived as {target_name}",
            "model_name": target_name,
        }
    except Exception as e:
        logger.error(f"Error archiving model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{model_name}")
async def delete_model(model_name: str):
    """Delete an archived model by name."""
    from tool_router.config import config

    models_dir = config.models_dir
    target_path = models_dir / model_name

    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found"
        )

    try:
        shutil.rmtree(target_path)
        return {"status": "success", "message": f"Model {model_name} deleted"}
    except Exception as e:
        logger.error(f"Error deleting model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
