"""
SynapseForge — Master Data Seeder (Python-native)

Seeds the canonical master data for the Default workspace (ws-001)
and the Demo workspace (ws-002), including:
  - workspaces
  - llm_configs
  - tools (MCP servers, MCP tools, REST tools)
  - agents (with category, sub_category, and tags)

Changes vs. original backup:
  - Removed "Mediclaim Supervisor Agent" from both workspaces
  - Added category / sub_category / tags to all agents and tools

Usage:
    python -m setup.seed_master_data
    python -m setup.seed_master_data --reset
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv

load_dotenv(dotenv_path=_backend_dir / ".env")

from db.engine import get_database, init_db, prepare_document, reset_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_master_data")

TS_SYSTEM = datetime(2026, 5, 26, 11, 39, 36, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

WORKSPACES: list[dict[str, Any]] = [
    {
        "_id": "00000000-0000-0000-0000-000000000001",
        "name": "Default Workspace",
        "description": "Master workspace containing the canonical tool and agent library.",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_dim": 384,
        "is_default": True,
        "status": "STOPPED",
        "shared_with": None,
        "created_at": TS_SYSTEM,
        "updated_at": TS_SYSTEM,
        "created_by": "system",
        "updated_by": "system",
    },
    {
        "_id": "00000000-0000-0000-0000-000000000002",
        "name": "Demo Workspace",
        "description": "Demo workspace with pre-configured examples for healthcare and BFSI use cases.",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_dim": 384,
        "is_default": False,
        "status": "STOPPED",
        "shared_with": None,
        "created_at": TS_SYSTEM,
        "updated_at": TS_SYSTEM,
        "created_by": "system",
        "updated_by": "system",
    },
]

# ---------------------------------------------------------------------------
# LLM Configs
# ---------------------------------------------------------------------------

LLM_CONFIGS: list[dict[str, Any]] = [
    {
        "_id": "c70234a9-6e48-4afb-8308-ea07dd20a997",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Teacher Config",
        "provider": "ollama",
        "model_name": "granite4.1:8b",
        "credentials": {"api_base": "http://localhost:11434"},
        "temperature": 0.8,
        "max_tokens": 2048,
        "created_at": TS_SYSTEM,
        "updated_at": TS_SYSTEM,
        "created_by": "system",
        "updated_by": "system",
    },
    {
        "_id": "bb435049-cf5a-4331-90f4-1a8b0cd1a28d",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Expansion Config",
        "provider": "ollama",
        "model_name": "granite4.1:8b",
        "credentials": {"api_base": "http://localhost:11434"},
        "temperature": 0.3,
        "max_tokens": 1024,
        "created_at": TS_SYSTEM,
        "updated_at": TS_SYSTEM,
        "created_by": "system",
        "updated_by": "system",
    },
    {
        "_id": "e1a44a2d-a20c-4150-bdec-2318ff3a9d95",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Heavy Config",
        "provider": "ollama",
        "model_name": "granite4.1:8b",
        "credentials": {"api_base": "http://localhost:11434"},
        "temperature": 0.0,
        "max_tokens": 4096,
        "created_at": TS_SYSTEM,
        "updated_at": TS_SYSTEM,
        "created_by": "system",
        "updated_by": "system",
    },
    {
        "_id": "ff21c29c-6802-4fdd-a9c6-478dc04c5af2",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "LocalModelConfig",
        "provider": "ollama",
        "model_name": "granite4.1:8b",
        "credentials": {"api_base": "http://localhost:11434"},
        "temperature": 0.8,
        "max_tokens": 2048,
        "created_at": TS_SYSTEM,
        "updated_at": TS_SYSTEM,
        "created_by": "system",
        "updated_by": "system",
    },
    {
        "_id": "5443fad5-787a-479f-b112-fe3189d5b865",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "WatsonxConfig",
        "provider": "ibm_watsonx",
        "model_name": "meta-llama/llama-4-maverick-17b-128e-instruct-fp8",
        "credentials": {"region": "us-south", "api_key": "***", "project_id": "6cf256b5-2e37-47d5-b925-22588c646264"},
        "temperature": 0.3,
        "max_tokens": 1024,
        "created_at": TS_SYSTEM,
        "updated_at": TS_SYSTEM,
        "created_by": "system",
        "updated_by": "system",
    },
]

# ---------------------------------------------------------------------------
# Tools — workspace 001 (Default)
# ---------------------------------------------------------------------------

_TOOLS_WS1: list[dict[str, Any]] = [
    {
        "_id": "c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3",
        "name": "Mediclaim MCP Server",
        "description": "Medical claims processing and policy retrieval server. Provides 6 tools: get_policy_details, check_coverage_limits, fetch_discharge_summary, verify_hospital_bills, calculate_claimable_amount, submit_mediclaim.",
        "type": "MCP_SERVER",
        "is_enabled": True,
        "transport": "stdio",
        "command": "python",
        "args": ["../examples/beeai_mediclaim_processing/mock_fastmcp_server.py"],
        "env": None,
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Healthcare",
        "sub_category": "Mediclaim & Insurance",
        "tags": ["mediclaim", "insurance", "healthcare", "mcp-server"],
    },
    {
        "_id": "da8f443b-387f-488c-9626-b1f7d1c0b101",
        "name": "UHNW Banking MCP Server",
        "description": "Ultra High Net Worth banking operations and wealth management server. Provides 10 tools: get_portfolio_summary, get_unrealized_gains_losses, get_live_market_data, get_market_news, execute_trade, simulate_capital_gains_tax, get_tax_loss_harvesting_options, run_aml_transaction_check, update_card_limit, initiate_wire_transfer.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "python",
        "args": ["../examples/langgraph_UHNW_banking/mock_fastmcp_server.py"],
        "env": None,
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "BFSI",
        "sub_category": "Wealth Management",
        "tags": ["banking", "wealth-management", "uhnw", "bfsi", "mcp-server"],
    },
    {
        "_id": "4ed3a3f3-b93f-459d-b021-3cca7516f7a5",
        "name": "Local File System",
        "description": "Provides secure, sandboxed access to the local file system. Useful for coding agents that need to read, write, and manage project files.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/workspace"],
        "env": None,
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Utility",
        "tags": ["filesystem", "files", "utility", "common", "mcp-server"],
    },
    {
        "_id": "8ed43e02-d584-4d33-9c5b-a80fcf636bd0",
        "name": "SQLite Database",
        "description": "Allows interacting with SQLite databases for lightweight data storage, querying, and schema management.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db", "/tmp/mcp-test.db"],
        "env": None,
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Data Processing",
        "tags": ["database", "sqlite", "sql", "common", "mcp-server"],
    },
    {
        "_id": "10a4cfc0-d72b-4223-8c42-838bbfda8331",
        "name": "Web Fetch Server",
        "description": "Fetches content from the internet safely. Enables agents to retrieve real-time information from web pages and APIs.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "env": None,
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["web", "fetch", "http", "internet", "common", "mcp-server"],
    },
    {
        "_id": "f269dbbd-9018-4a9e-b89c-2f1d5d67be69",
        "name": "Firecrawl MCP",
        "description": "Web scraping and crawling using Firecrawl. Extracts structured content from websites with JavaScript rendering support.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env": {"FIRECRAWL_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["scraping", "crawling", "firecrawl", "web", "common", "mcp-server"],
    },
    {
        "_id": "88bd7fb9-cc7e-4a29-9c17-7c0ef5a83bec",
        "name": "Brave Search MCP",
        "description": "Search the web using Brave Search API. Provides privacy-focused web search results for research and information retrieval agents.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["search", "brave", "web-search", "common", "mcp-server"],
    },
    {
        "_id": "ea7237c7-6634-4f9a-bd04-0a272fb24d8b",
        "name": "Perplexity MCP",
        "description": "Search and research using Perplexity AI. Provides AI-powered search with source citations for deep research tasks.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@perplexity-ai/mcp-server"],
        "env": {"PERPLEXITY_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["search", "perplexity", "ai-search", "research", "common", "mcp-server"],
    },
    {
        "_id": "82120f91-61f7-478d-85d8-11fe1472a1e0",
        "name": "REST API Template",
        "description": "A generic REST API tool template. Configure the connection_config with your endpoint URL, HTTP method, headers, and authentication.",
        "type": "REST",
        "is_enabled": False,
        "connection_config": {"url": "https://api.example.com/v1/resource", "method": "GET", "headers": {"Authorization": "Bearer <YOUR_TOKEN>"}},
        "schema_def": {"type": "function", "function": {"name": "rest_api_call", "description": "Execute a REST API request against a configured endpoint.", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string", "description": "The query or resource path to append"}}}}},
        "status": "active",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Utility",
        "tags": ["rest", "api", "http", "template", "common"],
    },
    # MCP TOOL children of Mediclaim MCP Server (ws1)
    {"_id": "4ed12335-acc1-4fe4-864a-2684e3e8238e", "name": "get_policy_details", "description": "Retrieve insurance policy details for a given policy number.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["policy", "insurance", "healthcare"]},
    {"_id": "d51b540a-a820-4755-9b38-b09bca520b9e", "name": "check_coverage_limits", "description": "Check if a specific treatment type is covered and retrieve coverage limits.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["coverage", "insurance", "healthcare"]},
    {"_id": "1294e0f6-f572-416f-a13d-61758b15d397", "name": "fetch_discharge_summary", "description": "Fetch the hospital discharge summary for a patient.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["hospital", "discharge", "clinical", "healthcare"]},
    {"_id": "a53e9829-a9d5-4874-937d-8277f1e39725", "name": "verify_hospital_bills", "description": "Verify and retrieve itemized hospital bills for a patient.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["billing", "hospital", "finance", "healthcare"]},
    {"_id": "1fd05b6e-9486-4de6-984c-5a61015894b0", "name": "calculate_claimable_amount", "description": "Calculate the final claimable amount after applying coverage limits and co-pay.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["claim", "calculation", "insurance", "healthcare"]},
    {"_id": "1a4f937d-bdf1-4f87-8c0c-c0316241df59", "name": "submit_mediclaim", "description": "Submit the final mediclaim for processing.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["claim", "submission", "insurance", "healthcare"]},
    # MCP TOOL children of UHNW Banking MCP Server (ws1)
    {"_id": "b5cc08b8-2f2a-4149-9825-0710ffd0b75e", "name": "get_portfolio_summary", "description": "Retrieve portfolio summary including holdings, asset allocation, and YTD performance.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Wealth Management", "tags": ["portfolio", "wealth", "bfsi"]},
    {"_id": "a6653e5a-d9c8-4009-99c8-3a8142ad4835", "name": "get_unrealized_gains_losses", "description": "Retrieve open positions and their profit/loss status.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Wealth Management", "tags": ["portfolio", "pnl", "trading", "bfsi"]},
    {"_id": "8a6f1c04-3b58-4860-8149-c97cfa87e86b", "name": "get_live_market_data", "description": "Fetch real-time price, P/E ratio, and recent analyst ratings.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Trading & Markets", "tags": ["market-data", "trading", "equity", "bfsi"]},
    {"_id": "e62cf896-0492-467f-a3c9-b890d0f80feb", "name": "get_market_news", "description": "Fetch breaking news sentiment for a sector or ticker.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Trading & Markets", "tags": ["news", "sentiment", "trading", "bfsi"]},
    {"_id": "56cbf7b7-cf6a-4014-aa75-5c136ad4c23a", "name": "execute_trade", "description": "Place a buy or sell order for a stock.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Trading & Markets", "tags": ["trade", "order", "equity", "bfsi"]},
    {"_id": "a58b0bee-6c22-4e26-a8fe-c451b0eeccea", "name": "simulate_capital_gains_tax", "description": "Calculate the estimated tax bill for a proposed sale.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Tax & Compliance", "tags": ["tax", "capital-gains", "compliance", "bfsi"]},
    {"_id": "dcb38750-52a6-4326-9baf-e37d344672cf", "name": "get_tax_loss_harvesting_options", "description": "Recommend losing positions to sell to offset gains.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Tax & Compliance", "tags": ["tax", "harvesting", "wealth", "bfsi"]},
    {"_id": "86d1def1-f54a-4c2c-9bfe-4bccefa4b847", "name": "run_aml_transaction_check", "description": "Run an Anti-Money Laundering check for large outbound wires.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Risk Management", "tags": ["aml", "compliance", "wire-transfer", "bfsi"]},
    {"_id": "c18092d8-bd2a-4508-95cc-2d5c4ef709ad", "name": "update_card_limit", "description": "Temporarily raises credit/spending limits.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Banking Operations", "tags": ["card", "credit", "banking", "bfsi"]},
    {"_id": "46676097-0cf9-4251-bb0a-25a9c7f6e2b9", "name": "initiate_wire_transfer", "description": "Wires money to external accounts.", "type": "MCP_TOOL", "is_enabled": False, "parent_id": "da8f443b-387f-488c-9626-b1f7d1c0b101", "status": "disabled", "category": "BFSI", "sub_category": "Payments & Transfers", "tags": ["wire", "transfer", "payment", "bfsi"]},
]

# ---------------------------------------------------------------------------
# Tools — workspace 002 (Demo)
# ---------------------------------------------------------------------------

_TOOLS_WS2: list[dict[str, Any]] = [
    {
        "_id": "922b9c29-54f9-46d5-860a-b7ef699481d3",
        "name": "Mediclaim MCP Server",
        "description": "Medical claims processing and policy retrieval server. Provides 6 tools: get_policy_details, check_coverage_limits, fetch_discharge_summary, verify_hospital_bills, calculate_claimable_amount, submit_mediclaim.",
        "type": "MCP_SERVER",
        "is_enabled": True,
        "transport": "stdio",
        "command": "python",
        "args": ["../examples/beeai_mediclaim_processing/mock_fastmcp_server.py"],
        "env": None,
        "url": None,
        "status": "active",
        "last_error": None,
        "parent_id": None,
        "category": "Healthcare",
        "sub_category": "Mediclaim & Insurance",
        "tags": ["mediclaim", "insurance", "healthcare", "mcp-server"],
    },
    {
        "_id": "4ba8b6ad-04d1-46a3-ab4a-47744e5c077b",
        "name": "UHNW Banking MCP Server",
        "description": "Ultra High Net Worth banking operations and wealth management server. Provides 10 tools across Portfolio, Market, Tax & Compliance, and Core Banking categories.",
        "type": "MCP_SERVER",
        "is_enabled": True,
        "transport": "stdio",
        "command": "python",
        "args": ["../examples/langgraph_UHNW_banking/mock_fastmcp_server.py"],
        "env": None,
        "url": None,
        "status": "active",
        "last_error": None,
        "parent_id": None,
        "category": "BFSI",
        "sub_category": "Wealth Management",
        "tags": ["banking", "wealth-management", "uhnw", "bfsi", "mcp-server"],
    },
    {
        "_id": "a2d628e1-41e4-4bd0-9693-ee816c74323d",
        "name": "Local File System",
        "description": "Provides secure, sandboxed access to the local file system.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/workspace"],
        "env": None,
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Utility",
        "tags": ["filesystem", "files", "utility", "common", "mcp-server"],
    },
    {
        "_id": "47ef6262-6f5b-4a94-a7ce-940b97bd8b35",
        "name": "SQLite Database",
        "description": "Allows interacting with SQLite databases for lightweight data storage, querying, and schema management.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db", "/tmp/mcp-test.db"],
        "env": None,
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Data Processing",
        "tags": ["database", "sqlite", "sql", "common", "mcp-server"],
    },
    {
        "_id": "b51345f3-ff8c-43de-847b-90bbad62dfae",
        "name": "Web Fetch Server",
        "description": "Fetches content from the internet safely.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "env": None,
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["web", "fetch", "http", "internet", "common", "mcp-server"],
    },
    {
        "_id": "a337d605-c2a8-4168-ad38-d08eb7a7e95b",
        "name": "Firecrawl MCP",
        "description": "Web scraping and crawling using Firecrawl. Extracts structured content from websites with JavaScript rendering support.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env": {"FIRECRAWL_API_KEY": "***"},
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["scraping", "crawling", "firecrawl", "web", "common", "mcp-server"],
    },
    {
        "_id": "6829f554-def1-4c9d-bd04-783a343d847a",
        "name": "Brave Search MCP",
        "description": "Search the web using Brave Search API. Provides privacy-focused web search results.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": "***"},
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["search", "brave", "web-search", "common", "mcp-server"],
    },
    {
        "_id": "58029774-4230-4fab-94a0-41afd98e9bd9",
        "name": "Perplexity MCP",
        "description": "Search and research using Perplexity AI. Provides AI-powered search with source citations.",
        "type": "MCP_SERVER",
        "is_enabled": False,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@perplexity-ai/mcp-server"],
        "env": {"PERPLEXITY_API_KEY": "***"},
        "url": None,
        "status": "disabled",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["search", "perplexity", "ai-search", "research", "common", "mcp-server"],
    },
    {
        "_id": "a4cf593c-8e24-4cdc-a19e-7aecbe7abe50",
        "name": "REST API Template",
        "description": "A generic REST API tool template.",
        "type": "REST",
        "is_enabled": False,
        "connection_config": {"url": "https://api.example.com/v1/resource", "method": "GET", "headers": {"Authorization": "Bearer <YOUR_TOKEN>"}},
        "schema_def": {"type": "function", "function": {"name": "rest_api_call", "description": "Execute a REST API request.", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}}},
        "status": "active",
        "last_error": None,
        "parent_id": None,
        "category": "Common",
        "sub_category": "Utility",
        "tags": ["rest", "api", "http", "template", "common"],
    },
    # MCP TOOL children — Mediclaim MCP Server (ws2)
    {"_id": "9e1aa001-54f9-46d5-860a-b7ef699481d3", "name": "get_policy_details", "description": "Retrieve insurance policy details for a given policy number.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "922b9c29-54f9-46d5-860a-b7ef699481d3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["policy", "insurance", "healthcare"]},
    {"_id": "9e2aa002-54f9-46d5-860a-b7ef699481d3", "name": "check_coverage_limits", "description": "Check if a specific treatment type is covered and retrieve coverage limits.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "922b9c29-54f9-46d5-860a-b7ef699481d3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["coverage", "insurance", "healthcare"]},
    {"_id": "9e3aa003-54f9-46d5-860a-b7ef699481d3", "name": "fetch_discharge_summary", "description": "Fetch the hospital discharge summary for a patient.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "922b9c29-54f9-46d5-860a-b7ef699481d3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["hospital", "discharge", "clinical", "healthcare"]},
    {"_id": "9e4aa004-54f9-46d5-860a-b7ef699481d3", "name": "verify_hospital_bills", "description": "Verify and retrieve itemized hospital bills for a patient.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "922b9c29-54f9-46d5-860a-b7ef699481d3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["billing", "hospital", "finance", "healthcare"]},
    {"_id": "9e5aa005-54f9-46d5-860a-b7ef699481d3", "name": "calculate_claimable_amount", "description": "Calculate the final claimable amount after applying coverage limits and co-pay.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "922b9c29-54f9-46d5-860a-b7ef699481d3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["claim", "calculation", "insurance", "healthcare"]},
    {"_id": "d7420830-a6cb-4774-b0d8-9b8c7d5cb2ba", "name": "submit_mediclaim", "description": "Submit the final mediclaim for processing.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "922b9c29-54f9-46d5-860a-b7ef699481d3", "status": "disabled", "category": "Healthcare", "sub_category": "Mediclaim & Insurance", "tags": ["claim", "submission", "insurance", "healthcare"]},
    # MCP TOOL children — UHNW Banking MCP Server (ws2)
    {"_id": "2f06ff47-85c9-40fc-9098-e31bfd10f5ee", "name": "get_portfolio_summary", "description": "Retrieve portfolio summary including holdings, asset allocation, and YTD performance.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "4ba8b6ad-04d1-46a3-ab4a-47744e5c077b", "status": "disabled", "category": "BFSI", "sub_category": "Wealth Management", "tags": ["portfolio", "wealth", "bfsi"]},
    {"_id": "1e271a1e-0c65-41d4-82bc-e18ee09095d8", "name": "get_unrealized_gains_losses", "description": "Retrieve open positions and their profit/loss status.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "4ba8b6ad-04d1-46a3-ab4a-47744e5c077b", "status": "disabled", "category": "BFSI", "sub_category": "Wealth Management", "tags": ["portfolio", "pnl", "trading", "bfsi"]},
    {"_id": "ff91b224-c087-4f57-9600-deecda97e646", "name": "get_live_market_data", "description": "Fetch real-time price, P/E ratio, and recent analyst ratings.", "type": "MCP_TOOL", "is_enabled": True, "parent_id": "4ba8b6ad-04d1-46a3-ab4a-47744e5c077b", "status": "disabled", "category": "BFSI", "sub_category": "Trading & Markets", "tags": ["market-data", "trading", "equity", "bfsi"]},
]

# Merge workspace-specific tool lists, adding workspace_id and timestamps
def _build_tools(raw_list: list[dict], ws_id: str) -> list[dict]:
    result = []
    for t in raw_list:
        doc = {
            "_id": t["_id"],
            "workspace_id": ws_id,
            "name": t["name"],
            "description": t.get("description"),
            "type": t.get("type", "REST"),
            "is_enabled": t.get("is_enabled", False),
            "connection_config": t.get("connection_config"),
            "schema_def": t.get("schema_def"),
            "transport": t.get("transport"),
            "command": t.get("command"),
            "args": t.get("args"),
            "env": t.get("env"),
            "url": t.get("url"),
            "status": t.get("status", "disabled"),
            "last_error": t.get("last_error"),
            "parent_id": t.get("parent_id"),
            "embedding": None,
            "category": t.get("category"),
            "sub_category": t.get("sub_category"),
            "tags": t.get("tags"),
            "created_at": TS_SYSTEM,
            "updated_at": TS_SYSTEM,
            "created_by": "system",
            "updated_by": "system",
        }
        result.append(doc)
    return result


TOOLS = _build_tools(_TOOLS_WS1, "00000000-0000-0000-0000-000000000001") + \
        _build_tools(_TOOLS_WS2, "00000000-0000-0000-0000-000000000002")

# ---------------------------------------------------------------------------
# Agents (Mediclaim Supervisor Agent is intentionally excluded)
# ---------------------------------------------------------------------------

AGENTS: list[dict[str, Any]] = [
    # ── Workspace 001 ──────────────────────────────────────────────
    {
        "_id": "eb9b84cb-3512-46e3-aab5-89e73dd8c9e3",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Policy Agent",
        "description": "Policy Agent — insurance policy verification specialist. Validates member coverage, exclusions, co-pay terms, and treatment eligibility.",
        "system_prompt": "You are an insurance policy verification specialist. Use get_policy_details and check_coverage_limits tools to verify policy information.",
        "llm_config_id": "c70234a9-6e48-4afb-8308-ea07dd20a997",
        "use_neural_router": True,
        "router_top_k": 3,
        "memory_type": "buffer",
        "memory_window": 10,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3"],
        "collaborator_agent_ids": None,
        "category": "Healthcare",
        "sub_category": "Mediclaim & Insurance",
        "tags": ["policy", "insurance", "healthcare", "sub-agent"],
    },
    {
        "_id": "c2187bcf-7b28-478f-9aab-9b762c805218",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Billing Agent",
        "description": "Billing Agent — hospital billing analyst. Reviews discharge records and itemized bills to validate admissible medical expenses.",
        "system_prompt": "You are a hospital billing analyst. Use fetch_discharge_summary and verify_hospital_bills tools.",
        "llm_config_id": "bb435049-cf5a-4331-90f4-1a8b0cd1a28d",
        "use_neural_router": True,
        "router_top_k": 3,
        "memory_type": "buffer",
        "memory_window": 10,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3"],
        "collaborator_agent_ids": None,
        "category": "Healthcare",
        "sub_category": "Mediclaim & Insurance",
        "tags": ["billing", "hospital", "healthcare", "sub-agent"],
    },
    {
        "_id": "8e27c031-7752-4ef2-b7bb-909982356d61",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Claim Processing Agent",
        "description": "Claim Processing Agent — orchestrates end-to-end mediclaim processing. Delegates to Policy Agent and Billing Agent, computes the final claimable amount and submits the mediclaim.",
        "system_prompt": "You are the lead orchestrator for mediclaim processing. Coordinate between Policy Agent and Billing Agent before computing and submitting claims.",
        "llm_config_id": "e1a44a2d-a20c-4150-bdec-2318ff3a9d95",
        "use_neural_router": True,
        "router_top_k": 3,
        "memory_type": "summary",
        "memory_window": 12,
        "max_iterations": 15,
        "timeout_seconds": 240,
        "attached_tool_ids": ["c0e9f72b-2139-40bd-8aac-79a8f7f1fbf3"],
        "collaborator_agent_ids": ["eb9b84cb-3512-46e3-aab5-89e73dd8c9e3", "c2187bcf-7b28-478f-9aab-9b762c805218"],
        "category": "Healthcare",
        "sub_category": "Mediclaim & Insurance",
        "tags": ["mediclaim", "orchestrator", "healthcare"],
    },
    {
        "_id": "d8a67d8e-5d7e-4011-9da2-a514b5f4f92d",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Portfolio Manager Agent",
        "description": "Senior wealth portfolio analyst focused on holdings, exposure, performance, and unrealized gains or losses for UHNW client portfolios.",
        "system_prompt": "You are the Portfolio Manager Agent for Ultra High Net Worth private banking. Analyze client holdings and performance.",
        "llm_config_id": "c70234a9-6e48-4afb-8308-ea07dd20a997",
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "summary",
        "memory_window": 12,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["da8f443b-387f-488c-9626-b1f7d1c0b101"],
        "collaborator_agent_ids": None,
        "category": "BFSI",
        "sub_category": "Wealth Management",
        "tags": ["portfolio", "wealth", "bfsi", "sub-agent"],
    },
    {
        "_id": "fef11f1f-8885-430e-a6af-26f0fb411b76",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Trading & Market Analyst Agent",
        "description": "Capital markets specialist that combines live market data, sentiment, and trade execution support for wealth management decisions.",
        "system_prompt": "You are the Trading & Market Analyst Agent. Fetch market data, news sentiment, and execute trades on behalf of UHNW clients.",
        "llm_config_id": "bb435049-cf5a-4331-90f4-1a8b0cd1a28d",
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "buffer",
        "memory_window": 8,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["da8f443b-387f-488c-9626-b1f7d1c0b101"],
        "collaborator_agent_ids": None,
        "category": "BFSI",
        "sub_category": "Trading & Markets",
        "tags": ["trading", "market-data", "bfsi", "sub-agent"],
    },
    {
        "_id": "6f931f02-32d1-45f1-89b0-9546729fc9b8",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Tax & Compliance Officer Agent",
        "description": "Risk and compliance specialist for tax impact analysis, loss harvesting, and AML checks on sensitive private banking operations.",
        "system_prompt": "You are the Tax & Compliance Officer Agent. Handle capital gains simulations, tax loss harvesting, and AML compliance checks.",
        "llm_config_id": "e1a44a2d-a20c-4150-bdec-2318ff3a9d95",
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "summary",
        "memory_window": 10,
        "max_iterations": 10,
        "timeout_seconds": 240,
        "attached_tool_ids": ["da8f443b-387f-488c-9626-b1f7d1c0b101"],
        "collaborator_agent_ids": None,
        "category": "BFSI",
        "sub_category": "Tax & Compliance",
        "tags": ["tax", "compliance", "aml", "bfsi", "sub-agent"],
    },
    {
        "_id": "cb5e86ad-727c-4d90-a706-d94c9141c4b6",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Premium Concierge Agent",
        "description": "High-touch banking concierge for card limits, wire instructions, and sensitive service requests.",
        "system_prompt": "You are the Premium Concierge Agent for UHNW private banking clients. Handle credit card limit adjustments and wire transfers.",
        "llm_config_id": "bb435049-cf5a-4331-90f4-1a8b0cd1a28d",
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "buffer",
        "memory_window": 8,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["da8f443b-387f-488c-9626-b1f7d1c0b101"],
        "collaborator_agent_ids": None,
        "category": "BFSI",
        "sub_category": "Banking Operations",
        "tags": ["concierge", "banking", "payments", "bfsi", "sub-agent"],
    },
    {
        "_id": "40d5d91d-20d9-426f-af05-1e5bf9f81236",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "name": "Banking Supervisor Agent",
        "description": "Supervisor and routing agent that decides which specialist agent should act next and when the private banking request is fully resolved.",
        "system_prompt": "You are the Supervisor for a UHNW Private Banking Concierge. Route requests to PortfolioManager, TradingAnalyst, TaxCompliance, or Concierge.",
        "llm_config_id": "c70234a9-6e48-4afb-8308-ea07dd20a997",
        "use_neural_router": True,
        "router_top_k": 5,
        "memory_type": "summary",
        "memory_window": 14,
        "max_iterations": 12,
        "timeout_seconds": 240,
        "attached_tool_ids": None,
        "collaborator_agent_ids": ["d8a67d8e-5d7e-4011-9da2-a514b5f4f92d", "fef11f1f-8885-430e-a6af-26f0fb411b76", "6f931f02-32d1-45f1-89b0-9546729fc9b8", "cb5e86ad-727c-4d90-a706-d94c9141c4b6"],
        "category": "BFSI",
        "sub_category": "Banking Operations",
        "tags": ["supervisor", "routing", "banking", "bfsi", "orchestrator"],
    },
    # ── Workspace 002 ──────────────────────────────────────────────
    {
        "_id": "d82efc6e-ff32-4ac9-aac4-208ed46464a5",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Policy Agent",
        "description": "Policy Agent — insurance policy verification specialist. Validates member coverage, exclusions, co-pay terms, and treatment eligibility.",
        "system_prompt": "You are an insurance policy verification specialist. Use get_policy_details and check_coverage_limits tools.",
        "llm_config_id": "ff21c29c-6802-4fdd-a9c6-478dc04c5af2",
        "use_neural_router": True,
        "router_top_k": 3,
        "memory_type": "buffer",
        "memory_window": 10,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["922b9c29-54f9-46d5-860a-b7ef699481d3"],
        "collaborator_agent_ids": None,
        "category": "Healthcare",
        "sub_category": "Mediclaim & Insurance",
        "tags": ["policy", "insurance", "healthcare", "sub-agent"],
    },
    {
        "_id": "5b35861f-24b8-45fb-9a33-beb3f46ec262",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Billing Agent",
        "description": "Billing Agent — hospital billing analyst. Reviews discharge records and itemized bills.",
        "system_prompt": "You are a hospital billing analyst. Use fetch_discharge_summary and verify_hospital_bills tools.",
        "llm_config_id": "5443fad5-787a-479f-b112-fe3189d5b865",
        "use_neural_router": True,
        "router_top_k": 3,
        "memory_type": "buffer",
        "memory_window": 10,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["922b9c29-54f9-46d5-860a-b7ef699481d3"],
        "collaborator_agent_ids": None,
        "category": "Healthcare",
        "sub_category": "Mediclaim & Insurance",
        "tags": ["billing", "hospital", "healthcare", "sub-agent"],
    },
    {
        "_id": "15be7d3f-ab0a-47ac-9d2c-b25cbf93e27b",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Claim Processing Agent",
        "description": "Claim Processing Agent — orchestrates end-to-end mediclaim processing.",
        "system_prompt": "You are the lead orchestrator for mediclaim processing. Coordinate between Policy Agent and Billing Agent before submitting claims.",
        "llm_config_id": "ff21c29c-6802-4fdd-a9c6-478dc04c5af2",
        "use_neural_router": True,
        "router_top_k": 3,
        "memory_type": "summary",
        "memory_window": 12,
        "max_iterations": 15,
        "timeout_seconds": 240,
        "attached_tool_ids": ["922b9c29-54f9-46d5-860a-b7ef699481d3"],
        "collaborator_agent_ids": ["d82efc6e-ff32-4ac9-aac4-208ed46464a5", "5b35861f-24b8-45fb-9a33-beb3f46ec262"],
        "category": "Healthcare",
        "sub_category": "Mediclaim & Insurance",
        "tags": ["mediclaim", "orchestrator", "healthcare"],
    },
    {
        "_id": "5d4ac1bf-4930-4749-88a3-66951c8308f8",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Portfolio Manager Agent",
        "description": "Senior wealth portfolio analyst focused on holdings, exposure, performance, and unrealized gains or losses for UHNW client portfolios.",
        "system_prompt": "You are the Portfolio Manager Agent for Ultra High Net Worth private banking.",
        "llm_config_id": "ff21c29c-6802-4fdd-a9c6-478dc04c5af2",
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "summary",
        "memory_window": 12,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["4ba8b6ad-04d1-46a3-ab4a-47744e5c077b"],
        "collaborator_agent_ids": None,
        "category": "BFSI",
        "sub_category": "Wealth Management",
        "tags": ["portfolio", "wealth", "bfsi", "sub-agent"],
    },
    {
        "_id": "5fb95a57-8aae-44c9-a74c-e797603c730f",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Trading & Market Analyst Agent",
        "description": "Capital markets specialist for live market data, sentiment, and trade execution.",
        "system_prompt": "You are the Trading & Market Analyst Agent.",
        "llm_config_id": "5443fad5-787a-479f-b112-fe3189d5b865",
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "buffer",
        "memory_window": 8,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["4ba8b6ad-04d1-46a3-ab4a-47744e5c077b"],
        "collaborator_agent_ids": None,
        "category": "BFSI",
        "sub_category": "Trading & Markets",
        "tags": ["trading", "market-data", "bfsi", "sub-agent"],
    },
    {
        "_id": "a424ebbf-899f-448f-9c5e-f5e15338d05f",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Tax & Compliance Officer Agent",
        "description": "Risk and compliance specialist for tax impact analysis, loss harvesting, and AML checks.",
        "system_prompt": "You are the Tax & Compliance Officer Agent.",
        "llm_config_id": None,
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "summary",
        "memory_window": 10,
        "max_iterations": 10,
        "timeout_seconds": 240,
        "attached_tool_ids": ["4ba8b6ad-04d1-46a3-ab4a-47744e5c077b"],
        "collaborator_agent_ids": None,
        "category": "BFSI",
        "sub_category": "Tax & Compliance",
        "tags": ["tax", "compliance", "aml", "bfsi", "sub-agent"],
    },
    {
        "_id": "1e03a280-c75f-491c-a35a-17f76b84458d",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Premium Concierge Agent",
        "description": "High-touch banking concierge for card limits and wire instructions.",
        "system_prompt": "You are the Premium Concierge Agent for UHNW private banking clients.",
        "llm_config_id": "5443fad5-787a-479f-b112-fe3189d5b865",
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "buffer",
        "memory_window": 8,
        "max_iterations": 8,
        "timeout_seconds": 180,
        "attached_tool_ids": ["4ba8b6ad-04d1-46a3-ab4a-47744e5c077b"],
        "collaborator_agent_ids": None,
        "category": "BFSI",
        "sub_category": "Banking Operations",
        "tags": ["concierge", "banking", "payments", "bfsi", "sub-agent"],
    },
    {
        "_id": "593bca15-b3d8-4bf2-92ba-bec24a5d1f17",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Banking Supervisor Agent",
        "description": "Supervisor and routing agent for the UHNW Private Banking use case.",
        "system_prompt": "You are the Supervisor for a UHNW Private Banking Concierge. Route to PortfolioManager, TradingAnalyst, TaxCompliance, or Concierge.",
        "llm_config_id": "ff21c29c-6802-4fdd-a9c6-478dc04c5af2",
        "use_neural_router": True,
        "router_top_k": 5,
        "memory_type": "summary",
        "memory_window": 14,
        "max_iterations": 12,
        "timeout_seconds": 240,
        "attached_tool_ids": None,
        "collaborator_agent_ids": ["5d4ac1bf-4930-4749-88a3-66951c8308f8", "5fb95a57-8aae-44c9-a74c-e797603c730f", "a424ebbf-899f-448f-9c5e-f5e15338d05f", "1e03a280-c75f-491c-a35a-17f76b84458d"],
        "category": "BFSI",
        "sub_category": "Banking Operations",
        "tags": ["supervisor", "routing", "banking", "bfsi", "orchestrator"],
    },
    {
        "_id": "f1e2d3c4-0010-4000-8000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Research Agent (Free)",
        "description": "A fully free research agent using only public APIs that require no API keys. Uses Wikipedia, ArXiv, and Hacker News REST tools plus the Web Fetch Server MCP.",
        "system_prompt": "You are a research assistant with access to free, public data sources.",
        "llm_config_id": "ff21c29c-6802-4fdd-a9c6-478dc04c5af2",
        "use_neural_router": False,
        "router_top_k": None,
        "memory_type": "buffer",
        "memory_window": 10,
        "max_iterations": 8,
        "timeout_seconds": 120,
        "attached_tool_ids": ["b51345f3-ff8c-43de-847b-90bbad62dfae"],
        "collaborator_agent_ids": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["research", "wikipedia", "arxiv", "free", "common"],
    },
    {
        "_id": "a1b2c3d4-0001-4000-8000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "name": "Research Agent (Pro)",
        "description": "Pro research agent with access to premium web intelligence tools: Brave Search, Firecrawl, Web Fetch Server, and Perplexity. Requires API keys.",
        "system_prompt": "You are an expert research assistant with access to powerful paid web intelligence tools.",
        "llm_config_id": "ff21c29c-6802-4fdd-a9c6-478dc04c5af2",
        "use_neural_router": True,
        "router_top_k": 4,
        "memory_type": "buffer",
        "memory_window": 12,
        "max_iterations": 10,
        "timeout_seconds": 180,
        "attached_tool_ids": ["a337d605-c2a8-4168-ad38-d08eb7a7e95b", "6829f554-def1-4c9d-bd04-783a343d847a", "b51345f3-ff8c-43de-847b-90bbad62dfae", "58029774-4230-4fab-94a0-41afd98e9bd9"],
        "collaborator_agent_ids": None,
        "category": "Common",
        "sub_category": "Search & Retrieval",
        "tags": ["research", "firecrawl", "brave-search", "perplexity", "pro", "common"],
    },
]


def _build_agent_doc(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "_id": a["_id"],
        "workspace_id": a["workspace_id"],
        "name": a["name"],
        "description": a.get("description"),
        "system_prompt": a.get("system_prompt"),
        "llm_config_id": a.get("llm_config_id"),
        "use_neural_router": a.get("use_neural_router", False),
        "router_model_id": a.get("router_model_id"),
        "router_top_k": a.get("router_top_k"),
        "memory_type": a.get("memory_type"),
        "memory_window": a.get("memory_window"),
        "max_iterations": a.get("max_iterations"),
        "timeout_seconds": a.get("timeout_seconds"),
        "attached_tool_ids": a.get("attached_tool_ids"),
        "collaborator_agent_ids": a.get("collaborator_agent_ids"),
        "category": a.get("category"),
        "sub_category": a.get("sub_category"),
        "tags": a.get("tags"),
        "created_at": TS_SYSTEM,
        "updated_at": TS_SYSTEM,
        "created_by": a.get("created_by", "system"),
        "updated_by": a.get("updated_by", "system"),
    }


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------

async def _upsert(collection_name: str, doc_id: str, payload: dict[str, Any]) -> None:
    db = get_database()
    await db[collection_name].replace_one(
        {"_id": doc_id},
        payload,
        upsert=True,
    )


async def seed(reset: bool = False) -> None:
    await init_db()

    if reset:
        logger.warning("Reset requested — dropping all master collections before reseeding.")
        await reset_db()

    logger.info("Seeding workspaces …")
    for ws in WORKSPACES:
        doc = prepare_document({k: v for k, v in ws.items() if k != "_id"})
        doc["_id"] = ws["_id"]
        await _upsert("workspaces", ws["_id"], doc)

    logger.info("Seeding llm_configs …")
    for lc in LLM_CONFIGS:
        doc = prepare_document({k: v for k, v in lc.items() if k != "_id"})
        doc["_id"] = lc["_id"]
        await _upsert("llm_configs", lc["_id"], doc)

    logger.info("Seeding tools (%d total) …", len(TOOLS))
    parent_tools = [t for t in TOOLS if not t.get("parent_id")]
    child_tools = [t for t in TOOLS if t.get("parent_id")]

    for t in parent_tools:
        doc = prepare_document({k: v for k, v in t.items() if k != "_id"})
        doc["_id"] = t["_id"]
        await _upsert("tools", t["_id"], doc)

    for t in sorted(child_tools, key=lambda x: str(x.get("parent_id"))):
        doc = prepare_document({k: v for k, v in t.items() if k != "_id"})
        doc["_id"] = t["_id"]
        await _upsert("tools", t["_id"], doc)

    logger.info("Seeding agents (%d total, Mediclaim Supervisor excluded) …", len(AGENTS))
    for a in AGENTS:
        doc = _build_agent_doc(a)
        doc_prepared = prepare_document({k: v for k, v in doc.items() if k != "_id"})
        doc_prepared["_id"] = a["_id"]
        await _upsert("agents", a["_id"], doc_prepared)

    logger.info("✅ Master data seed complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SynapseForge master data.")
    parser.add_argument("--reset", action="store_true", help="Drop existing data before reseeding.")
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))


if __name__ == "__main__":
    main()

# Made with Bob
