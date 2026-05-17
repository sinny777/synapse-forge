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

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
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
    workspace_id: Optional[str] = None


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("")
async def list_models(workspace_id: Optional[str] = Query(None)):
    """List all archived embedding models."""
    from tool_router.config import config

    models_dir = config.models_dir
    if workspace_id:
        models_dir = config.project_root / "data" / "workspaces" / workspace_id / "models"
    models = []
    if models_dir.exists():
        for item in models_dir.iterdir():
            if item.is_dir():
                models.append({"name": item.name, "path": str(item)})
                
    # Also list archived models stored in IBM COS
    # Include both archived_model and fine_tuned_model for backward compatibility
    # but exclude the temporary fine_tuned_tool_router directory
    if workspace_id:
        import uuid
        from db.engine import _session_factory
        from db.models import PipelineArtifact
        from sqlalchemy import select
        try:
            async with _session_factory() as session:
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == uuid.UUID(workspace_id),
                    PipelineArtifact.artifact_type.in_(["archived_model", "fine_tuned_model"]),
                    PipelineArtifact.name != "fine_tuned_tool_router"
                )
                db_artifacts = (await session.execute(stmt)).scalars().all()
                
                # Avoid duplicates
                existing_names = {m["name"] for m in models}
                for art in db_artifacts:
                    if art.name not in existing_names:
                        models.append({"name": art.name, "path": art.url})
        except Exception as e:
            logger.error(f"Error querying models from DB: {e}")
            
    return {"status": "success", "models": models}


# ---------------------------------------------------------------------------
# ARCHIVE
# ---------------------------------------------------------------------------

@router.post("/archive")
async def archive_model(req: ArchiveModelRequest, workspace_id: Optional[str] = Query(None)):
    """Copy a trained model directory into the models archive."""
    from tool_router.config import config

    ws_id = req.workspace_id or workspace_id
    models_dir = config.models_dir
    if ws_id:
        models_dir = config.project_root / "data" / "workspaces" / ws_id / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    
    source_path = Path(req.source_dir)
    if not source_path.is_absolute():
        source_path = config.project_root / req.source_dir

    local_source_existed = source_path.exists()
    
    # If the source model directory is not found locally, try to pull it from IBM COS
    if not local_source_existed and ws_id:
        import uuid
        from services.artifact_manager import ArtifactManager
        ws_uuid = uuid.UUID(ws_id)
        # Pull the base fine-tuned model from COS
        downloaded = await ArtifactManager.download_directory_if_needed(
            workspace_id=ws_uuid,
            phase="train",
            artifact_type="fine_tuned_model",
            local_dir_path=source_path,
            dir_name=source_path.name
        )
        if downloaded:
            logger.info(f"Successfully pulled source model from IBM COS: {source_path}")

    if not source_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source model directory not found locally or in IBM COS",
        )

    target_name = f"{req.name}_v{req.version}"
    target_path = models_dir / target_name

    try:
        if target_path.exists():
            shutil.rmtree(target_path)
        shutil.copytree(source_path, target_path)
        
        # Upload archived model directory to IBM COS and clean up
        cos_url = str(target_path)
        if ws_id:
            import uuid
            from services.artifact_manager import ArtifactManager
            cos_artifact = await ArtifactManager.upload_and_register_directory(
                workspace_id=uuid.UUID(ws_id),
                phase="train",
                artifact_type="archived_model",
                local_dir_path=target_path,
                dir_name=target_name
            )
            if cos_artifact:
                cos_url = cos_artifact.url
                
            # Clean up temporary source copy if we pulled it
            if not local_source_existed and source_path.exists():
                shutil.rmtree(source_path)
                logger.info(f"Cleaned up temporary source copy at {source_path}")
                
        return {
            "status": "success",
            "message": f"Model archived and uploaded to IBM COS as {target_name}",
            "model_name": target_name,
            "model_path": cos_url
        }
    except Exception as e:
        logger.error(f"Error archiving model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{model_name}")
async def delete_model(model_name: str, workspace_id: Optional[str] = Query(None)):
    """Delete an archived model by name."""
    from tool_router.config import config

    models_dir = config.models_dir
    if workspace_id:
        models_dir = config.project_root / "data" / "workspaces" / workspace_id / "models"
        
    target_path = models_dir / model_name
    local_existed = target_path.exists()

    cos_deleted = False
    if workspace_id:
        import uuid
        from db.engine import _session_factory
        from db.models import PipelineArtifact
        from sqlalchemy import select
        from services.ibm_cos_service import cos_service
        
        try:
            async with _session_factory() as session:
                # Try both archived_model and fine_tuned_model for backward compatibility
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == uuid.UUID(workspace_id),
                    PipelineArtifact.name == model_name,
                    PipelineArtifact.artifact_type.in_(["archived_model", "fine_tuned_model"])
                )
                artifact = (await session.execute(stmt)).scalars().first()
                if artifact:
                    cos_service.delete_prefix(artifact.cos_key, bucket_name=artifact.cos_bucket)
                    await session.delete(artifact)
                    await session.commit()
                    cos_deleted = True
                    logger.info(f"Deleted model {model_name} (type: {artifact.artifact_type}) from IBM COS and database.")
        except Exception as e:
            logger.error(f"Error deleting model from IBM COS: {e}")

    if not local_existed and not cos_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found locally or in IBM COS"
        )

    try:
        if local_existed:
            shutil.rmtree(target_path)
        return {"status": "success", "message": f"Model {model_name} deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting local model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
