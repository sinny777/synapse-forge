"""
NeuralToolRouter — SQLAlchemy ORM Models

Defines the core tables from the Platform Requirements:
  • Workspace   — multi-tenant container
  • Tool        — registered tools (REST / MCP) with pgvector embedding
  • Agent       — LLM agent definitions
  • Orchestration — workflow definitions (LangGraph, CrewAI, AutoGen)
  • MCPServer   — MCP server configurations (stdio/sse)

All tables use UUID primary keys and carry a workspace_id foreign key
(except Workspace itself) for strict multi-tenant isolation.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for all NTR models."""
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Workspace(Base, AuditMixin):
    """
    Multi-tenant workspace.

    Every other entity references a workspace_id so that tools, agents, and
    orchestrations are scoped to a single tenant context.
    """
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Per-workspace embedding configuration ---
    # Each workspace can choose its own embedding model and dimension.
    # The dimension here is informational / enforced at application level;
    # the Tool.embedding column is untyped vector (accepts any dimension).
    embedding_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="sentence-transformers/all-MiniLM-L6-v2",
        server_default="sentence-transformers/all-MiniLM-L6-v2",
    )
    embedding_dim: Mapped[int] = mapped_column(
        Integer, nullable=False, default=384, server_default="384"
    )
    
    shared_with: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Relationships
    tools = relationship("Tool", back_populates="workspace", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="workspace", cascade="all, delete-orphan")
    orchestrations = relationship(
        "Orchestration", back_populates="workspace", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Workspace id={self.id!s} name={self.name!r}>"


class Tool(Base, AuditMixin):
    """
    A unified tool registry entry.
    
    Can represent:
    1. A standalone REST tool.
    2. An MCP Server configuration (provider).
    3. An individual tool discovered from an MCP Server.
    """
    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    
    # Common fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[ToolType] = mapped_column(
        Enum(ToolType, name="tool_type", create_constraint=True),
        nullable=False,
        default=ToolType.REST,
    )
    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    
    # REST / MCP Tool specific
    connection_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    schema_def: Mapped[dict | None] = mapped_column(
        "schema", JSONB, nullable=True
    )

    # MCP Server specific (for type=MCP_SERVER)
    transport: Mapped[MCPTransportType | None] = mapped_column(
        Enum(MCPTransportType, name="mcp_transport_type", create_constraint=True),
        nullable=True,
    )
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    args: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    env: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Status and Discovery
    status: Mapped[MCPServerStatus] = mapped_column(
        Enum(MCPServerStatus, name="mcp_server_status", create_constraint=True),
        nullable=False,
        default=MCPServerStatus.ACTIVE,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Hierarchical link (MCP_TOOL -> MCP_SERVER)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=True
    )
    
    # pgvector embedding
    embedding = Column(Vector(), nullable=True)

    # Relationships
    workspace = relationship("Workspace", back_populates="tools")
    parent = relationship("Tool", remote_side=[id], back_populates="children")
    children = relationship("Tool", back_populates="parent", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_tools_workspace_id", "workspace_id"),
        Index("ix_tools_name", "name"),
        Index("ix_tools_type", "type"),
        Index("ix_tools_parent_id", "parent_id"),
    )

    def __repr__(self) -> str:
        return f"<Tool id={self.id!s} name={self.name!r} type={self.type.value}>"


class Agent(Base, AuditMixin):
    """
    An LLM agent definition bound to a workspace.

    ``attached_tool_ids`` stores a list of Tool UUIDs that this agent
    is allowed to invoke.  At runtime, NeuralToolRouter further narrows
    these down to the most relevant subset for each prompt.
    """
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attached_tool_ids: Mapped[list[str] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="agents")

    __table_args__ = (
        Index("ix_agents_workspace_id", "workspace_id"),
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id!s} name={self.name!r}>"


class Orchestration(Base, AuditMixin):
    """
    A multi-agent orchestration / workflow definition.

    ``config`` holds the JSONB map of agent roles, graph topology,
    and framework-specific settings consumed by the LangGraph (or
    CrewAI / AutoGen) engine at execution time.
    """
    __tablename__ = "orchestrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    framework: Mapped[OrchestrationFramework] = mapped_column(
        Enum(OrchestrationFramework, name="orchestration_framework", create_constraint=True),
        nullable=False,
        default=OrchestrationFramework.LANGGRAPH,
    )
    architecture_type: Mapped[ArchitectureType] = mapped_column(
        Enum(ArchitectureType, name="architecture_type", create_constraint=True),
        nullable=False,
        default=ArchitectureType.REACT,
    )
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    workspace = relationship("Workspace", back_populates="orchestrations")

    __table_args__ = (
        Index("ix_orchestrations_workspace_id", "workspace_id"),
    )

    def __repr__(self) -> str:
        return f"<Orchestration id={self.id!s} name={self.name!r} framework={self.framework.value}>"

# Made with Bob
