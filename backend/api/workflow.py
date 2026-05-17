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
        if config_data.queries_per_tool:
            config.data_generation.queries_per_tool = config_data.queries_per_tool
        if config_data.teacher_model:
            config.llm.teacher_model = config_data.teacher_model

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
        _update_global_config(config_data, "generate")
        from tool_router.generator import main as phase1_main
        await phase1_main()
        update_status(
            status="completed", progress=1.0,
            message="Generation phase completed successfully.",
        )
        return {"status": "success", "message": "Generation phase completed."}
    except Exception as e:
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
def train_phase(config_data: TrainConfig):
    """Start the embedding model training phase (runs in background thread)."""
    from tool_router.status_tracker import update_status, reset_status
    from tool_router.config import config
    import shutil

    reset_status()
    update_status(
        phase="train", status="running", progress=0.0,
        message="Initializing training phase...",
    )

    def run_training():
        try:
            _update_global_config(config_data, "train")
            from tool_router.trainer import main as phase2_main
            phase2_main()

            # Auto-archive the trained model
            source_path = config.embedding.fine_tuned_model_dir
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

                    action = "updated" if model_existed else "archived"
                    logger.info(f"Model {action} as {target_name}")
                    update_status(
                        status="completed", progress=1.0,
                        message=f"Training completed. Model {action} as {target_name}",
                    )
                except Exception as archive_error:
                    logger.warning(f"Training completed but archiving failed: {archive_error}")
                    update_status(
                        status="completed", progress=1.0,
                        message="Training completed but auto-archiving failed.",
                    )
            else:
                update_status(
                    status="completed", progress=1.0,
                    message="Training phase completed successfully.",
                )
        except Exception as e:
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

@router.post("/run")
async def run_phase(config_data: RunConfig):
    """Run the agentic tool-routing loop (streaming NDJSON)."""
    try:
        _update_global_config(config_data, "run")
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
        t0 = time.time()

        model_dir = (
            config_data.model_path
            if config_data.model_path
            else str(config.embedding.fine_tuned_model_dir)
        )
        model = SentenceTransformer(model_dir, device=config.embedding.device)

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
