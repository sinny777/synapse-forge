"""
SynapseForge — tool_router package

Public API for the standalone NeuralToolRouter engine.

Sub-packages:
  common/     — shared events, models, MCP manager, LLM adapters
  executors/  — BaseAgentExecutor + Mock, LangGraph, BeeAI implementations
  utils/      — archive utilities, mock MCP server (for testing)
"""

from tool_router.config import config
from tool_router.mcp_client import MCPClient, ToolSchema
from tool_router.agent_service import agent_orchestrator
from tool_router.status_tracker import update_status

__all__ = [
    "config",
    "MCPClient",
    "ToolSchema",
    "agent_orchestrator",
    "update_status",
]
