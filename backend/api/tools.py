"""
SynapseForge — Tool API Routes

CRUD operations for tools within a workspace.
On creation (and update when description changes), an embedding is
generated via the workspace's configured embedding model and stored
in the pgvector ``embedding`` column for semantic search.
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.engine import AsyncSessionDep
from db.models import Tool, Workspace, ToolType, MCPServerStatus
from db.schemas import ToolCreate, ToolUpdate, ToolRead
from services.embedding_service import embedding_service
from services.mcp_service import MCPService
from api.auth import get_current_user
from api.dependencies import require_workspace_access

logger = logging.getLogger("ntr.api.tools")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/tools",
    tags=["Tools"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_workspace_or_404(
    session: AsyncSession, workspace_id: uuid.UUID
) -> Workspace:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


def _generate_embedding(
    ws: Workspace, name: str, description: str | None, schema_def: dict | None
) -> list[float]:
    """Generate a tool embedding using the workspace's configured model."""
    return embedding_service.embed_tool(
        name=name,
        description=description,
        schema_def=schema_def,
        model_name=ws.embedding_model,
    )


def _mask_tool_secrets(tool: Tool) -> Tool:
    """Mask sensitive data in Tool responses."""
    if tool.env:
        tool.env = {k: "***" for k in tool.env.keys()}
    return tool


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ToolRead])
async def list_tools(workspace_id: uuid.UUID, session: AsyncSessionDep):
    """
    List all tools in a workspace.
    
    Includes REST tools, MCP Servers, and Discovered MCP Tools.
    """
    await _get_workspace_or_404(session, workspace_id)
    result = await session.execute(
        select(Tool)
        .where(Tool.workspace_id == workspace_id)
        .order_by(Tool.created_at.desc())
    )
    tools = result.scalars().all()
    return [_mask_tool_secrets(t) for t in tools]


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
async def create_tool(
    workspace_id: uuid.UUID, body: ToolCreate, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """
    Register a new tool or MCP server.

    If creating an MCP_SERVER, discovery will be triggered automatically.
    """
    ws = await require_workspace_access(workspace_id, session, user, require_write=True)
    email = user.get("email")

    # Generate embedding for REST or individual tools
    # MCP Servers (providers) might not need semantic embedding themselves,
    # but their discovered tools will.
    vec = None
    if body.type != ToolType.MCP_SERVER:
        vec = _generate_embedding(ws, body.name, body.description, body.schema_def)

    tool = Tool(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        type=body.type,
        is_enabled=body.is_enabled,
        connection_config=body.connection_config,
        schema_def=body.schema_def,
        transport=body.transport,
        command=body.command,
        args=body.args,
        env=body.env,
        url=body.url,
        status=body.status,
        parent_id=body.parent_id,
        embedding=vec,
        created_by=email,
        updated_by=email,
    )
    
    session.add(tool)
    await session.flush()
    
    # Handle MCP Server Discovery
    if tool.type == ToolType.MCP_SERVER:
        try:
            await MCPService.discover_tools(session, workspace_id, tool)
        except Exception as e:
            logger.warning(f"Initial tool discovery failed for {tool.name}: {e}")
            # We don't fail the create, status is updated in discovery

    await session.refresh(tool)
    return _mask_tool_secrets(tool)


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(
    workspace_id: uuid.UUID, tool_id: uuid.UUID, session: AsyncSessionDep
):
    """Get a single tool by ID."""
    await _get_workspace_or_404(session, workspace_id)
    tool = await session.get(Tool, tool_id)
    if tool is None or tool.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Tool not found")
    return _mask_tool_secrets(tool)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{tool_id}", response_model=ToolRead)
async def update_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: ToolUpdate,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user)
):
    """Update a tool or MCP server configuration."""
    ws = await require_workspace_access(workspace_id, session, user, require_write=True)
    tool = await session.get(Tool, tool_id)
    if tool is None or tool.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Tool not found")

    update_data = body.model_dump(exclude_unset=True)
    
    # Metadata fields that trigger re-embedding
    meta_fields = {"name", "description", "schema_def"}
    needs_reembed = any(k in update_data for k in meta_fields) and tool.type != ToolType.MCP_SERVER
    
    # Connection fields that trigger re-discovery for MCP servers
    discovery_fields = {"transport", "command", "args", "env", "url"}
    needs_rediscovery = any(k in update_data for k in discovery_fields) and tool.type == ToolType.MCP_SERVER

    for field, value in update_data.items():
        setattr(tool, field, value)
        
    tool.updated_by = user.get("email")

    # Automatically enable/disable child tools if the parent MCP server is toggled
    if "is_enabled" in update_data and tool.type == ToolType.MCP_SERVER:
        from sqlalchemy import update as sql_update
        stmt = sql_update(Tool).where(Tool.parent_id == str(tool_id)).values(is_enabled=update_data["is_enabled"])
        await session.execute(stmt)

    if needs_reembed:
        tool.embedding = _generate_embedding(
            ws, tool.name, tool.description, tool.schema_def
        )
        logger.info("Re-embedded tool %s", tool_id)

    await session.flush()
    
    if needs_rediscovery:
        try:
            await MCPService.discover_tools(session, workspace_id, tool)
        except Exception as e:
            logger.warning(f"Re-discovery failed for {tool.name}: {e}")

    await session.refresh(tool)
    return _mask_tool_secrets(tool)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    workspace_id: uuid.UUID, tool_id: uuid.UUID, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """Delete a tool (cascades to children for MCP servers)."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    tool = await session.get(Tool, tool_id)
    if tool is None or tool.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Tool not found")

    await session.delete(tool)
    logger.info("Deleted tool %s", tool_id)


# ---------------------------------------------------------------------------
# TEST MCP CONNECTION
# ---------------------------------------------------------------------------

@router.post("/{tool_id}/test")
async def test_tool_connection(
    workspace_id: uuid.UUID, tool_id: uuid.UUID, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """Test connectivity for an MCP_SERVER tool."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    tool = await session.get(Tool, tool_id)
    if not tool or tool.type != ToolType.MCP_SERVER:
        raise HTTPException(status_code=400, detail="Not an MCP server")

    try:
        from tool_router.mcp_client import MCPClient
        from tool_router.config import MCPConfig
        
        server_config = {"transport": tool.transport.value}
        if tool.transport.value == "stdio":
            server_config.update({
                "command": tool.command,
                "args": tool.args or [],
                "env": tool.env or {},
            })
        else:
            server_config["url"] = tool.url
            
        mcp_id = str(tool.id)
        client = MCPClient(MCPConfig(servers={mcp_id: server_config}))
        
        success = await client.connect_server(mcp_id, server_config)
        if success:
            tools = await client.list_tools(mcp_id)
            await client.close_all()
            tool.status = MCPServerStatus.ACTIVE
            tool.last_error = None
            tool.updated_by = user.get("email")
            await session.flush()
            return {"success": True, "tools_count": len(tools)}
        else:
            tool.status = MCPServerStatus.ERROR
            tool.last_error = "Failed to connect"
            tool.updated_by = user.get("email")
            await session.flush()
            return {"success": False, "error": "Connection failed"}
    except Exception as e:
        tool.status = MCPServerStatus.ERROR
        tool.last_error = str(e)
        tool.updated_by = user.get("email")
        await session.flush()
        return {"success": False, "error": str(e)}

# NOTE: Import/clone functionality has been moved to api/workspace_cloning.py
# which provides /api/clone/tools and /api/clone/agents endpoints.

