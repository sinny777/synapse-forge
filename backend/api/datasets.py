"""
SynapseForge — Dataset Management API Routes

Endpoints for managing versioned training datasets:
  • GET    /api/datasets              — list archived datasets
  • POST   /api/datasets/archive      — archive a dataset
  • POST   /api/datasets/load         — load a dataset file
  • DELETE /api/datasets/{name}       — delete a dataset
"""

import json
import logging
import os
import shutil
from pathlib import Path

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

logger = logging.getLogger("ntr.api.datasets")

router = APIRouter(prefix="/api/datasets", tags=["Datasets"])


class ArchiveDatasetRequest(BaseModel):
    name: str
    version: str
    source_file: str


class LoadDatasetRequest(BaseModel):
    dataset_path: str


@router.get("")
async def list_datasets(workspace_id: Optional[str] = Query(None)):
    """List all archived datasets."""
    from tool_router.config import config
    datasets_dir = config.datasets_dir
    if workspace_id:
        datasets_dir = config.project_root / "data" / "workspaces" / workspace_id / "data" / "datasets"
    datasets = []
    if datasets_dir.exists():
        for item in datasets_dir.iterdir():
            if item.is_file() and item.suffix == ".jsonl":
                name_parts = item.stem.split("_v")
                if len(name_parts) == 2:
                    name, version = name_parts[0], name_parts[1]
                else:
                    name, version = item.stem, "1.0"
                datasets.append({"name": name, "version": version, "path": str(item)})
                
    # Also list versioned datasets registered in IBM COS
    if workspace_id:
        import uuid
        from db.engine import _session_factory
        from db.models import PipelineArtifact
        from sqlalchemy import select
        try:
            async with _session_factory() as session:
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == uuid.UUID(workspace_id),
                    PipelineArtifact.artifact_type == "dataset"
                )
                db_artifacts = (await session.execute(stmt)).scalars().all()
                
                # Avoid duplicates
                existing_names = {f"{d['name']}_v{d['version']}" for d in datasets}
                
                for art in db_artifacts:
                    name_parts = art.name.replace(".jsonl", "").split("_v")
                    if len(name_parts) == 2:
                        name, version = name_parts[0], name_parts[1]
                    else:
                        name, version = art.name.replace(".jsonl", ""), "1.0"
                    
                    full_name = f"{name}_v{version}"
                    if full_name not in existing_names:
                        datasets.append({"name": name, "version": version, "path": art.url})
        except Exception as e:
            logger.error(f"Error querying datasets from DB: {e}")
            
    return {"status": "success", "datasets": datasets}


@router.post("/archive")
async def archive_dataset(req: ArchiveDatasetRequest, workspace_id: Optional[str] = Query(None)):
    """Archive a dataset with versioned name."""
    from tool_router.config import config
    datasets_dir = config.datasets_dir
    if workspace_id:
        datasets_dir = config.project_root / "data" / "workspaces" / workspace_id / "data" / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    
    source_path = Path(req.source_file)
    if not source_path.is_absolute():
        source_path = config.project_root / req.source_file
        
    local_source_existed = source_path.exists()
    
    # If the source file is not found locally, try to pull it from IBM COS
    if not local_source_existed and workspace_id:
        import uuid
        from services.artifact_manager import ArtifactManager
        ws_uuid = uuid.UUID(workspace_id)
        
        # Determine the correct local path for the workspace
        workspace_data_dir = config.project_root / "data" / "workspaces" / workspace_id / "data"
        workspace_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Use the workspace-specific path for download
        local_download_path = workspace_data_dir / source_path.name
        
        # Pull generated synthetic queries dataset if that is what we are archiving
        # Try raw_dataset first (newly generated), then dataset (previously archived)
        downloaded = await ArtifactManager.download_file_if_needed(
            workspace_id=ws_uuid,
            phase="generate",
            artifact_type="raw_dataset",
            local_file_path=local_download_path
        )
        
        if not downloaded:
            # Fallback to checking for archived dataset
            downloaded = await ArtifactManager.download_file_if_needed(
                workspace_id=ws_uuid,
                phase="generate",
                artifact_type="dataset",
                local_file_path=local_download_path
            )
        if downloaded:
            logger.info(f"Successfully pulled source dataset from IBM COS: {local_download_path}")
            source_path = local_download_path
            local_source_existed = False  # Mark that we downloaded it
            
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source dataset file not found locally or in IBM COS")
        
    target_name = f"{req.name}_v{req.version}.jsonl"
    target_path = datasets_dir / target_name
    
    try:
        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        if source_path.exists() and source_path.resolve() == target_path.resolve():
            # If they match, upload and register
            if workspace_id:
                import uuid
                from services.artifact_manager import ArtifactManager
                cos_artifact = await ArtifactManager.upload_and_register_file(
                    workspace_id=uuid.UUID(workspace_id),
                    phase="generate",
                    artifact_type="dataset",
                    local_file_path=target_path
                )
                return {"status": "success", "message": f"Dataset already archived as {target_name} and synced to IBM COS",
                        "dataset_name": req.name, "dataset_path": cos_artifact.url if cos_artifact else str(target_path)}
                        
            return {"status": "success", "message": f"Dataset already archived as {target_name}",
                    "dataset_name": req.name, "dataset_path": str(target_path)}
        
        # Copy source to target
        if source_path.exists():
            shutil.copy2(source_path, target_path)
        else:
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        # Upload archived file to IBM COS and clean up
        cos_url = str(target_path)
        if workspace_id:
            import uuid
            from services.artifact_manager import ArtifactManager
            cos_artifact = await ArtifactManager.upload_and_register_file(
                workspace_id=uuid.UUID(workspace_id),
                phase="generate",
                artifact_type="dataset",
                local_file_path=target_path
            )
            if cos_artifact:
                cos_url = cos_artifact.url
                
            # Clean up the pulled source file if it was originally deleted
            if not local_source_existed and source_path.exists():
                os.remove(source_path)
                logger.info(f"Cleaned up temporary source copy at {source_path}")
                
        return {"status": "success", "message": f"Dataset archived and uploaded to IBM COS as {target_name}",
                "dataset_name": req.name, "dataset_path": cos_url}
    except Exception as e:
        logger.error(f"Error archiving dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load")
async def load_dataset(req: LoadDatasetRequest):
    """Load a specific dataset file."""
    path_str = req.dataset_path
    
    # Check if this is a COS URI
    if path_str.startswith("cos://"):
        from services.ibm_cos_service import cos_service
        try:
            # Parse cos://bucket/key/path/to/file.ext
            url_no_scheme = path_str.replace("cos://", "")
            parts = url_no_scheme.split("/")
            bucket = parts[0]
            key = "/".join(parts[1:])
            filename = parts[-1]
            
            temp_dir = Path("data/temp_cache")
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_temp_path = temp_dir / filename
            
            cos_service.download_file(
                object_key=key,
                local_path=local_temp_path,
                bucket_name=bucket
            )
            path = local_temp_path
        except Exception as e:
            logger.error(f"Failed to stream dataset from IBM COS: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to stream dataset from IBM COS: {e}")
    else:
        path = Path(path_str)
        if not path.is_absolute():
            from tool_router.config import config
            path = config.project_root / req.dataset_path
            
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dataset file not found")
    try:
        data = []
        with open(path, "r") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
                    
        # Clean up temporary cached files
        if path_str.startswith("cos://") and path.exists():
            os.remove(path)
            
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error loading dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{dataset_name}")
async def delete_dataset(dataset_name: str, workspace_id: Optional[str] = Query(None)):
    """Delete an archived dataset from local storage, IBM COS, and database."""
    from tool_router.config import config
    from services.ibm_cos_service import cos_service
    import uuid
    from db.engine import _session_factory
    from db.models import PipelineArtifact
    from sqlalchemy import select
    
    datasets_dir = config.datasets_dir
    if workspace_id:
        datasets_dir = config.project_root / "data" / "workspaces" / workspace_id / "data" / "datasets"
    
    deleted = False
    deleted_files = []
    
    # Delete local files
    if datasets_dir.exists():
        for item in datasets_dir.iterdir():
            if item.is_file() and item.stem.startswith(dataset_name):
                try:
                    os.remove(item)
                    deleted = True
                    deleted_files.append(item.name)
                    logger.info(f"Deleted local dataset file: {item}")
                except Exception as e:
                    logger.error(f"Error deleting local dataset {item}: {e}")
    
    # Delete from IBM COS and database if workspace_id is provided
    cos_deleted_count = 0
    if workspace_id:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            async with _session_factory() as session:
                # Find all dataset artifacts matching this name
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == ws_uuid,
                    PipelineArtifact.artifact_type == "dataset"
                )
                artifacts = (await session.execute(stmt)).scalars().all()
                
                for artifact in artifacts:
                    # Check if artifact name matches the dataset_name
                    artifact_base_name = artifact.name.replace(".jsonl", "").split("_v")[0]
                    if artifact_base_name == dataset_name:
                        try:
                            # Delete from COS
                            cos_service.delete_prefix(
                                key_prefix=artifact.cos_key,
                                bucket_name=artifact.cos_bucket
                            )
                            logger.info(f"Deleted dataset from COS: {artifact.cos_key}")
                            
                            # Delete from database
                            await session.delete(artifact)
                            cos_deleted_count += 1
                            deleted = True
                        except Exception as cos_err:
                            logger.error(f"Error deleting dataset from COS: {cos_err}")
                
                await session.commit()
                
                if cos_deleted_count > 0:
                    logger.info(f"Deleted {cos_deleted_count} dataset artifact(s) from COS and database")
                
        except Exception as e:
            logger.error(f"Error deleting dataset from COS/DB: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete dataset from COS: {str(e)}")
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    return {
        "status": "success",
        "message": f"Dataset {dataset_name} deleted from local storage, IBM COS, and database",
        "deleted_files": deleted_files
    }
