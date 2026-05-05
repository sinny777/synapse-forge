"""
MCP Client Utility Module

This module provides a unified interface for connecting to and interacting with
Model Context Protocol (MCP) servers. Supports both Stdio and SSE transports.
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from pathlib import Path
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from tool_router.config import MCPConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ToolSchema:
    """Normalized tool schema representation."""
    
    id: str  # Unique identifier (server_name.tool_name)
    name: str  # Tool name
    description: str  # Tool description
    parameters: Dict[str, Any]  # JSON schema for parameters
    server_name: str  # Source MCP server
    raw_schema: Dict[str, Any]  # Original MCP tool schema
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "server_name": self.server_name,
            "raw_schema": self.raw_schema
        }
    
    def get_embedding_text(self) -> str:
        """
        Get text representation for embedding.
        Combines name, description, and parameter info.
        """
        param_text = ""
        if self.parameters and "properties" in self.parameters:
            param_names = list(self.parameters["properties"].keys())
            param_text = f" Parameters: {', '.join(param_names)}"
        
        return f"{self.name}: {self.description}{param_text}"


class MCPClient:
    """
    Unified MCP client for connecting to and interacting with MCP servers.
    Supports Stdio transport (SSE support can be added).
    """
    
    def __init__(self, config: MCPConfig):
        """
        Initialize MCP client.
        
        Args:
            config: MCP configuration
        """
        self.config = config
        self.sessions: Dict[str, ClientSession] = {}
        self.tools: Dict[str, ToolSchema] = {}  # tool_id -> ToolSchema
        self.server_tools: Dict[str, List[str]] = {}  # server_name -> [tool_ids]
        self.exit_stack = AsyncExitStack()
        
    async def connect_server(self, server_name: str, server_config: Dict[str, Any]) -> bool:
        """
        Connect to a single MCP server.
        
        Args:
            server_name: Name of the server
            server_config: Server configuration dict
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to MCP server: {server_name}")
            
            # Extract server parameters
            command = server_config.get("command")
            args = server_config.get("args", [])
            env = server_config.get("env", {})
            transport = server_config.get("transport", "stdio")
            
            if transport != "stdio":
                logger.warning(f"Transport {transport} not yet supported, skipping {server_name}")
                return False
            
            logger.debug(f"Server command: {command} {' '.join(args)}")
            
            # Create server parameters
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )
            
            # Connect using stdio with timeout
            logger.debug(f"Creating stdio context...")
            read, write = await asyncio.wait_for(
                self.exit_stack.enter_async_context(stdio_client(server_params)),
                timeout=10.0
            )
            
            logger.debug(f"Creating client session...")
            # Create session
            session = await asyncio.wait_for(
                self.exit_stack.enter_async_context(ClientSession(read, write)),
                timeout=10.0
            )
            
            logger.debug(f"Initializing session...")
            await asyncio.wait_for(
                session.initialize(),
                timeout=10.0
            )
            
            # Store session and context for cleanup
            self.sessions[server_name] = session
            
            logger.info(f"✓ Connected to {server_name}")
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout connecting to {server_name}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to {server_name}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    async def connect_all(self) -> Dict[str, bool]:
        """
        Connect to all configured MCP servers.
        
        Returns:
            Dictionary mapping server names to connection status
        """
        results = {}
        
        for server_name, server_config in self.config.servers.items():
            success = await self.connect_server(server_name, server_config)
            results[server_name] = success
        
        return results
    
    async def list_tools(self, server_name: Optional[str] = None) -> List[ToolSchema]:
        """
        List tools from one or all connected servers.
        
        Args:
            server_name: Specific server name, or None for all servers
        
        Returns:
            List of ToolSchema objects
        """
        tools = []
        
        servers_to_query = [server_name] if server_name else list(self.sessions.keys())
        
        for srv_name in servers_to_query:
            if srv_name not in self.sessions:
                logger.warning(f"Server {srv_name} not connected")
                continue
            
            try:
                session = self.sessions[srv_name]
                response = await session.list_tools()
                
                for tool in response.tools:
                    tool_id = f"{srv_name}.{tool.name}"
                    
                    # Extract parameters schema
                    parameters = {}
                    if hasattr(tool, 'inputSchema'):
                        parameters = tool.inputSchema
                    
                    # Create normalized schema
                    schema = ToolSchema(
                        id=tool_id,
                        name=tool.name,
                        description=tool.description or "",
                        parameters=parameters,
                        server_name=srv_name,
                        raw_schema={
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": parameters
                        }
                    )
                    
                    tools.append(schema)
                    self.tools[tool_id] = schema
                
                # Track tools per server
                self.server_tools[srv_name] = [t.id for t in tools if t.server_name == srv_name]
                
                logger.info(f"Listed {len(response.tools)} tools from {srv_name}")
                
            except Exception as e:
                logger.error(f"Failed to list tools from {srv_name}: {e}")
        
        return tools
    
    async def call_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a tool by its ID.
        
        Args:
            tool_id: Tool identifier (server_name.tool_name)
            arguments: Tool arguments
        
        Returns:
            Tool execution result
        """
        if tool_id not in self.tools:
            raise ValueError(f"Tool {tool_id} not found")
        
        tool_schema = self.tools[tool_id]
        server_name = tool_schema.server_name
        tool_name = tool_schema.name
        
        if server_name not in self.sessions:
            raise ValueError(f"Server {server_name} not connected")
        
        try:
            session = self.sessions[server_name]
            
            logger.info(f"Calling tool: {tool_id} with args: {arguments}")
            
            result = await session.call_tool(tool_name, arguments)
            
            # Parse result content
            parsed_result = {
                "tool_id": tool_id,
                "success": True,
                "content": []
            }
            
            for content_item in result.content:
                if isinstance(content_item, TextContent):
                    parsed_result["content"].append({
                        "type": "text",
                        "text": content_item.text
                    })
                elif isinstance(content_item, ImageContent):
                    parsed_result["content"].append({
                        "type": "image",
                        "data": content_item.data,
                        "mimeType": content_item.mimeType
                    })
                elif isinstance(content_item, EmbeddedResource):
                    parsed_result["content"].append({
                        "type": "resource",
                        "resource": content_item.resource
                    })
            
            logger.info(f"✓ Tool {tool_id} executed successfully")
            return parsed_result
            
        except Exception as e:
            logger.error(f"Failed to call tool {tool_id}: {e}")
            return {
                "tool_id": tool_id,
                "success": False,
                "error": str(e)
            }
    
    async def get_tool_schema(self, tool_id: str) -> Optional[ToolSchema]:
        """
        Get schema for a specific tool.
        
        Args:
            tool_id: Tool identifier
        
        Returns:
            ToolSchema or None if not found
        """
        return self.tools.get(tool_id)
    
    async def search_tools(self, query: str) -> List[ToolSchema]:
        """
        Simple text search across tool names and descriptions.
        This is the fallback tool that can be called by the Heavy LLM.
        
        Args:
            query: Search query
        
        Returns:
            List of matching ToolSchema objects
        """
        query_lower = query.lower()
        matches = []
        
        for tool_schema in self.tools.values():
            # Search in name and description
            if (query_lower in tool_schema.name.lower() or
                query_lower in tool_schema.description.lower()):
                matches.append(tool_schema)
        
        logger.info(f"Search for '{query}' found {len(matches)} tools")
        return matches
    
    async def close_all(self):
        """Close all server connections."""
        try:
            await self.exit_stack.aclose()
            logger.info("Closed all MCP connections and contexts")
        except Exception as e:
            logger.error(f"Error closing contexts: {e}")
        
        self.sessions.clear()
        self.tools.clear()
        self.server_tools.clear()
    
    def get_all_tools(self) -> List[ToolSchema]:
        """Get all available tools."""
        return list(self.tools.values())
    
    def save_tool_cache(self, cache_path: Path):
        """
        Save tool schemas to cache file.
        
        Args:
            cache_path: Path to cache file
        """
        cache_data = {
            "tools": [tool.to_dict() for tool in self.tools.values()],
            "server_tools": self.server_tools
        }
        
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        logger.info(f"Saved {len(self.tools)} tools to cache: {cache_path}")
    
    def load_tool_cache(self, cache_path: Path) -> bool:
        """
        Load tool schemas from cache file.
        
        Args:
            cache_path: Path to cache file
        
        Returns:
            True if loaded successfully
        """
        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
            
            self.tools.clear()
            for tool_dict in cache_data.get("tools", []):
                tool_schema = ToolSchema(**tool_dict)
                self.tools[tool_schema.id] = tool_schema
            
            self.server_tools = cache_data.get("server_tools", {})
            
            logger.info(f"Loaded {len(self.tools)} tools from cache: {cache_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load tool cache: {e}")
            return False
    
    def load_predefined_tools(self, json_path: Path) -> bool:
        """
        Load tool schemas from a predefined JSON file.
        This is useful for testing without MCP server connections.
        
        Args:
            json_path: Path to JSON file containing tool definitions
        
        Returns:
            True if loaded successfully
        """
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            self.tools.clear()
            self.server_tools.clear()
            
            tools_list = data.get("tools", [])
            for tool_data in tools_list:
                tool_schema = ToolSchema(
                    id=tool_data["id"],
                    name=tool_data["name"],
                    description=tool_data["description"],
                    parameters=tool_data.get("parameters", {}),
                    server_name="predefined",
                    raw_schema=tool_data  # Store the original tool data
                )
                self.tools[tool_schema.id] = tool_schema
            
            # Group all tools under "predefined" server
            self.server_tools["predefined"] = list(self.tools.keys())
            
            logger.info(f"Loaded {len(self.tools)} predefined tools from {json_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load predefined tools: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False


async def main():
    """Example usage of MCPClient."""
    from tool_router.config import config
    
    # Create client
    client = MCPClient(config.mcp)
    
    # Connect to all servers
    print("Connecting to MCP servers...")
    results = await client.connect_all()
    
    for server_name, success in results.items():
        status = "✓" if success else "✗"
        print(f"{status} {server_name}")
    
    # List all tools
    print("\nListing tools...")
    tools = await client.list_tools()
    
    print(f"\nFound {len(tools)} tools:")
    for tool in tools:
        print(f"  - {tool.id}: {tool.description[:60]}...")
    
    # Save cache
    cache_path = Path("./data/tool_cache.json")
    client.save_tool_cache(cache_path)
    
    # Search tools
    print("\nSearching for 'file' tools...")
    matches = await client.search_tools("file")
    for match in matches:
        print(f"  - {match.id}")
    
    # Close connections
    await client.close_all()
    print("\nConnections closed.")


if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
