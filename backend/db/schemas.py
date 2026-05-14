"""
NeuralToolRouter — Pydantic v2 Schemas

Request / Response schemas for the platform API.
Separated from the ORM models to keep validation concerns distinct.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

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
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None
    shared_with: list[str] | None = None


# ========================== TOOL ===========================================


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
    system_prompt: str | None = Field(
        default=None, examples=["You are a helpful banking assistant."]
    )
    llm_provider: str | None = Field(default=None, examples=["openai"])
    llm_model: str | None = Field(default=None, examples=["gpt-4o"])
    attached_tool_ids: list[uuid.UUID] | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    system_prompt: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    attached_tool_ids: list[uuid.UUID] | None = None


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    system_prompt: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    attached_tool_ids: list[uuid.UUID] | None = None
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
