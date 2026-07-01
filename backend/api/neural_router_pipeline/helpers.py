"""
api.neural_router_pipeline.helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Utility functions shared across the NTR pipeline route handlers.
"""

from __future__ import annotations

from pathlib import Path


def apply_dict_to_obj(config_dict: dict | None, obj) -> None:
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
                    setattr(obj, k, int(v) if isinstance(orig_val, int) else float(v))
                except (ValueError, TypeError):
                    setattr(obj, k, v)
            else:
                setattr(obj, k, v)


def update_global_config(config_data, phase: str) -> None:
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

        config.embedding.fine_tuned_model_dir = config.models_dir / "fine_tuned_tool_router"
        config.training.training_data_path = config.data_dir / "synthetic_queries.jsonl"
        config.training.logging_dir = config.logs_dir / "training"
        config.vector_store.faiss_index_path = config.data_dir / "faiss_index.bin"
        config.vector_store.chromadb_path = config.data_dir / "chromadb"
        config.mcp.tool_cache_path = config.data_dir / "tool_cache.json"
        config.data_generation.output_path = config.data_dir / "synthetic_queries.jsonl"
        config.runtime.log_file = config.logs_dir / "runtime.log"

    if phase == "generate":
        apply_dict_to_obj(config_data.llm, config.llm)
        apply_dict_to_obj(config_data.embedding, config.embedding)
        apply_dict_to_obj(config_data.vector_store, config.vector_store)
        apply_dict_to_obj(config_data.data_generation, config.data_generation)

        if config_data.mcp:
            apply_dict_to_obj(
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
        apply_dict_to_obj(config_data.training, config.training)
        apply_dict_to_obj(config_data.embedding, config.embedding)
        apply_dict_to_obj(config_data.vectorStore, config.vector_store)

    elif phase in ("run", "evaluate"):
        if hasattr(config_data, "enable_query_expansion"):
            config.runtime.enable_query_expansion = config_data.enable_query_expansion
        if hasattr(config_data, "max_tool_calls"):
            config.runtime.max_tool_calls = config_data.max_tool_calls
        if hasattr(config_data, "top_k"):
            config.vector_store.top_k = config_data.top_k

    # Re-enforce workspace isolation after overrides
    if ws_id and ws_root:
        config.mcp.tool_cache_path = config.data_dir / "tool_cache.json"
        config.embedding.fine_tuned_model_dir = config.models_dir / "fine_tuned_tool_router"
        config.vector_store.faiss_index_path = config.data_dir / "faiss_index.bin"
        config.vector_store.chromadb_path = config.data_dir / "chromadb"
        config.training.logging_dir = config.logs_dir / "training"
        config.runtime.log_file = config.logs_dir / "runtime.log"

        if isinstance(config.data_generation.output_path, (str, Path)):
            fname = Path(config.data_generation.output_path).name
            config.data_generation.output_path = config.datasets_dir / fname

        if isinstance(config.training.training_data_path, (str, Path)):
            fname = Path(config.training.training_data_path).name
            config.training.training_data_path = config.datasets_dir / fname


async def ensure_run_artifacts_downloaded(
    workspace_id: str | None,
    model_name: str | None = None,
):
    """Download tool cache, fine-tuned model, and search indexes from IBM COS as needed."""
    import uuid
    from services.artifact_manager import ArtifactManager
    from tool_router.config import config

    if not workspace_id:
        return config.embedding.fine_tuned_model_dir

    ws_uuid = uuid.UUID(str(workspace_id))

    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid,
        phase="generate",
        artifact_type="tool_cache",
        local_file_path=config.mcp.tool_cache_path,
    )

    if model_name:
        local_model_dir = config.models_dir / model_name
        dir_name = model_name
    else:
        local_model_dir = config.embedding.fine_tuned_model_dir
        dir_name = config.embedding.fine_tuned_model_dir.name

    downloaded = await ArtifactManager.download_directory_if_needed(
        workspace_id=ws_uuid,
        phase="train",
        artifact_type="archived_model",
        local_dir_path=local_model_dir,
        dir_name=dir_name,
    )
    if not downloaded:
        await ArtifactManager.download_directory_if_needed(
            workspace_id=ws_uuid,
            phase="train",
            artifact_type="fine_tuned_model",
            local_dir_path=local_model_dir,
            dir_name=dir_name,
        )

    faiss_path = Path(config.vector_store.faiss_index_path)
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid, phase="train", artifact_type="faiss_index", local_file_path=faiss_path,
    )
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid, phase="train", artifact_type="faiss_index_mapping",
        local_file_path=faiss_path.with_suffix(".json"),
    )

    bm25_path = faiss_path.parent / "bm25_index.pkl"
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid, phase="train", artifact_type="bm25_index", local_file_path=bm25_path,
    )
    await ArtifactManager.download_file_if_needed(
        workspace_id=ws_uuid, phase="train", artifact_type="bm25_index_mapping",
        local_file_path=bm25_path.with_suffix(".json"),
    )

    return local_model_dir
