"""
NeuralToolRouter — SQLAlchemy ORM Models

Defines the four core tables from the Platform Requirements:
  • Workspace   — multi-tenant container
  • Tool        — registered tools (REST / MCP) with pgvector embedding
  • Agent       — LLM agent definitions
  • Orchestration — workflow definitions (LangGraph, CrewAI, AutoGen)

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


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ToolType(str, enum.Enum):
    """Transport type used to connect to the tool."""
    REST = "REST"
    MCP_SERVER = "MCP_SERVER"


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
# Helper
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Workspace(Base):
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    tools = relationship("Tool", back_populates="workspace", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="workspace", cascade="all, delete-orphan")
    orchestrations = relationship(
        "Orchestration", back_populates="workspace", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Workspace id={self.id!s} name={self.name!r}>"


class Tool(Base):
    """
    A registered tool (REST endpoint or MCP server action).

    The ``embedding`` column stores a dense vector produced by
    NeuralToolRouter so the platform can perform pgvector similarity
    search to find the top-K most relevant tools for a given prompt.
    """
    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[ToolType] = mapped_column(
        Enum(ToolType, name="tool_type", create_constraint=True),
        nullable=False,
        default=ToolType.REST,
    )
    connection_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    schema_def: Mapped[dict | None] = mapped_column(
        "schema", JSONB, nullable=True
    )

    # pgvector embedding — UNTYPED vector (no fixed dimension).
    # Each workspace defines its own embedding_model + embedding_dim.
    # Since queries always filter by workspace_id, dimension consistency
    # is guaranteed.  Untyped vectors accept any dimension (384, 768, 1536…).
    embedding = Column(Vector(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="tools")

    # Indexes
    __table_args__ = (
        Index("ix_tools_workspace_id", "workspace_id"),
        Index("ix_tools_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Tool id={self.id!s} name={self.name!r} type={self.type.value}>"


class Agent(Base):
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="agents")

    __table_args__ = (
        Index("ix_agents_workspace_id", "workspace_id"),
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id!s} name={self.name!r}>"


class Orchestration(Base):
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="orchestrations")

    __table_args__ = (
        Index("ix_orchestrations_workspace_id", "workspace_id"),
    )

    def __repr__(self) -> str:
        return f"<Orchestration id={self.id!s} name={self.name!r} framework={self.framework.value}>"
