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

from fastapi import APIRouter, HTTPException, status
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
async def list_datasets():
    """List all archived datasets."""
    from tool_router.config import config
    datasets_dir = config.datasets_dir
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
    return {"status": "success", "datasets": datasets}


@router.post("/archive")
async def archive_dataset(req: ArchiveDatasetRequest):
    """Archive a dataset with versioned name."""
    from tool_router.config import config
    datasets_dir = config.datasets_dir
    datasets_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(req.source_file)
    if not source_path.is_absolute():
        source_path = config.project_root / req.source_file
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source dataset file not found")
    target_name = f"{req.name}_v{req.version}.jsonl"
    target_path = datasets_dir / target_name
    try:
        if source_path.resolve() == target_path.resolve():
            return {"status": "success", "message": f"Dataset already archived as {target_name}",
                    "dataset_name": req.name, "dataset_path": str(target_path)}
        shutil.copy2(source_path, target_path)
        return {"status": "success", "message": f"Dataset archived as {target_name}",
                "dataset_name": req.name, "dataset_path": str(target_path)}
    except Exception as e:
        logger.error(f"Error archiving dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load")
async def load_dataset(req: LoadDatasetRequest):
    """Load a specific dataset file."""
    path = Path(req.dataset_path)
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
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error loading dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{dataset_name}")
async def delete_dataset(dataset_name: str):
    """Delete an archived dataset."""
    from tool_router.config import config
    datasets_dir = config.datasets_dir
    deleted = False
    for item in datasets_dir.iterdir():
        if item.is_file() and item.stem.startswith(dataset_name):
            try:
                os.remove(item)
                deleted = True
            except Exception as e:
                logger.error(f"Error deleting dataset {item}: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "success", "message": f"Dataset {dataset_name} deleted"}
