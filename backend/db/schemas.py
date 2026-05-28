"""
SynapseForge — Pydantic v2 Schemas

Request / Response schemas for the platform API.
Separated from the ORM models to keep validation concerns distinct.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums (mirror SQLAlchemy enums for API serialisation)
# ---------------------------------------------------------------------------

class ToolTypeEnum(str, Enum):
    REST = "REST"
    MCP_SERVER = "MCP_SERVER"
    MCP_TOOL = "MCP_TOOL"


class MCPTransportEnum(str, Enum):
    STDIO = "stdio"
    SSE = "sse"


class MCPServerStatusEnum(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class FrameworkEnum(str, Enum):
    LANGGRAPH = "LANGGRAPH"
    CREWAI = "CREWAI"
    AUTOGEN = "AUTOGEN"


class ArchitectureEnum(str, Enum):
    REACT = "REACT"
    SUPERVISOR = "SUPERVISOR"
    PLANNER = "PLANNER"


class WorkspaceStatusEnum(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"


# ========================== WORKSPACE ======================================

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["My Workspace"])
    description: str | None = Field(default=None, examples=["Banking agent workspace"])
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        max_length=255,
        examples=["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-base-en-v1.5"],
        description="HuggingFace model ID or provider path for embedding generation",
    )
    embedding_dim: int = Field(
        default=384,
        ge=32,
        le=4096,
        examples=[384, 768, 1024, 1536],
        description="Vector dimension produced by the selected embedding model",
    )


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    embedding_model: str | None = Field(default=None, max_length=255)
    embedding_dim: int | None = Field(default=None, ge=32, le=4096)


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    embedding_model: str
    embedding_dim: int
    is_default: bool = False
    status: WorkspaceStatusEnum = WorkspaceStatusEnum.STOPPED
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None
    shared_with: list[str] | None = None


# ========================== TOOL ===========================================


class CollaboratorAgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    system_prompt: str | None = None


class ToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["get_balance"])
    description: str | None = Field(default=None, examples=["Retrieve current account balance"])
    type: ToolTypeEnum = ToolTypeEnum.REST
    is_enabled: bool = Field(default=False, description="Whether the tool is active for the agent")
    
    # REST / MCP Tool config
    connection_config: dict[str, Any] | None = Field(
        default=None,
        examples=[{"url": "https://api.bank.com/balance", "method": "GET"}],
    )
    schema_def: dict[str, Any] | None = Field(
        default=None,
        description="OpenAPI / Function-calling schema for this tool",
    )
    
    # MCP Server Config (for type=MCP_SERVER)
    transport: MCPTransportEnum | None = Field(
        default=None,
        description="Transport protocol (required for MCP_SERVER)",
    )
    command: str | None = Field(default=None, max_length=500)
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = Field(default=None, max_length=500)
    
    # Status and Hierarchy
    status: MCPServerStatusEnum = Field(default=MCPServerStatusEnum.ACTIVE)
    parent_id: uuid.UUID | None = Field(
        default=None,
        description="ID of the parent provider/server",
    )

    @field_validator("command")
    @classmethod
    def validate_stdio_command(cls, v: str | None, info) -> str | None:
        if info.data.get("type") == ToolTypeEnum.MCP_SERVER and info.data.get("transport") == MCPTransportEnum.STDIO and not v:
            raise ValueError("command is required when transport is 'stdio'")
        return v

    @field_validator("url")
    @classmethod
    def validate_sse_url(cls, v: str | None, info) -> str | None:
        if info.data.get("type") == ToolTypeEnum.MCP_SERVER and info.data.get("transport") == MCPTransportEnum.SSE and not v:
            raise ValueError("url is required when transport is 'sse'")
        return v


class ToolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    type: ToolTypeEnum | None = None
    is_enabled: bool | None = None
    connection_config: dict[str, Any] | None = None
    schema_def: dict[str, Any] | None = None
    transport: MCPTransportEnum | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    status: MCPServerStatusEnum | None = None
    last_error: str | None = None
    parent_id: uuid.UUID | None = None


class ToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    type: ToolTypeEnum
    is_enabled: bool
    connection_config: dict[str, Any] | None = None
    schema_def: dict[str, Any] | None = None
    transport: MCPTransportEnum | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    status: MCPServerStatusEnum
    last_error: str | None = None
    parent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None



# ========================== AGENT ==========================================

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Banking Assistant"])
    description: str | None = Field(
        default=None,
        examples=["Research-focused agent that synthesizes evidence and cites sources."],
    )
    system_prompt: str | None = Field(
        default=None, examples=["You are a helpful banking assistant."]
    )
    llm_config_id: uuid.UUID | None = None
    use_neural_router: bool = False
    router_model_id: str | None = Field(default=None, max_length=255)
    router_top_k: int | None = Field(default=None, ge=1, le=50)
    memory_type: str | None = Field(default=None, examples=["buffer", "summary", "vector"])
    memory_window: int | None = Field(default=None, ge=1)
    max_iterations: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    attached_tool_ids: list[uuid.UUID] | None = None
    collaborator_agent_ids: list[uuid.UUID] | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = None
    llm_config_id: uuid.UUID | None = None
    use_neural_router: bool | None = None
    router_model_id: str | None = Field(default=None, max_length=255)
    router_top_k: int | None = Field(default=None, ge=1, le=50)
    memory_type: str | None = None
    memory_window: int | None = Field(default=None, ge=1)
    max_iterations: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    attached_tool_ids: list[uuid.UUID] | None = None
    collaborator_agent_ids: list[uuid.UUID] | None = None


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    system_prompt: str | None = None
    llm_config_id: uuid.UUID | None = None
    use_neural_router: bool = False
    router_model_id: str | None = None
    router_top_k: int | None = None
    memory_type: str | None = None
    memory_window: int | None = None
    max_iterations: int | None = None
    timeout_seconds: int | None = None
    attached_tool_ids: list[uuid.UUID] | None = None
    collaborator_agent_ids: list[uuid.UUID] | None = None
    collaborators: list[CollaboratorAgentRead] = []
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


# ========================== ORCHESTRATION ==================================

class OrchestrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["UHNW Banking Flow"])
    framework: FrameworkEnum = FrameworkEnum.LANGGRAPH
    architecture_type: ArchitectureEnum = ArchitectureEnum.REACT
    config: dict[str, Any] | None = Field(
        default=None,
        description="JSONB map of agent roles and graph topology",
        examples=[{
            "supervisor_agent_id": "uuid-here",
            "worker_agents": ["uuid-1", "uuid-2"],
        }],
    )


class OrchestrationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    framework: FrameworkEnum | None = None
    architecture_type: ArchitectureEnum | None = None
    config: dict[str, Any] | None = None


class OrchestrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    framework: FrameworkEnum
    architecture_type: ArchitectureEnum
    config: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


# ========================== LLM CONFIG =====================================

class LLMProviderSchemaEnum(str, Enum):
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


class LLMConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Teacher Config"])
    provider: LLMProviderSchemaEnum = LLMProviderSchemaEnum.OLLAMA
    model_name: str = Field(..., min_length=1, max_length=255, examples=["granite4.1:8b"])
    credentials: dict[str, Any] | None = Field(
        default=None,
        examples=[{"api_base": "http://localhost:11434"}],
        description="Provider-specific credentials (api_key, api_base, etc.)",
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1)


class LLMConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    provider: LLMProviderSchemaEnum | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=255)
    credentials: dict[str, Any] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)


class LLMConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    provider: LLMProviderSchemaEnum
    model_name: str
    credentials: dict[str, Any] | None = None
    temperature: float
    max_tokens: int
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


class AgentExecuteRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1, examples=["Summarize the claim and validate coverage."])


class AgentExecutionToolSummary(BaseModel):
    id: uuid.UUID
    name: str
    type: ToolTypeEnum


class AgentExecutionCollaboratorSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    llm_config_id: uuid.UUID | None = None
    attached_tool_ids: list[uuid.UUID] | None = None
    use_neural_router: bool = False
    router_top_k: int | None = None


class AgentExecutionResolvedConfig(BaseModel):
    id: uuid.UUID
    name: str
    provider: LLMProviderSchemaEnum
    model_name: str
    temperature: float
    max_tokens: int


class AgentExecutionResolvedAgent(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    system_prompt: str | None = None
    use_neural_router: bool = False
    router_model_id: str | None = None
    router_top_k: int | None = None
    memory_type: str | None = None
    memory_window: int | None = None
    max_iterations: int | None = None
    timeout_seconds: int | None = None
    llm_config: AgentExecutionResolvedConfig | None = None
    tools: list[AgentExecutionToolSummary] = []
    collaborators: list[AgentExecutionCollaboratorSummary] = []


class AgentExecutionTraceEvent(BaseModel):
    type: Literal["router", "llm_call", "thought", "reasoning", "tool_call", "tool_result", "assistant", "error", "complete"]
    label: str
    detail: str | None = None
    timestamp: datetime
    latency_ms: float | None = None
    status: Literal["running", "success", "error"] | None = "success"
    trace_id: str | None = None
    metadata: dict[str, Any] | None = None


# ========================== ROUTER PREDICT =================================

class RouterPredictRequest(BaseModel):
    """POST /api/router/predict — semantic tool retrieval."""
    user_prompt: str = Field(..., min_length=1, examples=["What is my account balance?"])
    workspace_id: uuid.UUID
    top_k: int = Field(default=5, ge=1, le=50)


class RouterPredictResponse(BaseModel):
    """Response from the semantic router prediction."""
    tools: list[ToolRead]
    cached: bool = False
    latency_ms: float

# Made with Bob
