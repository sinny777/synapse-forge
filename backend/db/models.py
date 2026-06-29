"""
SynapseForge — MongoDB Domain Models

Defines the core document models used by the platform while preserving the
existing UUID-based API contract. These models replace the previous
SQLAlchemy/PostgreSQL ORM layer for Phase 1 of the MongoDB migration.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class MongoDocument(BaseModel):
    """Base document model with UUID string IDs and audit metadata."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    created_by: str | None = None
    updated_by: str | None = None

    def touch(self, updated_by: str | None = None) -> None:
        """Update modification metadata."""
        self.updated_at = utcnow()
        if updated_by is not None:
            self.updated_by = updated_by


class ToolType(str, enum.Enum):
    """Transport type used to connect to the tool."""

    REST = "REST"
    MCP_SERVER = "MCP_SERVER"
    MCP_TOOL = "MCP_TOOL"


class MCPTransportType(str, enum.Enum):
    """MCP server transport protocol."""

    STDIO = "stdio"
    SSE = "sse"


class MCPServerStatus(str, enum.Enum):
    """MCP server connection status."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class OrchestrationFramework(str, enum.Enum):
    """Supported orchestration frameworks."""

    LANGGRAPH = "LANGGRAPH"
    CREWAI = "CREWAI"
    AUTOGEN = "AUTOGEN"


class ArchitectureType(str, enum.Enum):
    """Supported multi-agent architecture patterns."""

    REACT = "REACT"
    SUPERVISOR = "SUPERVISOR"
    PLANNER = "PLANNER"


class WorkspaceStatus(str, enum.Enum):
    """Tracks the container / environment lifecycle of a workspace."""

    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"


class LLMProviderEnum(str, enum.Enum):
    """Supported LLM provider types."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    IBM_WATSONX = "ibm_watsonx"
    GROQ = "groq"
    AZURE = "azure"
    COHERE = "cohere"
    BEDROCK = "bedrock"
    VERTEX_AI = "vertex_ai"


class Workspace(MongoDocument):
    """Multi-tenant workspace root document."""

    name: str
    description: str | None = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    is_default: bool = False
    status: WorkspaceStatus = WorkspaceStatus.STOPPED
    shared_with: list[str] | None = None


class Tool(MongoDocument):
    """Unified tool registry document."""

    workspace_id: str
    name: str
    description: str | None = None
    type: ToolType = ToolType.REST
    is_enabled: bool = True
    connection_config: dict[str, Any] | None = None
    schema_def: dict[str, Any] | None = None
    transport: MCPTransportType | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, Any] | None = None
    url: str | None = None
    status: MCPServerStatus = MCPServerStatus.ACTIVE
    last_error: str | None = None
    parent_id: str | None = None
    embedding: list[float] | None = None
    # Classification
    category: str | None = None
    sub_category: str | None = None
    tags: list[str] | None = None


class Agent(MongoDocument):
    """LLM agent definition document."""

    workspace_id: str
    name: str
    description: str | None = None
    system_prompt: str | None = None
    llm_config_id: str | None = None
    use_neural_router: bool = False
    router_model_id: str | None = None
    router_top_k: int | None = None
    memory_type: str | None = None
    memory_window: int | None = None
    max_iterations: int | None = None
    timeout_seconds: int | None = None
    attached_tool_ids: list[str] | None = None
    collaborator_agent_ids: list[str] | None = None
    # Classification
    category: str | None = None
    sub_category: str | None = None
    tags: list[str] | None = None


class Orchestration(MongoDocument):
    """Multi-agent orchestration definition document."""

    workspace_id: str
    name: str
    framework: OrchestrationFramework = OrchestrationFramework.LANGGRAPH
    architecture_type: ArchitectureType = ArchitectureType.REACT
    config: dict[str, Any] | None = None


class LLMConfig(MongoDocument):
    """Per-workspace LLM provider configuration document."""

    workspace_id: str
    name: str
    provider: LLMProviderEnum = LLMProviderEnum.OLLAMA
    model_name: str
    credentials: dict[str, Any] | None = None
    temperature: float = 0.7
    max_tokens: int = 2048


class PipelineArtifact(MongoDocument):
    """Artifact metadata document for COS-backed pipeline outputs."""

    workspace_id: str
    phase: str
    artifact_type: str
    name: str
    cos_bucket: str
    cos_key: str
    cos_endpoint: str
    url: str | None = None

# Made with Bob
