"""
SynapseForge — Tool API Routes

CRUD operations for tools within a workspace using MongoDB.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.auth import get_current_user
from api.dependencies import require_workspace_access
from db.engine import get_db, normalize_mongo_document, prepare_document, utcnow
from db.models import MCPServerStatus, Tool, ToolType, Workspace
from db.schemas import ToolCreate, ToolRead, ToolUpdate
from services.embedding_service import embedding_service
from services.mcp_service import MCPService

logger = logging.getLogger("ntr.api.tools")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/tools",
    tags=["Tools"],
)


def _tool_from_doc(document: dict | None) -> Tool | None:
    """Convert a MongoDB document into a Tool model."""
    normalized = normalize_mongo_document(document)
    if normalized is None:
        return None
    return Tool.model_validate(normalized)


async def _get_workspace_or_404(
    db: AsyncIOMotorDatabase,
    workspace_id: uuid.UUID,
) -> Workspace:
    document = await db.workspaces.find_one({"_id": str(workspace_id)})
    normalized = normalize_mongo_document(document)
    if normalized is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return Workspace.model_validate(normalized)


def _generate_embedding(
    ws: Workspace,
    name: str,
    description: str | None,
    schema_def: dict | None,
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
    masked_tool = tool.model_copy(deep=True)
    if masked_tool.env:
        masked_tool.env = {key: "***" for key in masked_tool.env.keys()}
    return masked_tool


@router.get("", response_model=list[ToolRead])
async def list_tools(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all tools in a workspace."""
    await _get_workspace_or_404(db, workspace_id)
    cursor = db.tools.find({"workspace_id": str(workspace_id)}).sort("created_at", -1)

    tools: list[ToolRead] = []
    async for document in cursor:
        tool = _tool_from_doc(document)
        if tool is not None:
            tools.append(ToolRead.model_validate(_mask_tool_secrets(tool)))
    return tools


@router.post("", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
async def create_tool(
    workspace_id: uuid.UUID,
    body: ToolCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Register a new tool or MCP server.

    If creating an MCP_SERVER, discovery will be triggered automatically.
    """
    ws = await require_workspace_access(workspace_id, db, user, require_write=True)
    email = user.get("email")

    vec = None
    if body.type != ToolType.MCP_SERVER:
        vec = _generate_embedding(ws, body.name, body.description, body.schema_def)

    tool = Tool(
        workspace_id=str(workspace_id),
        name=body.name,
        description=body.description,
        type=ToolType(body.type.value) if hasattr(body.type, "value") else ToolType(body.type),
        is_enabled=body.is_enabled,
        connection_config=body.connection_config,
        schema_def=body.schema_def,
        transport=(
            None
            if body.transport is None
            else body.transport.value
        ),
        command=body.command,
        args=body.args,
        env=body.env,
        url=body.url,
        status=(
            body.status.value
            if hasattr(body.status, "value")
            else body.status
        ),
        parent_id=str(body.parent_id) if body.parent_id else None,
        embedding=vec,
        created_by=email,
        updated_by=email,
    )

    await db.tools.insert_one(prepare_document(tool.model_dump()))

    if tool.type == ToolType.MCP_SERVER:
        try:
            await MCPService.discover_tools(db, workspace_id, tool)
        except Exception as exc:
            logger.warning("Initial tool discovery failed for %s: %s", tool.name, exc)

    return ToolRead.model_validate(_mask_tool_secrets(tool))


@router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a single tool by ID."""
    await _get_workspace_or_404(db, workspace_id)
    tool = _tool_from_doc(await db.tools.find_one({"_id": str(tool_id)}))
    if tool is None or tool.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Tool not found")
    return ToolRead.model_validate(_mask_tool_secrets(tool))


@router.put("/{tool_id}", response_model=ToolRead)
async def update_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: ToolUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update a tool or MCP server configuration."""
    ws = await require_workspace_access(workspace_id, db, user, require_write=True)
    tool = _tool_from_doc(await db.tools.find_one({"_id": str(tool_id)}))
    if tool is None or tool.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Tool not found")

    update_data = body.model_dump(exclude_unset=True)

    meta_fields = {"name", "description", "schema_def"}
    needs_reembed = any(key in update_data for key in meta_fields) and tool.type != ToolType.MCP_SERVER

    discovery_fields = {"transport", "command", "args", "env", "url"}
    needs_rediscovery = any(key in update_data for key in discovery_fields) and tool.type == ToolType.MCP_SERVER

    for field, value in update_data.items():
        if field == "parent_id" and value is not None:
            setattr(tool, field, str(value))
        elif field in {"transport", "status"} and value is not None and hasattr(value, "value"):
            setattr(tool, field, value.value)
        else:
            setattr(tool, field, value)

    tool.updated_by = user.get("email")
    tool.updated_at = utcnow()

    if "is_enabled" in update_data and tool.type == ToolType.MCP_SERVER:
        await db.tools.update_many(
            {"parent_id": str(tool_id)},
            {
                "$set": {
                    "is_enabled": update_data["is_enabled"],
                    "updated_at": utcnow(),
                    "updated_by": user.get("email"),
                }
            },
        )

    if needs_reembed:
        tool.embedding = _generate_embedding(ws, tool.name, tool.description, tool.schema_def)
        logger.info("Re-embedded tool %s", tool_id)

    await db.tools.replace_one({"_id": str(tool_id)}, prepare_document(tool.model_dump()))

    if needs_rediscovery:
        try:
            await MCPService.discover_tools(db, workspace_id, tool)
        except Exception as exc:
            logger.warning("Re-discovery failed for %s: %s", tool.name, exc)

    return ToolRead.model_validate(_mask_tool_secrets(tool))


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete a tool (cascades to children for MCP servers)."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    tool = _tool_from_doc(await db.tools.find_one({"_id": str(tool_id)}))
    if tool is None or tool.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Tool not found")

    await db.tools.delete_many(
        {
            "$or": [
                {"_id": str(tool_id)},
                {"parent_id": str(tool_id)},
            ]
        }
    )
    logger.info("Deleted tool %s", tool_id)


@router.post("/{tool_id}/test")
async def test_tool_connection(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Test connectivity for an MCP_SERVER tool."""
    await require_workspace_access(workspace_id, db, user, require_write=True)
    tool = _tool_from_doc(await db.tools.find_one({"_id": str(tool_id)}))
    if not tool or tool.type != ToolType.MCP_SERVER:
        raise HTTPException(status_code=400, detail="Not an MCP server")

    if tool.transport is None:
        raise HTTPException(status_code=400, detail="MCP server transport is not configured")

    try:
        from tool_router.config import MCPConfig
        from tool_router.mcp_client import MCPClient

        server_config: dict[str, object] = {"transport": tool.transport.value}
        if tool.transport.value == "stdio":
            server_config["command"] = tool.command or ""
            server_config["args"] = tool.args or []
            server_config["env"] = tool.env or {}
        else:
            if not tool.url:
                raise HTTPException(status_code=400, detail="MCP server URL is not configured")
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
            tool.updated_at = utcnow()
            await db.tools.replace_one({"_id": str(tool_id)}, prepare_document(tool.model_dump()))
            return {"success": True, "tools_count": len(tools)}

        tool.status = MCPServerStatus.ERROR
        tool.last_error = "Failed to connect"
        tool.updated_by = user.get("email")
        tool.updated_at = utcnow()
        await db.tools.replace_one({"_id": str(tool_id)}, prepare_document(tool.model_dump()))
        return {"success": False, "error": "Connection failed"}
    except Exception as exc:
        tool.status = MCPServerStatus.ERROR
        tool.last_error = str(exc)
        tool.updated_by = user.get("email")
        tool.updated_at = utcnow()
        await db.tools.replace_one({"_id": str(tool_id)}, prepare_document(tool.model_dump()))
        return {"success": False, "error": str(exc)}

# NOTE: Import/clone functionality has been moved to api/workspace_cloning.py
# which provides /api/clone/tools and /api/clone/agents endpoints.

