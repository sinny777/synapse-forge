"""
api.neural_router_pipeline.schemas
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pydantic request models for the NTR pipeline, data, datasets, models, and scenarios.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


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


class ArchiveModelRequest(BaseModel):
    name: str
    version: str
    source_dir: str
    workspace_id: Optional[str] = None


class ArchiveDatasetRequest(BaseModel):
    name: str
    version: str
    source_file: str


class LoadDatasetRequest(BaseModel):
    dataset_path: str


class SyntheticDataUpdate(BaseModel):
    data: list


class AgentExecuteRequest(BaseModel):
    """Standalone scenario execution request (not the workspace agent execute)."""
    scenario_id: str
    workspace_id: Optional[str] = None
    user_prompt: Optional[str] = None
    llm_config: Optional[Dict[str, Any]] = None
    runtime_config: Optional[Dict[str, Any]] = None
