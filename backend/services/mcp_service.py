"""
MCP Service — Dynamic Tool Discovery and Lifecycle Management

Handles the background initialization of MCP clients, tool discovery (list_tools),
and persistence/caching of discovered tools in the main tools registry.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Tool, ToolType, MCPServerStatus, Workspace
from tool_router.mcp_client import MCPClient, ToolSchema
from tool_router.config import MCPConfig
from services.embedding_service import embedding_service

logger = logging.getLogger("ntr.services.mcp")

class MCPService:
    """
    Manages MCP server lifecycles and tool discovery using the unified Tool model.
    """
    
    @staticmethod
    async def discover_tools(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        server_tool: Tool
    ) -> List[Tool]:
        """
        Connect to an MCP server (represented as a Tool of type MCP_SERVER), 
        list its tools, and sync them as child Tool entries.
        
        Args:
            session: Async database session
            workspace_id: Current workspace ID
            server_tool: The Tool model instance (type must be MCP_SERVER)
            
        Returns:
            List of created/updated child Tool models
        """
        if server_tool.type != ToolType.MCP_SERVER:
            logger.warning(f"Tool {server_tool.id} is not an MCP_SERVER. Skipping discovery.")
            return []

        logger.info(f"Starting discovery for MCP server: {server_tool.name}")
        
        # 1. Prepare MCP Client configuration from the unified Tool model
        server_config = {
            "transport": server_tool.transport.value,
        }
        if server_tool.transport.value == "stdio":
            server_config.update({
                "command": server_tool.command,
                "args": server_tool.args or [],
                "env": server_tool.env or {},
            })
        else:
            server_config["url"] = server_tool.url
            
        # server_tool.id as string for unique client ID
        mcp_id = str(server_tool.id)
        mcp_config = MCPConfig(servers={mcp_id: server_config})
        client = MCPClient(mcp_config)
        
        discovered_tools: List[Tool] = []
        
        try:
            # 2. Connect
            connected = await client.connect_server(mcp_id, server_config)
            if not connected:
                raise Exception("Failed to connect to MCP server")
            
            # 3. List Tools
            mcp_tools = await client.list_tools(mcp_id)
            await client.close_all()
            
            # 4. Sync with Database
            # Delete existing child tools for this server to ensure clean sync
            await session.execute(
                delete(Tool).where(Tool.parent_id == server_tool.id)
            )
            
            # Get workspace for embedding config
            ws = await session.get(Workspace, workspace_id)
            
            for m_tool in mcp_tools:
                # Create child Tool record (type MCP_TOOL)
                child_tool = Tool(
                    workspace_id=workspace_id,
                    parent_id=server_tool.id,
                    name=m_tool.name,
                    description=m_tool.description,
                    type=ToolType.MCP_TOOL,
                    connection_config={
                        "server_id": mcp_id,
                        "mcp_id": m_tool.id
                    },
                    schema_def=m_tool.parameters,
                    is_enabled=False # Individual tools are disabled by default
                )
                
                if ws:
                    try:
                        # Generate embedding for discovery
                        embedding_text = f"{m_tool.name}: {m_tool.description}"
                        embedding = embedding_service.embed_text(
                            embedding_text, 
                            model_name=ws.embedding_model
                        )
                        child_tool.embedding = embedding
                    except Exception as emb_err:
                        logger.warning(f"Failed to generate embedding for tool {m_tool.name}: {emb_err}")
                
                session.add(child_tool)
                discovered_tools.append(child_tool)
            
            # 5. Update Server Status
            server_tool.status = MCPServerStatus.ACTIVE
            server_tool.last_error = None
            
            logger.info(f"✓ Discovered and synced {len(discovered_tools)} tools for {server_tool.name}")
            
        except Exception as e:
            logger.error(f"Error during tool discovery for {server_tool.name}: {e}")
            server_tool.status = MCPServerStatus.ERROR
            server_tool.last_error = str(e)
            raise e
            
        finally:
            await session.flush()
            
        return discovered_tools

    @staticmethod
    async def restart_server_discovery(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        tool_id: uuid.UUID
    ):
        """
        Triggered when a server tool is updated or manually refreshed.
        """
        server_tool = await session.get(Tool, tool_id)
        if not server_tool:
            return
        
        return await MCPService.discover_tools(session, workspace_id, server_tool)

