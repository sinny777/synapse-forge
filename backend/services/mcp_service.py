"""
MCP Service — Dynamic Tool Discovery and Lifecycle Management

Handles MCP client initialization, tool discovery, and persistence of discovered
child tools in MongoDB.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from db.engine import normalize_mongo_document, prepare_document, utcnow
from db.models import MCPServerStatus, Tool, ToolType, Workspace
from services.embedding_service import embedding_service
from tool_router.config import MCPConfig
from tool_router.mcp_client import MCPClient

logger = logging.getLogger("ntr.services.mcp")


class MCPService:
    """Manages MCP server lifecycles and tool discovery using MongoDB."""

    @staticmethod
    async def discover_tools(
        db: AsyncIOMotorDatabase,
        workspace_id: uuid.UUID | str,
        server_tool: Tool,
    ) -> list[Tool]:
        """
        Connect to an MCP server, list its tools, and sync them as child Tool entries.
        """
        if server_tool.type != ToolType.MCP_SERVER:
            logger.warning(
                "Tool %s is not an MCP_SERVER. Skipping discovery.",
                server_tool.id,
            )
            return []

        if server_tool.transport is None:
            raise ValueError("MCP server transport is required for discovery")

        logger.info("Starting discovery for MCP server: %s", server_tool.name)

        server_config: dict[str, Any] = {
            "transport": server_tool.transport.value,
        }
        if server_tool.transport.value == "stdio":
            server_config.update(
                {
                    "command": server_tool.command,
                    "args": server_tool.args or [],
                    "env": server_tool.env or {},
                }
            )
        else:
            server_config["url"] = server_tool.url

        mcp_id = str(server_tool.id)
        client = MCPClient(MCPConfig(servers={mcp_id: server_config}))
        discovered_tools: list[Tool] = []
        workspace_key = str(workspace_id)

        try:
            connected = await client.connect_server(mcp_id, server_config)
            if not connected:
                raise RuntimeError("Failed to connect to MCP server")

            mcp_tools = await client.list_tools(mcp_id)

            await db.tools.delete_many({"parent_id": server_tool.id})

            workspace_doc = await db.workspaces.find_one({"_id": workspace_key})
            workspace_data = normalize_mongo_document(workspace_doc)
            workspace = (
                Workspace.model_validate(workspace_data)
                if workspace_data is not None
                else None
            )

            for m_tool in mcp_tools:
                child_tool = Tool(
                    workspace_id=workspace_key,
                    parent_id=server_tool.id,
                    name=m_tool.name,
                    description=m_tool.description,
                    type=ToolType.MCP_TOOL,
                    connection_config={
                        "server_id": mcp_id,
                        "mcp_id": m_tool.id,
                    },
                    schema_def=m_tool.parameters,
                    is_enabled=False,
                )

                if workspace is not None:
                    try:
                        embedding_text = f"{m_tool.name}: {m_tool.description or ''}".strip()
                        child_tool.embedding = embedding_service.embed_text(
                            embedding_text,
                            model_name=workspace.embedding_model,
                        )
                    except Exception as emb_err:
                        logger.warning(
                            "Failed to generate embedding for tool %s: %s",
                            m_tool.name,
                            emb_err,
                        )

                await db.tools.insert_one(prepare_document(child_tool.model_dump()))
                discovered_tools.append(child_tool)

            server_tool.status = MCPServerStatus.ACTIVE
            server_tool.last_error = None
            server_tool.updated_at = utcnow()

            await db.tools.replace_one(
                {"_id": server_tool.id},
                prepare_document(server_tool.model_dump()),
            )

            logger.info(
                "Discovered and synced %s tools for %s",
                len(discovered_tools),
                server_tool.name,
            )
            return discovered_tools

        except Exception as exc:
            logger.error(
                "Error during tool discovery for %s: %s",
                server_tool.name,
                exc,
            )
            server_tool.status = MCPServerStatus.ERROR
            server_tool.last_error = str(exc)
            server_tool.updated_at = utcnow()

            await db.tools.replace_one(
                {"_id": server_tool.id},
                prepare_document(server_tool.model_dump()),
            )
            raise
        finally:
            await client.close_all()

    @staticmethod
    async def restart_server_discovery(
        db: AsyncIOMotorDatabase,
        workspace_id: uuid.UUID | str,
        tool_id: uuid.UUID | str,
    ) -> list[Tool] | None:
        """Trigger discovery for an existing MCP server tool."""
        server_doc = await db.tools.find_one({"_id": str(tool_id)})
        server_data = normalize_mongo_document(server_doc)
        if server_data is None:
            return None

        server_tool = Tool.model_validate(server_data)
        return await MCPService.discover_tools(db, workspace_id, server_tool)

