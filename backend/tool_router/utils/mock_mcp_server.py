#!/usr/bin/env python3
"""
Mock MCP Server for Testing
Provides a simple set of tools for testing the ToolRouter framework.
"""

import asyncio
import json
import sys
from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Create server instance
app = Server("mock-test-server")


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="read_file",
            description="Read the contents of a file from the filesystem",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="write_file",
            description="Write content to a file on the filesystem",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["path", "content"]
            }
        ),
        Tool(
            name="list_directory",
            description="List files and directories in a given path",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory to list"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="search_files",
            description="Search for files matching a pattern in a directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to search in"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "File pattern to search for (e.g., '*.py')"
                    }
                },
                "required": ["directory", "pattern"]
            }
        ),
        Tool(
            name="get_file_info",
            description="Get metadata information about a file (size, modified time, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file"
                    }
                },
                "required": ["path"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    
    if name == "read_file":
        path = arguments.get("path", "")
        return [TextContent(
            type="text",
            text=f"Mock response: Reading file from {path}"
        )]
    
    elif name == "write_file":
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        return [TextContent(
            type="text",
            text=f"Mock response: Wrote {len(content)} bytes to {path}"
        )]
    
    elif name == "list_directory":
        path = arguments.get("path", "")
        return [TextContent(
            type="text",
            text=f"Mock response: Listed directory {path}"
        )]
    
    elif name == "search_files":
        directory = arguments.get("directory", "")
        pattern = arguments.get("pattern", "")
        return [TextContent(
            type="text",
            text=f"Mock response: Searched for {pattern} in {directory}"
        )]
    
    elif name == "get_file_info":
        path = arguments.get("path", "")
        return [TextContent(
            type="text",
            text=f"Mock response: Got info for {path}"
        )]
    
    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]


async def main():
    """Run the server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
