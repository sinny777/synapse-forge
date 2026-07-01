"""
api.neural_router_pipeline.router
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Route handlers for the NTR pipeline domain.

Combines:
  • workflow/  — /api/generate, /api/train, /api/run, /api/evaluate, /api/status
  • data/      — /api/data/synthetic, /api/data/tools
  • datasets/  — /api/datasets
  • model_registry/ — /api/models
  • scenarios/ — /api/agents/scenarios, /api/agents/execute
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from api.neural_router_pipeline.helpers import (
    ensure_run_artifacts_downloaded,
    update_global_config,
)
from api.neural_router_pipeline.schemas import (
    AgentExecuteRequest,
    ArchiveDatasetRequest,
    ArchiveModelRequest,
    EvaluateConfig,
    GenerateConfig,
    LoadDatasetRequest,
    RunConfig,
    SyntheticDataUpdate,
    TrainConfig,
)

logger = logging.getLogger("ntr.api.neural_router_pipeline")

router = APIRouter(tags=["SynapseForge_Workflow"])


# ===========================================================================
# STATUS
# ===========================================================================

@router.get("/api/status")
async def get_status():
    """Return current pipeline status."""
    from tool_router.status_tracker import get_status as _get_status
    return _get_status()


# ===========================================================================
# GENERATE
# ===========================================================================

@router.post("/api/generate")
async def generate_phase(config_data: GenerateConfig):
    """Run the synthetic data generation phase."""
    from tool_router.status_tracker import update_status, reset_status

    reset_status()
    update_status(phase="generate", status="running", progress=0.0, message="Initializing generation phase...")
    try:
        teacher_model_str = config_data.teacher_model
        if teacher_model_str:
            import uuid as _uuid
            from db.engine import get_database, normalize_mongo_document
            from db.models import LLMConfig

            is_uuid = False
            try:
                _uuid.UUID(str(teacher_model_str))
                is_uuid = True
            except ValueError:
                pass

            if is_uuid:
                db = get_database()
                config_doc = await db.llm_configs.find_one({"_id": str(teacher_model_str)})
                config_data_doc = normalize_mongo_document(config_doc)
                config_row = LLMConfig(**config_data_doc) if config_data_doc else None
                if config_row:
                    provider = config_row.provider.value
                    model_name = config_row.model_name
                    credentials = config_row.credentials or {}

                    logger.info(
                        "Using selected LLM Config '%s' (provider: %s, model: %s) for Phase 1 generation.",
                        config_row.name, provider, model_name,
                    )

                    if provider == "ibm_watsonx":
                        api_key = credentials.get("api_key") or credentials.get("apikey")
                        project_id = credentials.get("project_id")
                        region = credentials.get("region", "us-south")
                        if api_key:
                            os.environ["WATSONX_APIKEY"] = api_key
                            os.environ["WATSONX_API_KEY"] = api_key
                        if project_id:
                            os.environ["WATSONX_PROJECT_ID"] = project_id
                        if region:
                            os.environ["WATSONX_URL"] = region if region.startswith("http") else f"https://{region}.ml.cloud.ibm.com"
                            os.environ["WATSONX_REGION"] = region
                        config_data.teacher_model = f"watsonx/{model_name}"
                    elif provider == "openai":
                        api_key = credentials.get("api_key") or credentials.get("apikey")
                        api_base = credentials.get("api_base") or credentials.get("url")
                        if api_key:
                            os.environ["OPENAI_API_KEY"] = api_key
                        if api_base:
                            os.environ["OPENAI_API_BASE"] = api_base
                        config_data.teacher_model = f"openai/{model_name}"
                    elif provider == "ollama":
                        api_base = credentials.get("api_base") or credentials.get("url")
                        if api_base:
                            os.environ["OLLAMA_API_BASE"] = api_base
                        config_data.teacher_model = f"ollama/{model_name}"
                    elif provider == "anthropic":
                        api_key = credentials.get("api_key") or credentials.get("apikey")
                        if api_key:
                            os.environ["ANTHROPIC_API_KEY"] = api_key
                        config_data.teacher_model = f"anthropic/{model_name}"
                    elif provider == "google":
                        api_key = credentials.get("api_key") or credentials.get("apikey")
                        if api_key:
                            os.environ["GEMINI_API_KEY"] = api_key
                        config_data.teacher_model = f"gemini/{model_name}"
                    elif provider == "groq":
                        api_key = credentials.get("api_key") or credentials.get("apikey")
                        if api_key:
                            os.environ["GROQ_API_KEY"] = api_key
                        config_data.teacher_model = f"groq/{model_name}"
                    else:
                        config_data.teacher_model = f"{provider}/{model_name}"
                else:
                    logger.warning(
                        "Selected LLM Config with ID %s not found in database. Using default/fallback model.",
                        teacher_model_str,
                    )

        update_global_config(config_data, "generate")
        from tool_router.generator import main as phase1_main
        await phase1_main()

        ws_id = getattr(config_data, "workspace_id", None)
        if ws_id:
            import uuid as _uuid
            from services.artifact_manager import ArtifactManager
            from tool_router.config import config as tr_config

            ws_uuid = _uuid.UUID(str(ws_id))
            update_status(status="running", progress=0.96, message="Uploading artifacts to IBM Cloud Object Storage...")

            output_path = Path(tr_config.data_generation.output_path)
            await ArtifactManager.upload_and_register_file(
                workspace_id=ws_uuid, phase="generate", artifact_type="raw_dataset", local_file_path=output_path,
            )

            tool_cache_path = Path(tr_config.mcp.tool_cache_path)
            await ArtifactManager.upload_and_register_file(
                workspace_id=ws_uuid, phase="generate", artifact_type="tool_cache", local_file_path=tool_cache_path,
            )

            try:
                ArtifactManager.cleanup_empty_workspace_directories(ws_uuid)
            except Exception as cleanup_err:
                logger.warning("Failed to clean up empty workspace directories: %s", cleanup_err)

        update_status(status="completed", progress=1.0, message="Generation phase completed successfully. Artifacts uploaded to IBM COS.")
        return {"status": "success", "message": "Generation phase completed."}

    except Exception as exc:
        ws_id = getattr(config_data, "workspace_id", None)
        if ws_id:
            try:
                import uuid as _uuid
                from services.artifact_manager import ArtifactManager
                ArtifactManager.cleanup_empty_workspace_directories(_uuid.UUID(str(ws_id)))
            except Exception:
                pass
        update_status(status="error", message=f"Generation failed: {exc}")
        logger.error("Generate phase failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ===========================================================================
# TRAIN
# ===========================================================================

@router.get("/api/train/stream")
async def train_stream():
    """Server-Sent Events endpoint for real-time training progress."""
    from tool_router.status_tracker import add_listener, remove_listener, get_status as _get_status

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        def status_callback(status_data):
            try:
                asyncio.create_task(queue.put(status_data))
            except Exception:
                pass

        add_listener(status_callback)
        try:
            yield f"data: {json.dumps(_get_status().model_dump())}\n\n"
            while True:
                try:
                    status_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(status_data)}\n\n"
                    if status_data.get("status") in ("completed", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            remove_listener(status_callback)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/api/train")
async def train_phase(config_data: TrainConfig):
    """Start the embedding model training phase (runs in background thread)."""
    from tool_router.status_tracker import update_status, reset_status
    from tool_router.config import config

    reset_status()
    update_status(phase="train", status="running", progress=0.0, message="Initializing training phase...")

    workspace_id = getattr(config_data, "workspace_id", None)
    if workspace_id:
        import uuid as _uuid
        from services.artifact_manager import ArtifactManager

        update_global_config(config_data, "train")
        ws_uuid = _uuid.UUID(str(workspace_id))
        update_status(status="running", progress=0.05, message="Downloading training data and tool cache from IBM COS...")

        await ArtifactManager.download_file_if_needed(
            workspace_id=ws_uuid, phase="generate", artifact_type="tool_cache",
            local_file_path=config.mcp.tool_cache_path,
        )
        downloaded = await ArtifactManager.download_file_if_needed(
            workspace_id=ws_uuid, phase="generate", artifact_type="raw_dataset",
            local_file_path=config.training.training_data_path,
        )
        if not downloaded:
            await ArtifactManager.download_file_if_needed(
                workspace_id=ws_uuid, phase="generate", artifact_type="dataset",
                local_file_path=config.training.training_data_path,
            )

    def run_training():
        try:
            from tool_router.trainer import main as phase2_main
            phase2_main()

            source_path = config.embedding.fine_tuned_model_dir
            target_path = None
            target_name = None
            model_existed = False

            if source_path.exists():
                if config_data.archive_name and config_data.archive_version:
                    model_name_str = config_data.archive_name
                    version = config_data.archive_version
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    model_name_str = f"tool_router_{timestamp}"
                    version = "1.0"

                target_name = f"{model_name_str}_v{version}"
                target_path = config.models_dir / target_name

                try:
                    model_existed = target_path.exists()
                    if model_existed:
                        shutil.rmtree(target_path)
                    shutil.copytree(source_path, target_path)
                    if source_path.exists() and source_path != target_path:
                        shutil.rmtree(source_path)
                        logger.info("Cleaned up temporary training directory: %s", source_path)
                    action = "updated" if model_existed else "archived"
                    logger.info("Model %s as %s", action, target_name)
                except Exception as archive_error:
                    logger.warning("Training completed but archiving failed: %s", archive_error)
                    target_path = None

            if workspace_id:
                import uuid as _uuid
                from services.artifact_manager import ArtifactManager
                ws_uuid = _uuid.UUID(str(workspace_id))

                update_status(status="running", progress=0.95, message="Uploading model and retrieval indexes to IBM COS...")

                def upload_training_files_sync():
                    faiss_path = Path(config.vector_store.faiss_index_path)
                    if faiss_path.exists():
                        ArtifactManager.upload_and_register_file_sync(
                            workspace_id=ws_uuid, phase="train", artifact_type="faiss_index", local_file_path=faiss_path,
                        )
                        faiss_json = faiss_path.with_suffix(".json")
                        if faiss_json.exists():
                            ArtifactManager.upload_and_register_file_sync(
                                workspace_id=ws_uuid, phase="train", artifact_type="faiss_index_mapping", local_file_path=faiss_json,
                            )

                    bm25_path = faiss_path.parent / "bm25_index.pkl"
                    if bm25_path.exists():
                        ArtifactManager.upload_and_register_file_sync(
                            workspace_id=ws_uuid, phase="train", artifact_type="bm25_index", local_file_path=bm25_path,
                        )
                        bm25_json = bm25_path.with_suffix(".json")
                        if bm25_json.exists():
                            ArtifactManager.upload_and_register_file_sync(
                                workspace_id=ws_uuid, phase="train", artifact_type="bm25_index_mapping", local_file_path=bm25_json,
                            )

                    if target_path and target_path.exists() and target_name:
                        ArtifactManager.upload_and_register_directory_sync(
                            workspace_id=ws_uuid, phase="train", artifact_type="archived_model",
                            local_dir_path=target_path, dir_name=target_name,
                        )

                try:
                    upload_training_files_sync()
                except Exception as upload_err:
                    logger.error("Failed to upload training artifacts: %s", upload_err)
                    raise

                try:
                    for p in [config.mcp.tool_cache_path, config.training.training_data_path]:
                        file_path = Path(p)
                        if file_path.exists():
                            file_path.unlink()
                            logger.info("✓ Cleaned up local training input file: %s", file_path)
                except Exception as cleanup_err:
                    logger.warning("Failed to delete training input files: %s", cleanup_err)

                try:
                    ArtifactManager.cleanup_empty_workspace_directories(ws_uuid)
                except Exception as cleanup_err:
                    logger.warning("Failed to clean up empty workspace directories after training: %s", cleanup_err)

            if target_name:
                action = "updated" if model_existed else "archived"
                msg = f"Training completed. Model {action} as {target_name} and uploaded to IBM COS."
            else:
                msg = "Training phase completed successfully. Artifacts uploaded to IBM COS."
            update_status(status="completed", progress=1.0, message=msg)

        except Exception as exc:
            ws_id = getattr(config_data, "workspace_id", None)
            if ws_id:
                try:
                    import uuid as _uuid
                    from services.artifact_manager import ArtifactManager
                    ArtifactManager.cleanup_empty_workspace_directories(_uuid.UUID(str(ws_id)))
                except Exception:
                    pass
            update_status(status="error", message=f"Training failed: {exc}")
            logger.error("Train phase failed: %s", exc)

    training_thread = threading.Thread(target=run_training, daemon=True)
    training_thread.start()

    return {"status": "success", "message": "Training started. Use /api/train/stream for real-time updates."}


# ===========================================================================
# RUN
# ===========================================================================

@router.post("/api/run")
async def run_phase(config_data: RunConfig):
    """Run the agentic tool-routing loop (streaming NDJSON)."""
    try:
        update_global_config(config_data, "run")
        if config_data.workspace_id:
            model_name = Path(config_data.model_path).name if config_data.model_path else None
            await ensure_run_artifacts_downloaded(config_data.workspace_id, model_name)
        if config_data.model_path:
            from tool_router.config import config
            config.embedding.fine_tuned_model_dir = Path(config_data.model_path)

        from tool_router.runtime import ToolRouter

        async def event_generator():
            router_instance = ToolRouter()
            try:
                await router_instance.initialize()
                async for event in router_instance.process_query_stream(config_data.query):
                    yield event
            except Exception as exc:
                logger.error("Error in stream: %s", exc)
                yield json.dumps({"event": "error", "data": {"message": str(exc)}}) + "\n"
            finally:
                await router_instance.close()

        return StreamingResponse(event_generator(), media_type="application/x-ndjson")
    except Exception as exc:
        logger.error("Run phase failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ===========================================================================
# EVALUATE
# ===========================================================================

@router.post("/api/evaluate")
async def evaluate_phase(config_data: EvaluateConfig):
    """Evaluate the trained model against a query."""
    from tool_router.runtime import SemanticRouter
    from tool_router.config import config
    from tool_router.mcp_client import MCPClient
    from sentence_transformers import SentenceTransformer

    try:
        update_global_config(config_data, "evaluate")

        model_name = Path(config_data.model_path).name if config_data.model_path else None
        model_dir = await ensure_run_artifacts_downloaded(config_data.workspace_id, model_name)
        if model_dir is None:
            raise HTTPException(status_code=400, detail="workspace_id is required for evaluation")

        t0 = time.time()
        model = SentenceTransformer(str(model_dir), device=config.embedding.device)
        semantic_router = SemanticRouter(model, config.vector_store)

        if config.vector_store.store_type == "faiss":
            semantic_router.load_faiss_index()
        elif config.vector_store.store_type == "chromadb":
            semantic_router.load_chromadb_collection()

        try:
            semantic_router.load_bm25_index()
        except FileNotFoundError:
            pass

        retrieved_tools = semantic_router.retrieve_tools(
            config_data.query, top_k=config_data.top_k, use_hybrid=False, apply_threshold=False,
        )

        mcp_client = MCPClient(config.mcp)
        mcp_client.load_tool_cache(config.mcp.tool_cache_path)

        enriched_tools = []
        for tid, score in retrieved_tools:
            tool_schema = mcp_client.tools.get(tid)
            if tool_schema:
                enriched_tools.append({
                    "id": tid, "score": score, "name": tool_schema.name,
                    "description": tool_schema.description, "server_name": tool_schema.server_name,
                    "parameters": tool_schema.parameters,
                    "input_schema": tool_schema.raw_schema.get("inputSchema", {}),
                    "output_format": tool_schema.raw_schema.get("outputFormat", "Tool execution result"),
                })
            else:
                enriched_tools.append({
                    "id": tid, "score": score,
                    "name": tid.split(".")[-1] if "." in tid else tid,
                    "description": "Tool metadata not available", "server_name": "unknown",
                    "parameters": {}, "input_schema": {}, "output_format": "Tool execution result",
                })

        return {
            "status": "success",
            "message": "Evaluation completed.",
            "data": {"query": config_data.query, "retrieved_tools": enriched_tools, "time_taken": time.time() - t0},
        }
    except Exception as exc:
        logger.error("Evaluate phase failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ===========================================================================
# SYNTHETIC DATA  —  /api/data
# ===========================================================================

@router.get("/api/data/synthetic")
async def get_synthetic_data(workspace_id: Optional[str] = Query(None)):
    """Return the current synthetic training data (JSONL)."""
    from tool_router.config import config

    path = config.data_generation.output_path
    if workspace_id:
        path = config.project_root / "data" / "workspaces" / workspace_id / "data" / "synthetic_queries.jsonl"
        import uuid as _uuid
        from services.artifact_manager import ArtifactManager
        await ArtifactManager.download_file_if_needed(
            workspace_id=_uuid.UUID(workspace_id), phase="generate", artifact_type="dataset", local_file_path=path,
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
    except Exception as exc:
        logger.error("Error reading synthetic data: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if workspace_id and os.path.exists(path):
            try:
                import uuid as _uuid
                from services.artifact_manager import ArtifactManager
                os.remove(path)
                logger.info("✓ Cleaned up local copy of downloaded synthetic data at %s", path)
                ArtifactManager.cleanup_empty_workspace_directories(_uuid.UUID(workspace_id))
            except Exception as cleanup_err:
                logger.warning("Failed to clean up synthetic data local file or dirs: %s", cleanup_err)


@router.post("/api/data/synthetic")
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

        if workspace_id:
            import uuid as _uuid
            from services.artifact_manager import ArtifactManager
            await ArtifactManager.upload_and_register_file(
                workspace_id=_uuid.UUID(workspace_id), phase="generate", artifact_type="dataset", local_file_path=path,
            )
            try:
                ArtifactManager.cleanup_empty_workspace_directories(_uuid.UUID(workspace_id))
            except Exception:
                pass

        return {"status": "success", "message": "Synthetic data saved and synced to IBM COS."}
    except Exception as exc:
        logger.error("Error saving synthetic data: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/data/tools")
async def get_cached_tools(workspace_id: Optional[str] = Query(None)):
    """Return the cached MCP tool schemas (id + name only)."""
    from tool_router.config import config

    path = config.mcp.tool_cache_path
    if workspace_id:
        path = config.project_root / "data" / "workspaces" / workspace_id / "data" / "tool_cache.json"
        import uuid as _uuid
        from services.artifact_manager import ArtifactManager
        await ArtifactManager.download_file_if_needed(
            workspace_id=_uuid.UUID(workspace_id), phase="generate", artifact_type="tool_cache", local_file_path=path,
        )

    if not os.path.exists(path):
        return {"tools": []}

    try:
        with open(path, "r") as f:
            data = json.load(f)
            return {"tools": [{"id": t["id"], "name": t.get("name", t["id"])} for t in data.get("tools", [])]}
    except Exception as exc:
        logger.error("Error reading tool cache: %s", exc)
        return {"tools": []}
    finally:
        if workspace_id and os.path.exists(path):
            try:
                import uuid as _uuid
                from services.artifact_manager import ArtifactManager
                os.remove(path)
                logger.info("✓ Cleaned up local copy of downloaded tool cache at %s", path)
                ArtifactManager.cleanup_empty_workspace_directories(_uuid.UUID(workspace_id))
            except Exception as cleanup_err:
                logger.warning("Failed to clean up tool cache local file or dirs: %s", cleanup_err)


# ===========================================================================
# DATASETS  —  /api/datasets
# ===========================================================================

@router.get("/api/datasets")
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
                name, version = (name_parts[0], name_parts[1]) if len(name_parts) == 2 else (item.stem, "1.0")
                datasets.append({"name": name, "version": version, "path": str(item)})

    if workspace_id:
        from db.engine import get_database, normalize_mongo_document
        try:
            db = get_database()
            db_artifacts = await db.pipeline_artifacts.find(
                {"workspace_id": workspace_id, "artifact_type": "dataset"}
            ).to_list(length=None)

            existing_names = {f"{d['name']}_v{d['version']}" for d in datasets}
            for artifact_doc in db_artifacts:
                art = normalize_mongo_document(artifact_doc) or {}
                artifact_name = str(art.get("name", "")).replace(".jsonl", "")
                name_parts = artifact_name.split("_v")
                name, version = (name_parts[0], name_parts[1]) if len(name_parts) == 2 else (artifact_name, "1.0")
                full_name = f"{name}_v{version}"
                if full_name not in existing_names:
                    datasets.append({"name": name, "version": version, "path": art.get("url")})
        except Exception as exc:
            logger.error("Error querying datasets from DB: %s", exc)

    return {"status": "success", "datasets": datasets}


@router.post("/api/datasets/archive")
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

    if not local_source_existed and workspace_id:
        import uuid as _uuid
        from services.artifact_manager import ArtifactManager
        ws_uuid = _uuid.UUID(workspace_id)

        workspace_data_dir = config.project_root / "data" / "workspaces" / workspace_id / "data"
        workspace_data_dir.mkdir(parents=True, exist_ok=True)
        local_download_path = workspace_data_dir / source_path.name

        downloaded = await ArtifactManager.download_file_if_needed(
            workspace_id=ws_uuid, phase="generate", artifact_type="raw_dataset", local_file_path=local_download_path,
        )
        if not downloaded:
            downloaded = await ArtifactManager.download_file_if_needed(
                workspace_id=ws_uuid, phase="generate", artifact_type="dataset", local_file_path=local_download_path,
            )
        if downloaded:
            logger.info("Successfully pulled source dataset from IBM COS: %s", local_download_path)
            source_path = local_download_path
            local_source_existed = False

    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source dataset file not found locally or in IBM COS")

    target_name = f"{req.name}_v{req.version}.jsonl"
    target_path = datasets_dir / target_name

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if source_path.exists() and source_path.resolve() == target_path.resolve():
            if workspace_id:
                import uuid as _uuid
                from services.artifact_manager import ArtifactManager
                cos_artifact = await ArtifactManager.upload_and_register_file(
                    workspace_id=_uuid.UUID(workspace_id), phase="generate", artifact_type="dataset", local_file_path=target_path,
                )
                return {
                    "status": "success",
                    "message": f"Dataset already archived as {target_name} and synced to IBM COS",
                    "dataset_name": req.name,
                    "dataset_path": cos_artifact.url if cos_artifact else str(target_path),
                }
            return {"status": "success", "message": f"Dataset already archived as {target_name}", "dataset_name": req.name, "dataset_path": str(target_path)}

        shutil.copy2(source_path, target_path)

        cos_url = str(target_path)
        if workspace_id:
            import uuid as _uuid
            from services.artifact_manager import ArtifactManager
            cos_artifact = await ArtifactManager.upload_and_register_file(
                workspace_id=_uuid.UUID(workspace_id), phase="generate", artifact_type="dataset", local_file_path=target_path,
            )
            if cos_artifact:
                cos_url = cos_artifact.url

            if not local_source_existed and source_path.exists():
                os.remove(source_path)
                logger.info("Cleaned up temporary source copy at %s", source_path)

        return {
            "status": "success",
            "message": f"Dataset archived and uploaded to IBM COS as {target_name}",
            "dataset_name": req.name,
            "dataset_path": cos_url,
        }
    except Exception as exc:
        logger.error("Error archiving dataset: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/datasets/load")
async def load_dataset(req: LoadDatasetRequest):
    """Load a specific dataset file."""
    path_str = req.dataset_path

    if path_str.startswith("cos://"):
        from services.ibm_cos_service import cos_service
        try:
            url_no_scheme = path_str.replace("cos://", "")
            parts = url_no_scheme.split("/")
            bucket = parts[0]
            key = "/".join(parts[1:])
            filename = parts[-1]
            temp_dir = Path("data/temp_cache")
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_temp_path = temp_dir / filename
            cos_service.download_file(object_key=key, local_path=local_temp_path, bucket_name=bucket)
            path = local_temp_path
        except Exception as exc:
            logger.error("Failed to stream dataset from IBM COS: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to stream dataset from IBM COS: {exc}")
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

        if path_str.startswith("cos://") and path.exists():
            os.remove(path)

        return {"status": "success", "data": data}
    except Exception as exc:
        logger.error("Error loading dataset: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/api/datasets/{dataset_name}")
async def delete_dataset(dataset_name: str, workspace_id: Optional[str] = Query(None)):
    """Delete an archived dataset from local storage, IBM COS, and database."""
    from tool_router.config import config
    from services.ibm_cos_service import cos_service
    from db.engine import get_database, normalize_mongo_document

    datasets_dir = config.datasets_dir
    if workspace_id:
        datasets_dir = config.project_root / "data" / "workspaces" / workspace_id / "data" / "datasets"

    deleted = False
    deleted_files = []

    if datasets_dir.exists():
        for item in datasets_dir.iterdir():
            if item.is_file() and item.stem.startswith(dataset_name):
                try:
                    os.remove(item)
                    deleted = True
                    deleted_files.append(item.name)
                except Exception as exc:
                    logger.error("Error deleting local dataset %s: %s", item, exc)

    cos_deleted_count = 0
    if workspace_id:
        try:
            db = get_database()
            artifacts = await db.pipeline_artifacts.find(
                {"workspace_id": workspace_id, "artifact_type": "dataset"}
            ).to_list(length=None)

            for artifact_doc in artifacts:
                artifact = normalize_mongo_document(artifact_doc) or {}
                artifact_name = str(artifact.get("name", "")).replace(".jsonl", "")
                if artifact_name.split("_v")[0] == dataset_name:
                    try:
                        cos_service.delete_prefix(
                            key_prefix=str(artifact.get("cos_key", "")),
                            bucket_name=str(artifact.get("cos_bucket", "")),
                        )
                        await db.pipeline_artifacts.delete_one({"_id": artifact["id"]})
                        cos_deleted_count += 1
                        deleted = True
                    except Exception as cos_err:
                        logger.error("Error deleting dataset from COS: %s", cos_err)

        except Exception as exc:
            logger.error("Error deleting dataset from COS/DB: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to delete dataset from COS: {exc}")

    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return {
        "status": "success",
        "message": f"Dataset {dataset_name} deleted from local storage, IBM COS, and database",
        "deleted_files": deleted_files,
    }


# ===========================================================================
# MODELS  —  /api/models
# ===========================================================================

@router.get("/api/models")
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

    if workspace_id:
        from db.engine import get_database, normalize_mongo_document
        try:
            db = get_database()
            db_artifacts = await db.pipeline_artifacts.find(
                {
                    "workspace_id": workspace_id,
                    "artifact_type": {"$in": ["archived_model", "fine_tuned_model"]},
                    "name": {"$ne": "fine_tuned_tool_router"},
                }
            ).to_list(length=None)

            existing_names = {m["name"] for m in models}
            for artifact_doc in db_artifacts:
                art = normalize_mongo_document(artifact_doc) or {}
                artifact_name = art.get("name")
                if artifact_name and artifact_name not in existing_names:
                    models.append({"name": artifact_name, "path": art.get("url")})
        except Exception as exc:
            logger.error("Error querying models from DB: %s", exc)

    return {"status": "success", "models": models}


@router.post("/api/models/archive")
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

    if not local_source_existed and ws_id:
        import uuid as _uuid
        from services.artifact_manager import ArtifactManager
        ws_uuid = _uuid.UUID(ws_id)
        downloaded = await ArtifactManager.download_directory_if_needed(
            workspace_id=ws_uuid, phase="train", artifact_type="fine_tuned_model",
            local_dir_path=source_path, dir_name=source_path.name,
        )
        if downloaded:
            logger.info("Successfully pulled source model from IBM COS: %s", source_path)

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

        cos_url = str(target_path)
        if ws_id:
            import uuid as _uuid
            from services.artifact_manager import ArtifactManager
            cos_artifact = await ArtifactManager.upload_and_register_directory(
                workspace_id=_uuid.UUID(ws_id), phase="train", artifact_type="archived_model",
                local_dir_path=target_path, dir_name=target_name,
            )
            if cos_artifact:
                cos_url = cos_artifact.url
            if not local_source_existed and source_path.exists():
                shutil.rmtree(source_path)
                logger.info("Cleaned up temporary source copy at %s", source_path)

        return {
            "status": "success",
            "message": f"Model archived and uploaded to IBM COS as {target_name}",
            "model_name": target_name,
            "model_path": cos_url,
        }
    except Exception as exc:
        logger.error("Error archiving model: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/api/models/{model_name}")
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
        from db.engine import get_database, normalize_mongo_document
        from services.ibm_cos_service import cos_service

        try:
            db = get_database()
            artifact_doc = await db.pipeline_artifacts.find_one(
                {
                    "workspace_id": workspace_id,
                    "name": model_name,
                    "artifact_type": {"$in": ["archived_model", "fine_tuned_model"]},
                }
            )
            artifact = normalize_mongo_document(artifact_doc)
            if artifact:
                cos_service.delete_prefix(
                    str(artifact.get("cos_key", "")),
                    bucket_name=str(artifact.get("cos_bucket", "")),
                )
                await db.pipeline_artifacts.delete_one({"_id": artifact["id"]})
                cos_deleted = True
                logger.info(
                    "Deleted model %s (type: %s) from IBM COS and database.",
                    model_name, artifact.get("artifact_type"),
                )
        except Exception as exc:
            logger.error("Error deleting model from IBM COS: %s", exc)

    if not local_existed and not cos_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found locally or in IBM COS"
        )

    try:
        if local_existed:
            shutil.rmtree(target_path)
        return {"status": "success", "message": f"Model {model_name} deleted successfully"}
    except Exception as exc:
        logger.error("Error deleting local model: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ===========================================================================
# SCENARIOS  —  /api/agents
# ===========================================================================

@router.get("/api/agents/scenarios")
async def list_agent_scenarios():
    """Get list of available agent scenarios."""
    try:
        from tool_router.agent_service import agent_orchestrator
        scenarios = agent_orchestrator.list_scenarios()
        return {"status": "success", "scenarios": scenarios}
    except Exception as exc:
        logger.error("Error listing agent scenarios: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/agents/scenarios/{scenario_id}")
async def get_agent_scenario(scenario_id: str):
    """Get detailed information about a specific agent scenario."""
    try:
        from tool_router.agent_service import agent_orchestrator
        scenario = agent_orchestrator.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
        return {"status": "success", "scenario": scenario}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting agent scenario: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/agents/execute")
async def execute_agent_scenario(request: AgentExecuteRequest):
    """Execute an agent scenario and stream events (SSE)."""

    async def event_generator():
        try:
            from tool_router.agent_service import agent_orchestrator
            if request.user_prompt:
                yield f"data: {json.dumps({'type': 'thought', 'label': 'User Prompt Received', 'detail': request.user_prompt, 'timestamp': time.time(), 'status': 'success'})}\n\n"
                yield f"data: {json.dumps({'type': 'reasoning', 'label': 'Preparing Agent Execution', 'detail': f'Executing selected agent {request.scenario_id}', 'timestamp': time.time(), 'status': 'running'})}\n\n"

            async for event in agent_orchestrator.execute_scenario(
                scenario_id=request.scenario_id,
                workspace_id=request.workspace_id,
                llm_config=request.llm_config,
                runtime_config=request.runtime_config,
            ):
                event_dict = event.to_dict()
                event_type = event_dict.get("type")

                if event_type == "assistant_response":
                    event_dict["type"] = "assistant"
                    event_dict.setdefault("label", "Agent Response")
                    event_dict["detail"] = event_dict.get("detail") or event_dict.get("message") or ""
                elif event_type == "thinking":
                    event_dict["type"] = "thought"
                    event_dict.setdefault("label", "LLM Thought")
                elif event_type == "tool_start":
                    event_dict["type"] = "tool_call"
                    event_dict.setdefault("label", "Tool Call")
                elif event_type == "tool_end":
                    event_dict["type"] = "tool_result"
                    event_dict.setdefault("label", "Tool Result")

                yield f"data: {json.dumps(event_dict)}\n\n"

            yield f"data: {json.dumps({'type': 'complete', 'label': 'Agent Execution Complete', 'detail': 'Streaming finished', 'timestamp': time.time(), 'status': 'success'})}\n\n"

        except Exception as exc:
            logger.error("Error in agent execution stream: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'timestamp': time.time(), 'data': {'error': str(exc), 'error_type': type(exc).__name__}})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
