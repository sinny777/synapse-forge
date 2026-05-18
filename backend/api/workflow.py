"""
SynapseForge — Workflow API Routes

Endpoints for the standalone SynapseForge pipeline:
  • Generate  — synthetic data generation (Phase 1)
  • Train     — embedding model fine-tuning (Phase 2)
  • Run       — agentic runtime loop (Phase 3)
  • Evaluate  — model evaluation
  • Status    — real-time pipeline status
"""

import asyncio
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("ntr.api.workflow")

router = APIRouter(prefix="/api", tags=["SynapseForge_Workflow"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class GenerateConfig(BaseModel):
    workspace_id: Optional[str] = None
    queries_per_tool: Optional[int] = 10
    teacher_model: Optional[str] = "ollama/granite4.1:8b"
    llm: Optional[dict] = None
    embedding: Optional[dict] = None
    vector_store: Optional[dict] = None
    mcp: Optional[dict] = None
    data_generation: Optional[dict] = None


class TrainConfig(BaseModel):
    workspace_id: Optional[str] = None
    training: Optional[dict] = None
    embedding: Optional[dict] = None
    vectorStore: Optional[dict] = None
    archive_name: Optional[str] = None
    archive_version: Optional[str] = None


class RunConfig(BaseModel):
    workspace_id: Optional[str] = None
    query: str
    enable_query_expansion: bool = True
    max_tool_calls: int = 10
    model_path: Optional[str] = None


class EvaluateConfig(BaseModel):
    workspace_id: Optional[str] = None
    query: str
    top_k: int = 5
    model_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Config helpers (shared across workflow endpoints)
# ---------------------------------------------------------------------------

def _apply_dict_to_obj(config_dict, obj):
    """Apply a flat dict of overrides onto a dataclass/object."""
    if not config_dict:
        return
    for k, v in config_dict.items():
        if hasattr(obj, k):
            orig_val = getattr(obj, k)
            if isinstance(orig_val, Path) and isinstance(v, str):
                setattr(obj, k, Path(v))
            elif isinstance(orig_val, (int, float)) and isinstance(v, str):
                try:
                    if isinstance(orig_val, int):
                        setattr(obj, k, int(v))
                    else:
                        setattr(obj, k, float(v))
                except (ValueError, TypeError):
                    setattr(obj, k, v)
            else:
                setattr(obj, k, v)


def _update_global_config(config_data, phase: str):
    """Update the global ToolRouter config for a given pipeline phase."""
    from tool_router.config import config

    ws_id = getattr(config_data, "workspace_id", None)
    ws_root = None
    if ws_id:
        ws_root = config.project_root / "data" / "workspaces" / str(ws_id)
        config.data_dir = ws_root / "data"
        config.datasets_dir = ws_root / "data" / "datasets"
        config.models_dir = ws_root / "models"
        config.logs_dir = ws_root / "logs"

        config.data_dir.mkdir(parents=True, exist_ok=True)
        config.datasets_dir.mkdir(parents=True, exist_ok=True)
        config.models_dir.mkdir(parents=True, exist_ok=True)
        config.logs_dir.mkdir(parents=True, exist_ok=True)

        # Set default isolated paths
        config.embedding.fine_tuned_model_dir = config.models_dir / "fine_tuned_tool_router"
        config.training.training_data_path = config.data_dir / "synthetic_queries.jsonl"
        config.training.logging_dir = config.logs_dir / "training"
        config.vector_store.faiss_index_path = config.data_dir / "faiss_index.bin"
        config.vector_store.chromadb_path = config.data_dir / "chromadb"
        config.mcp.tool_cache_path = config.data_dir / "tool_cache.json"
        config.data_generation.output_path = config.data_dir / "synthetic_queries.jsonl"
        config.runtime.log_file = config.logs_dir / "runtime.log"

    # Apply overrides from request
    if phase == "generate":
        _apply_dict_to_obj(config_data.llm, config.llm)
        _apply_dict_to_obj(config_data.embedding, config.embedding)
        _apply_dict_to_obj(config_data.vector_store, config.vector_store)
        _apply_dict_to_obj(config_data.data_generation, config.data_generation)

        if config_data.mcp:
            _apply_dict_to_obj(
                {k: v for k, v in config_data.mcp.items() if k != "servers"},
                config.mcp,
            )
            if "servers" in config_data.mcp:
                config.mcp.servers = config_data.mcp["servers"]

        if config_data.queries_per_tool:
            config.data_generation.queries_per_tool = config_data.queries_per_tool
        if config_data.teacher_model:
            config.llm.teacher_model = config_data.teacher_model

    elif phase == "train":
        _apply_dict_to_obj(config_data.training, config.training)
        _apply_dict_to_obj(config_data.embedding, config.embedding)
        _apply_dict_to_obj(config_data.vectorStore, config.vector_store)

    elif phase in ("run", "evaluate"):
        if hasattr(config_data, "enable_query_expansion"):
            config.runtime.enable_query_expansion = config_data.enable_query_expansion
        if hasattr(config_data, "max_tool_calls"):
            config.runtime.max_tool_calls = config_data.max_tool_calls
        if hasattr(config_data, "top_k"):
            config.vector_store.top_k = config_data.top_k

    # RE-ENFORCE workspace isolation after overrides
    if ws_id and ws_root:
        # Always force these into workspace, even if frontend sent relative paths
        config.mcp.tool_cache_path = config.data_dir / "tool_cache.json"
        config.embedding.fine_tuned_model_dir = config.models_dir / "fine_tuned_tool_router"
        config.vector_store.faiss_index_path = config.data_dir / "faiss_index.bin"
        config.vector_store.chromadb_path = config.data_dir / "chromadb"
        config.training.logging_dir = config.logs_dir / "training"
        config.runtime.log_file = config.logs_dir / "runtime.log"

        # Special handling for user-provided dataset filenames
        # If they are strings, we extract the filename and put it in the workspace datasets dir
        if isinstance(config.data_generation.output_path, (str, Path)):
            fname = Path(config.data_generation.output_path).name
            config.data_generation.output_path = config.datasets_dir / fname
        
        if isinstance(config.training.training_data_path, (str, Path)):
            fname = Path(config.training.training_data_path).name
            # If training data path is just the filename or in data/datasets, move to workspace datasets dir
            config.training.training_data_path = config.datasets_dir / fname


# ---------------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_status():
    """Return current pipeline status."""
    from tool_router.status_tracker import get_status
    return get_status()


# ---------------------------------------------------------------------------
# GENERATE
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_phase(config_data: GenerateConfig):
    """Run the synthetic data generation phase."""
    from tool_router.status_tracker import update_status, reset_status

    reset_status()
    update_status(
        phase="generate", status="running", progress=0.0,
        message="Initializing generation phase...",
    )
    try:
        # Resolve user-selected LLM Config from database if teacher_model is a UUID
        teacher_model_str = config_data.teacher_model
        if teacher_model_str:
            import uuid
            is_uuid = False
            try:
                uuid.UUID(str(teacher_model_str))
                is_uuid = True
            except ValueError:
                pass

            if is_uuid:
                from db.engine import _session_factory
                from db.models import LLMConfig
                import os

                async with _session_factory() as session:
                    config_row = await session.get(LLMConfig, uuid.UUID(str(teacher_model_str)))
                    if config_row:
                        provider = config_row.provider.value
                        model_name = config_row.model_name
                        credentials = config_row.credentials or {}
                        
                        logger.info(f"Using selected LLM Config '{config_row.name}' (provider: {provider}, model: {model_name}) for Phase 1 generation.")

                        # Inject credentials into env vars
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
                                if region.startswith("http"):
                                    os.environ["WATSONX_URL"] = region
                                else:
                                    os.environ["WATSONX_URL"] = f"https://{region}.ml.cloud.ibm.com"
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
                        logger.warning(f"Selected LLM Config with ID {teacher_model_str} not found in database. Using default/fallback model.")

        _update_global_config(config_data, "generate")
        from tool_router.generator import main as phase1_main
        await phase1_main()

        # Upload and register generated artifacts to IBM COS and clean up local copy
        ws_id = getattr(config_data, "workspace_id", None)
        if ws_id:
            import uuid
            from services.artifact_manager import ArtifactManager
            from tool_router.config import config as tr_config

            ws_uuid = uuid.UUID(str(ws_id))
            update_status(
                status="running", progress=0.96,
                message="Uploading artifacts to IBM Cloud Object Storage...",
            )

            # Upload synthetic queries JSONL (as raw_dataset, not dataset)
            # This prevents it from appearing in the archived datasets list
            # Users must explicitly archive it to make it available for training
            output_path = Path(tr_config.data_generation.output_path)
            await ArtifactManager.upload_and_register_file(
                workspace_id=ws_uuid,
                phase="generate",
                artifact_type="raw_dataset",  # Changed from "dataset" to "raw_dataset"
                local_file_path=output_path
            )

            # Upload tool cache JSON
            tool_cache_path = Path(tr_config.mcp.tool_cache_path)
            await ArtifactManager.upload_and_register_file(
                workspace_id=ws_uuid,
                phase="generate",
                artifact_type="tool_cache",
                local_file_path=tool_cache_path
            )

            # Clean up all empty temporary directories in the workspace
            try:
                ArtifactManager.cleanup_empty_workspace_directories(ws_uuid)
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up empty workspace directories: {cleanup_err}")

        update_status(
            status="completed", progress=1.0,
            message="Generation phase completed successfully. Artifacts uploaded to IBM COS.",
        )
        return {"status": "success", "message": "Generation phase completed."}
    except Exception as e:
        ws_id = getattr(config_data, "workspace_id", None)
        if ws_id:
            try:
                import uuid
                from services.artifact_manager import ArtifactManager
                ArtifactManager.cleanup_empty_workspace_directories(uuid.UUID(str(ws_id)))
            except:
                pass
        update_status(status="error", message=f"Generation failed: {str(e)}")
        logger.error(f"Generate phase failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# TRAIN  (POST + SSE stream)
# ---------------------------------------------------------------------------

@router.get("/train/stream")
async def train_stream():
    """Server-Sent Events endpoint for real-time training progress."""
    from tool_router.status_tracker import add_listener, remove_listener, get_status

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        def status_callback(status_data):
            try:
                asyncio.create_task(queue.put(status_data))
            except Exception:
                pass

        add_listener(status_callback)
        try:
            initial_status = get_status().model_dump()
            yield f"data: {json.dumps(initial_status)}\n\n"

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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/train")
async def train_phase(config_data: TrainConfig):
    """Start the embedding model training phase (runs in background thread)."""
    from tool_router.status_tracker import update_status, reset_status
    from tool_router.config import config
    import shutil

    reset_status()
    update_status(
        phase="train", status="running", progress=0.0,
        message="Initializing training phase...",
    )
    
    # Pre-download files from COS in the main async context BEFORE starting the background thread
    workspace_id = getattr(config_data, "workspace_id", None)
    if workspace_id:
        import uuid
        from services.artifact_manager import ArtifactManager
        
        # Temporarily update config to get correct paths
        _update_global_config(config_data, "train")
        
        ws_uuid = uuid.UUID(str(workspace_id))
        
        update_status(
            status="running", progress=0.05,
            message="Downloading training data and tool cache from IBM COS...",
        )
        
        # Download files in the main async context
        await ArtifactManager.download_file_if_needed(
            workspace_id=ws_uuid,
            phase="generate",
            artifact_type="tool_cache",
            local_file_path=config.mcp.tool_cache_path
        )
        # Try raw_dataset first (newly generated), then dataset (archived)
        downloaded = await ArtifactManager.download_file_if_needed(
            workspace_id=ws_uuid,
            phase="generate",
            artifact_type="raw_dataset",
            local_file_path=config.training.training_data_path
        )
        if not downloaded:
            # Fallback to archived dataset
            await ArtifactManager.download_file_if_needed(
                workspace_id=ws_uuid,
                phase="generate",
                artifact_type="dataset",
                local_file_path=config.training.training_data_path
            )

    def run_training():
        try:
            # Config already updated above, just proceed with training

            from tool_router.trainer import main as phase2_main
            phase2_main()

            # Auto-archive the trained model
            source_path = config.embedding.fine_tuned_model_dir
            target_path = None
            target_name = None
            model_existed = False

            if source_path.exists():
                if config_data.archive_name and config_data.archive_version:
                    model_name = config_data.archive_name
                    version = config_data.archive_version
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    model_name = f"tool_router_{timestamp}"
                    version = "1.0"

                target_name = f"{model_name}_v{version}"
                target_path = config.models_dir / target_name

                try:
                    model_existed = target_path.exists()
                    if model_existed:
                        shutil.rmtree(target_path)
                    shutil.copytree(source_path, target_path)
                    
                    # Delete the source fine_tuned_tool_router directory after successful copy
                    # to avoid duplicate model entries
                    if source_path.exists() and source_path != target_path:
                        shutil.rmtree(source_path)
                        logger.info(f"Cleaned up temporary training directory: {source_path}")

                    action = "updated" if model_existed else "archived"
                    logger.info(f"Model {action} as {target_name}")
                except Exception as archive_error:
                    logger.warning(f"Training completed but archiving failed: {archive_error}")
                    target_path = None

            # 2. Post-training: upload all Phase 2 artifacts to IBM COS and clean up local copies
            if workspace_id:
                import uuid
                from services.artifact_manager import ArtifactManager
                ws_uuid = uuid.UUID(str(workspace_id))
                
                update_status(
                    status="running", progress=0.95,
                    message="Uploading model and retrieval indexes to IBM COS...",
                )
                
                def upload_training_files_sync():
                    """Synchronous wrapper for COS uploads using the sync upload methods"""
                    # Upload FAISS index files
                    faiss_path = Path(config.vector_store.faiss_index_path)
                    if faiss_path.exists():
                        ArtifactManager.upload_and_register_file_sync(
                            workspace_id=ws_uuid,
                            phase="train",
                            artifact_type="faiss_index",
                            local_file_path=faiss_path
                        )
                        faiss_json = faiss_path.with_suffix('.json')
                        if faiss_json.exists():
                            ArtifactManager.upload_and_register_file_sync(
                                workspace_id=ws_uuid,
                                phase="train",
                                artifact_type="faiss_index_mapping",
                                local_file_path=faiss_json
                            )
                            
                    # Upload BM25 index files
                    bm25_path = faiss_path.parent / "bm25_index.pkl"
                    if bm25_path.exists():
                        ArtifactManager.upload_and_register_file_sync(
                            workspace_id=ws_uuid,
                            phase="train",
                            artifact_type="bm25_index",
                            local_file_path=bm25_path
                        )
                        bm25_json = bm25_path.with_suffix('.json')
                        if bm25_json.exists():
                            ArtifactManager.upload_and_register_file_sync(
                                workspace_id=ws_uuid,
                                phase="train",
                                artifact_type="bm25_index_mapping",
                                local_file_path=bm25_json
                            )
                            
                    # Only upload the archived model directory (user-named), not the fine_tuned_tool_router
                    if target_path and target_path.exists():
                        ArtifactManager.upload_and_register_directory_sync(
                            workspace_id=ws_uuid,
                            phase="train",
                            artifact_type="archived_model",
                            local_dir_path=target_path,
                            dir_name=target_name
                        )
                
                # Call synchronous upload function
                try:
                    upload_training_files_sync()
                except Exception as upload_err:
                    logger.error(f"Failed to upload training artifacts: {upload_err}")
                    raise

                # Clean up downloaded input files used for training
                try:
                    for p in [config.mcp.tool_cache_path, config.training.training_data_path]:
                        file_path = Path(p)
                        if file_path.exists():
                            file_path.unlink()
                            logger.info(f"✓ Cleaned up local training input file: {file_path}")
                except Exception as cleanup_input_err:
                    logger.warning(f"Failed to delete training input files: {cleanup_input_err}")

                # Clean up all empty temporary directories in the workspace
                try:
                    ArtifactManager.cleanup_empty_workspace_directories(ws_uuid)
                except Exception as cleanup_err:
                    logger.warning(f"Failed to clean up empty workspace directories after training: {cleanup_err}")

            # Update final status
            if target_name:
                action = "updated" if model_existed else "archived"
                msg = f"Training completed. Model {action} as {target_name} and uploaded to IBM COS."
            else:
                msg = "Training phase completed successfully. Artifacts uploaded to IBM COS."
                
            update_status(status="completed", progress=1.0, message=msg)
        except Exception as e:
            ws_id = getattr(config_data, "workspace_id", None)
            if ws_id:
                try:
                    import uuid
                    from services.artifact_manager import ArtifactManager
                    ArtifactManager.cleanup_empty_workspace_directories(uuid.UUID(str(ws_id)))
                except:
                    pass
            update_status(status="error", message=f"Training failed: {str(e)}")
            logger.error(f"Train phase failed: {e}")

    training_thread = threading.Thread(target=run_training, daemon=True)
    training_thread.start()

    return {
        "status": "success",
        "message": "Training started. Use /api/train/stream for real-time updates.",
    }


# ---------------------------------------------------------------------------
# RUN
# ---------------------------------------------------------------------------

async def _ensure_run_artifacts_downloaded(workspace_id: str, model_name: str = None):
    """Ensures tool cache, fine-tuned model, and search indexes are cached locally from COS.
    
    Returns:
        Path: The local directory path where the model was downloaded
    """
    import uuid
    from services.artifact_manager import ArtifactManager
    from tool_router.config import config
    
    if not workspace_id:
        return config.embedding.fine_tuned_model_dir
    
    ws_uuid = uuid.UUID(str(workspace_id))
    
    # Download tool cache JSON
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid,
        phase="generate",
        artifact_type="tool_cache",
        local_file_path=config.mcp.tool_cache_path
    )
    
    # Download fine-tuned model directory
    # If a specific model name is provided, download to models_dir/model_name
    # Otherwise, use the default fine_tuned_model_dir
    if model_name:
        local_model_dir = config.models_dir / model_name
        dir_name = model_name
    else:
        local_model_dir = config.embedding.fine_tuned_model_dir
        dir_name = config.embedding.fine_tuned_model_dir.name
    
    # Try archived_model first (new format), then fall back to fine_tuned_model (old format)
    downloaded = await ArtifactManager.download_directory_if_needed(
        workspace_id=ws_uuid,
        phase="train",
        artifact_type="archived_model",
        local_dir_path=local_model_dir,
        dir_name=dir_name
    )
    if not downloaded:
        # Fall back to old artifact type for backward compatibility
        await ArtifactManager.download_directory_if_needed(
            workspace_id=ws_uuid,
            phase="train",
            artifact_type="fine_tuned_model",
            local_dir_path=local_model_dir,
            dir_name=dir_name
        )
    
    # Download FAISS index files
    faiss_path = Path(config.vector_store.faiss_index_path)
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid,
        phase="train",
        artifact_type="faiss_index",
        local_file_path=faiss_path
    )
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid,
        phase="train",
        artifact_type="faiss_index_mapping",
        local_file_path=faiss_path.with_suffix('.json')
    )
    
    # Download BM25 index files
    bm25_path = faiss_path.parent / "bm25_index.pkl"
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid,
        phase="train",
        artifact_type="bm25_index",
        local_file_path=bm25_path
    )
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid,
        phase="train",
        artifact_type="bm25_index_mapping",
        local_file_path=bm25_path.with_suffix('.json')
    )
    
    return local_model_dir


@router.post("/run")
async def run_phase(config_data: RunConfig):
    """Run the agentic tool-routing loop (streaming NDJSON)."""
    try:
        _update_global_config(config_data, "run")
        if config_data.workspace_id:
            # Extract model name from model_path if provided
            model_name = None
            if config_data.model_path:
                model_name = Path(config_data.model_path).name
            await _ensure_run_artifacts_downloaded(config_data.workspace_id, model_name)
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
            except Exception as e:
                logger.error(f"Error in stream: {e}")
                yield json.dumps({"event": "error", "data": {"message": str(e)}}) + "\n"
            finally:
                await router_instance.close()

        return StreamingResponse(event_generator(), media_type="application/x-ndjson")
    except Exception as e:
        logger.error(f"Run phase failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# EVALUATE
# ---------------------------------------------------------------------------

@router.post("/evaluate")
async def evaluate_phase(config_data: EvaluateConfig):
    """Evaluate the trained model against a query."""
    from tool_router.runtime import SemanticRouter
    from tool_router.config import config
    from tool_router.mcp_client import MCPClient
    from sentence_transformers import SentenceTransformer

    try:
        _update_global_config(config_data, "evaluate")
        
        # Extract model name from model_path if provided (COS URL)
        model_name = None
        if config_data.model_path:
            # Extract model name from COS URL (e.g., "multi-router-model_v1.0" from the path)
            model_name = Path(config_data.model_path).name
        
        # Download artifacts and get the local model directory path
        model_dir = await _ensure_run_artifacts_downloaded(config_data.workspace_id, model_name)
        
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
            config_data.query,
            top_k=config_data.top_k,
            use_hybrid=False,
            apply_threshold=False,
        )

        mcp_client = MCPClient(config.mcp)
        mcp_client.load_tool_cache(config.mcp.tool_cache_path)

        enriched_tools = []
        for tid, score in retrieved_tools:
            tool_schema = mcp_client.tools.get(tid)
            if tool_schema:
                enriched_tools.append({
                    "id": tid,
                    "score": score,
                    "name": tool_schema.name,
                    "description": tool_schema.description,
                    "server_name": tool_schema.server_name,
                    "parameters": tool_schema.parameters,
                    "input_schema": tool_schema.raw_schema.get("inputSchema", {}),
                    "output_format": tool_schema.raw_schema.get("outputFormat", "Tool execution result"),
                })
            else:
                enriched_tools.append({
                    "id": tid,
                    "score": score,
                    "name": tid.split(".")[-1] if "." in tid else tid,
                    "description": "Tool metadata not available",
                    "server_name": "unknown",
                    "parameters": {},
                    "input_schema": {},
                    "output_format": "Tool execution result",
                })

        total_time = time.time() - t0

        return {
            "status": "success",
            "message": "Evaluation completed.",
            "data": {
                "query": config_data.query,
                "retrieved_tools": enriched_tools,
                "time_taken": total_time,
            },
        }
    except Exception as e:
        logger.error(f"Evaluate phase failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
