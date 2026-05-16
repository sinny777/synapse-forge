"""
SynapseForge — Default Workspace Seeder

Populates the database with the read-only "System Default Workspace" containing:
  • Example MCP Servers (Mediclaim, UHNW Banking mock servers)
  • Common MCP Servers (File System, SQLite, Web Fetch, Firecrawl, Brave, Perplexity)
  • Pre-built Agent definitions derived from the example applications
    – Mediclaim Agents (Policy, Billing, Claim Processing)  — from BeeAI example
    – UHNW Banking Agents (Portfolio, Market, Tax, Concierge) — from LangGraph example

All agents are stored with LangGraph-compatible metadata and system prompts
taken directly from the example orchestrators.

Usage:
    # From the backend/ directory with venv activated:
    python -m setup.seed_default_workspace          # create / sync
    python -m setup.seed_default_workspace --reset   # wipe & re-seed
"""

import argparse
import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure the backend package root is on sys.path and .env is loaded
# ---------------------------------------------------------------------------
_backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_backend_dir / ".env")

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db.models import (
    Base,
    Workspace,
    WorkspaceStatus,
    Tool,
    ToolType,
    MCPTransportType,
    MCPServerStatus,
    Agent,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_default_workspace")

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_WORKSPACE_NAME = "System Default Workspace"
DEFAULT_WORKSPACE_DESCRIPTION = (
    "Read-only template workspace pre-loaded with standard Agents and Tool "
    "templates. Clone resources from here into your own workspaces."
)

# ---------------------------------------------------------------------------
# MCP Server / Tool Templates
#
# Sources:
#   • Example apps:  examples/beeai_mediclaim_processing/mock_fastmcp_server.py
#                    examples/langgraph_UHNW_banking/mock_fastmcp_server.py
#   • Common servers: seed_master_data.py (master data script)
# ---------------------------------------------------------------------------

TOOL_TEMPLATES: list[dict] = [
    # ══════════════════════════════════════════════════════════════════════
    # Example App MCP Servers (with relative paths to mock servers)
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "Mediclaim MCP Server",
        "description": (
            "Medical claims processing and policy retrieval server. "
            "Provides 6 tools: get_policy_details, check_coverage_limits, "
            "fetch_discharge_summary, verify_hospital_bills, "
            "calculate_claimable_amount, submit_mediclaim."
        ),
        "type": ToolType.MCP_SERVER,
        "transport": MCPTransportType.STDIO,
        "command": "python",
        "args": ["../examples/beeai_mediclaim_processing/mock_fastmcp_server.py"],
        "is_enabled": False,
        "status": MCPServerStatus.DISABLED,
    },
    {
        "name": "UHNW Banking MCP Server",
        "description": (
            "Ultra High Net Worth banking operations and wealth management server. "
            "Provides 10 tools across Portfolio, Market, Tax & Compliance, and "
            "Core Banking categories: get_portfolio_summary, "
            "get_unrealized_gains_losses, get_live_market_data, get_market_news, "
            "execute_trade, simulate_capital_gains_tax, "
            "get_tax_loss_harvesting_options, run_aml_transaction_check, "
            "update_card_limit, initiate_wire_transfer."
        ),
        "type": ToolType.MCP_SERVER,
        "transport": MCPTransportType.STDIO,
        "command": "python",
        "args": ["../examples/langgraph_UHNW_banking/mock_fastmcp_server.py"],
        "is_enabled": False,
        "status": MCPServerStatus.DISABLED,
    },

    # ══════════════════════════════════════════════════════════════════════
    # Common / Utility MCP Servers
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "Local File System",
        "description": (
            "Provides secure, sandboxed access to the local file system. "
            "Useful for coding agents that need to read, write, and manage "
            "project files."
        ),
        "type": ToolType.MCP_SERVER,
        "transport": MCPTransportType.STDIO,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/workspace"],
        "is_enabled": False,
        "status": MCPServerStatus.DISABLED,
    },
    {
        "name": "SQLite Database",
        "description": (
            "Allows interacting with SQLite databases for lightweight "
            "data storage, querying, and schema management."
        ),
        "type": ToolType.MCP_SERVER,
        "transport": MCPTransportType.STDIO,
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db", "/tmp/mcp-test.db"],
        "is_enabled": False,
        "status": MCPServerStatus.DISABLED,
    },
    {
        "name": "Web Fetch Server",
        "description": (
            "Fetches content from the internet safely. Enables agents to "
            "retrieve real-time information from web pages and APIs."
        ),
        "type": ToolType.MCP_SERVER,
        "transport": MCPTransportType.STDIO,
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "is_enabled": False,
        "status": MCPServerStatus.DISABLED,
    },
    {
        "name": "Firecrawl MCP",
        "description": (
            "Web scraping and crawling using Firecrawl. Extracts structured "
            "content from websites with JavaScript rendering support."
        ),
        "type": ToolType.MCP_SERVER,
        "transport": MCPTransportType.STDIO,
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env": {"FIRECRAWL_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "is_enabled": False,
        "status": MCPServerStatus.DISABLED,
    },
    {
        "name": "Brave Search MCP",
        "description": (
            "Search the web using Brave Search API. Provides privacy-focused "
            "web search results for research and information retrieval agents."
        ),
        "type": ToolType.MCP_SERVER,
        "transport": MCPTransportType.STDIO,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "is_enabled": False,
        "status": MCPServerStatus.DISABLED,
    },
    {
        "name": "Perplexity MCP",
        "description": (
            "Search and research using Perplexity AI. Provides AI-powered "
            "search with source citations for deep research tasks."
        ),
        "type": ToolType.MCP_SERVER,
        "transport": MCPTransportType.STDIO,
        "command": "npx",
        "args": ["-y", "@perplexity-ai/mcp-server"],
        "env": {"PERPLEXITY_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "is_enabled": False,
        "status": MCPServerStatus.DISABLED,
    },

    # ══════════════════════════════════════════════════════════════════════
    # REST API Template (generic skeleton)
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "REST API Template",
        "description": (
            "A generic REST API tool template. Configure the connection_config "
            "with your endpoint URL, HTTP method, headers, and authentication."
        ),
        "type": ToolType.REST,
        "is_enabled": False,
        "connection_config": {
            "url": "https://api.example.com/v1/resource",
            "method": "GET",
            "headers": {"Authorization": "Bearer <YOUR_TOKEN>"},
        },
        "schema_def": {
            "type": "function",
            "function": {
                "name": "rest_api_call",
                "description": "Execute a REST API request against a configured endpoint.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The query or resource path to append",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Pre-seeded MCP Tool Definitions (child tools of the example MCP servers)
#
# These records mirror what would be discovered via MCPService.discover_tools()
# when connecting to the mock MCP servers. By pre-seeding them, the modal
# shows available tools without requiring a live connection.
# ---------------------------------------------------------------------------

MCP_TOOL_CHILDREN: list[dict] = [
    # ── Mediclaim MCP Server Tools (6) ─────────────────────────────────────
    {
        "parent_server": "Mediclaim MCP Server",
        "name": "get_policy_details",
        "description": "Retrieve insurance policy details for a given policy number.",
    },
    {
        "parent_server": "Mediclaim MCP Server",
        "name": "check_coverage_limits",
        "description": "Check if a specific treatment type is covered and retrieve coverage limits.",
    },
    {
        "parent_server": "Mediclaim MCP Server",
        "name": "fetch_discharge_summary",
        "description": "Fetch the hospital discharge summary for a patient.",
    },
    {
        "parent_server": "Mediclaim MCP Server",
        "name": "verify_hospital_bills",
        "description": "Verify and retrieve itemized hospital bills for a patient.",
    },
    {
        "parent_server": "Mediclaim MCP Server",
        "name": "calculate_claimable_amount",
        "description": "Calculate the final claimable amount after applying coverage limits and co-pay.",
    },
    {
        "parent_server": "Mediclaim MCP Server",
        "name": "submit_mediclaim",
        "description": "Submit the final mediclaim for processing.",
    },

    # ── UHNW Banking MCP Server Tools (10) ─────────────────────────────────
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "get_portfolio_summary",
        "description": "Retrieve portfolio summary including holdings, asset allocation, and YTD performance.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "get_unrealized_gains_losses",
        "description": "Retrieve open positions and their profit/loss status.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "get_live_market_data",
        "description": "Fetch real-time price, P/E ratio, and recent analyst ratings.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "get_market_news",
        "description": "Fetch breaking news sentiment for a sector or ticker.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "execute_trade",
        "description": "Place a buy or sell order for a stock.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "simulate_capital_gains_tax",
        "description": "Calculate the estimated tax bill for a proposed sale.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "get_tax_loss_harvesting_options",
        "description": "Recommend losing positions to sell to offset gains.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "run_aml_transaction_check",
        "description": "Run an Anti-Money Laundering check for large outbound wires.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "update_card_limit",
        "description": "Temporarily raises credit/spending limits.",
    },
    {
        "parent_server": "UHNW Banking MCP Server",
        "name": "initiate_wire_transfer",
        "description": "Wires money to external accounts.",
    },
]

# ---------------------------------------------------------------------------
# Agent Definitions
#
# Derived from the actual example orchestrators:
#   • examples/beeai_mediclaim_processing/multi_agent_orchestrator.py
#     (IBM BeeAI framework — 3 agents: Policy, Billing, Claim Processing)
#   • examples/langgraph_UHNW_banking/multi_agent_orchestrator.py
#     (LangGraph framework — 4+1 agents: Portfolio, Market, Tax, Concierge + Supervisor)
#
# All agents are stored with LangGraph-compatible prompts and metadata
# so the platform can instantiate them in any workspace.
# ---------------------------------------------------------------------------

AGENT_DEFINITIONS: list[dict] = [
    # ══════════════════════════════════════════════════════════════════════
    # Mediclaim Processing Agents (from BeeAI example)
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "Policy Agent",
        "system_prompt": (
            "You are the Policy Agent specialised in insurance policy verification. "
            "Your role is to fetch insurance policy details and check coverage limits "
            "for specific treatments. Use the get_policy_details tool to retrieve "
            "policy information and the check_coverage_limits tool to verify whether "
            "a treatment type is covered and what the coverage limits are. "
            "Always present findings clearly with policy numbers, coverage status, "
            "limits, and co-pay percentages."
        ),
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "_attach_tool": "Mediclaim MCP Server",
        "_metadata": {
            "framework_origin": "beeai",
            "example_app": "beeai_mediclaim_processing",
            "role": "Policy verification and coverage checking",
            "category": "Insurance / Mediclaim",
        },
    },
    {
        "name": "Billing Agent",
        "system_prompt": (
            "You are the Billing Agent responsible for verifying hospital bills "
            "and discharge summaries. Use the fetch_discharge_summary tool to "
            "retrieve patient hospitalisation details including diagnosis, "
            "admission and discharge dates. Use the verify_hospital_bills tool "
            "to get itemized bill breakdowns including surgery costs, room charges, "
            "medicines, and diagnostics. Present all financial details clearly "
            "with line-item totals."
        ),
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "_attach_tool": "Mediclaim MCP Server",
        "_metadata": {
            "framework_origin": "beeai",
            "example_app": "beeai_mediclaim_processing",
            "role": "Hospital bill verification and discharge summary",
            "category": "Insurance / Mediclaim",
        },
    },
    {
        "name": "Claim Processing Agent",
        "system_prompt": (
            "You are the Claim Processing Agent responsible for calculating "
            "final claimable amounts and submitting mediclaims. You receive "
            "context from the Policy Agent (coverage details) and the Billing "
            "Agent (verified bills). Use the calculate_claimable_amount tool "
            "to compute the final amount after applying coverage limits and "
            "co-pay deductions. Then use the submit_mediclaim tool to submit "
            "the claim for processing. Always present the full calculation "
            "breakdown and confirmation details."
        ),
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "_attach_tool": "Mediclaim MCP Server",
        "_metadata": {
            "framework_origin": "beeai",
            "example_app": "beeai_mediclaim_processing",
            "role": "Claim calculation and submission",
            "category": "Insurance / Mediclaim",
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # UHNW Banking Agents (from LangGraph example)
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "Portfolio Manager Agent",
        "system_prompt": (
            "You are the Portfolio Manager Agent for Ultra High Net Worth "
            "private banking. You analyze the client's holdings and performance. "
            "Use the get_portfolio_summary tool to retrieve portfolio details "
            "including total AUM, YTD performance, and individual holdings. "
            "Use the get_unrealized_gains_losses tool to assess open positions "
            "and their profit/loss status. You must output results directly "
            "to the user with clear formatting of financial figures. "
            "When using tools, invoke them then provide the final answer."
        ),
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "_attach_tool": "UHNW Banking MCP Server",
        "_metadata": {
            "framework_origin": "langgraph",
            "example_app": "langgraph_UHNW_banking",
            "role": "Portfolio analysis, holdings, and performance",
            "category": "Private Banking / Wealth Management",
            "langgraph_node": "PortfolioManager",
        },
    },
    {
        "name": "Trading & Market Analyst Agent",
        "system_prompt": (
            "You are the Trading & Market Analyst Agent. You fetch market data, "
            "news sentiment, and execute trades on behalf of UHNW clients. "
            "Use the get_live_market_data tool for real-time price, P/E ratios, "
            "and analyst ratings. Use the get_market_news tool for breaking "
            "news sentiment on sectors or tickers. Use the execute_trade tool "
            "to place buy or sell orders. Always confirm trade details with "
            "the client before execution and present market data clearly."
        ),
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "_attach_tool": "UHNW Banking MCP Server",
        "_metadata": {
            "framework_origin": "langgraph",
            "example_app": "langgraph_UHNW_banking",
            "role": "Market data, news, and trade execution",
            "category": "Private Banking / Wealth Management",
            "langgraph_node": "TradingAnalyst",
        },
    },
    {
        "name": "Tax & Compliance Officer Agent",
        "system_prompt": (
            "You are the Tax & Compliance Officer Agent. You handle capital "
            "gains simulations, tax loss harvesting recommendations, and "
            "Anti-Money Laundering (AML) compliance checks. Use the "
            "simulate_capital_gains_tax tool to estimate tax implications "
            "of proposed sales. Use the get_tax_loss_harvesting_options tool "
            "to identify losing positions that can offset gains. Use the "
            "run_aml_transaction_check tool for large outbound wire "
            "compliance screening. Present all tax figures and compliance "
            "results with clear breakdowns."
        ),
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "_attach_tool": "UHNW Banking MCP Server",
        "_metadata": {
            "framework_origin": "langgraph",
            "example_app": "langgraph_UHNW_banking",
            "role": "Tax simulation, harvesting, and AML compliance",
            "category": "Private Banking / Wealth Management",
            "langgraph_node": "TaxCompliance",
        },
    },
    {
        "name": "Premium Concierge Agent",
        "system_prompt": (
            "You are the Premium Concierge Agent for UHNW private banking "
            "clients. You handle lifestyle banking requests including credit "
            "card limit adjustments and wire transfers. Use the "
            "update_card_limit tool to temporarily raise spending limits. "
            "Use the initiate_wire_transfer tool to send money to external "
            "accounts. Always confirm sensitive operations and provide "
            "clear confirmation details including amounts, recipients, "
            "and reference numbers."
        ),
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "_attach_tool": "UHNW Banking MCP Server",
        "_metadata": {
            "framework_origin": "langgraph",
            "example_app": "langgraph_UHNW_banking",
            "role": "Card limits, wire transfers, and lifestyle banking",
            "category": "Private Banking / Wealth Management",
            "langgraph_node": "Concierge",
        },
    },
    {
        "name": "Banking Supervisor Agent",
        "system_prompt": (
            "You are the Supervisor for a UHNW Private Banking Concierge. "
            "Given the conversation, decide who should act next.\n"
            "Options:\n"
            "- PortfolioManager: For portfolio queries, holdings, performance.\n"
            "- TradingAnalyst: For executing trades, fetching market data or news.\n"
            "- TaxCompliance: For tax simulations, harvesting, or AML compliance "
            "checks on large wires.\n"
            "- Concierge: For credit card limits, wire transfers, lifestyle.\n"
            "- FINISH: When the user's request has been fully resolved by the "
            "agents and a final response is ready.\n\n"
            "IMPORTANT: If the user's core question has been fully answered by "
            "previous agents in the conversation history, you MUST output FINISH. "
            "Do not route to other agents unnecessarily."
        ),
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "_attach_tool": None,
        "_metadata": {
            "framework_origin": "langgraph",
            "example_app": "langgraph_UHNW_banking",
            "role": "Supervisor / Router — delegates to specialist agents",
            "category": "Private Banking / Wealth Management",
            "langgraph_node": "supervisor",
            "is_supervisor": True,
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# Database helpers
# ═══════════════════════════════════════════════════════════════════════════

def _build_database_url() -> str:
    user = os.getenv("POSTGRES_USER", "ntr_user")
    password = os.getenv("POSTGRES_PASSWORD", "ntr_secret_2026")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "synapse_forge")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


async def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL") or _build_database_url()
    engine = create_async_engine(url, echo=False)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# ═══════════════════════════════════════════════════════════════════════════
# Seed logic
# ═══════════════════════════════════════════════════════════════════════════

async def _ensure_default_workspace(session: AsyncSession) -> Workspace:
    """Return the default workspace, creating it if it doesn't exist."""
    result = await session.execute(
        select(Workspace).where(Workspace.is_default == True)  # noqa: E712
    )
    ws = result.scalar_one_or_none()

    if ws is not None:
        logger.info("Default workspace already exists: %s (%s)", ws.name, ws.id)
        return ws

    ws = Workspace(
        name=DEFAULT_WORKSPACE_NAME,
        description=DEFAULT_WORKSPACE_DESCRIPTION,
        is_default=True,
        status=WorkspaceStatus.STOPPED,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        embedding_dim=384,
        created_by="system",
        updated_by="system",
    )
    session.add(ws)
    await session.flush()
    logger.info("✅ Created default workspace: %s (%s)", ws.name, ws.id)
    return ws


async def _seed_tools(session: AsyncSession, workspace_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Seed tool templates into the workspace. Returns name → id mapping."""
    # Check existing tools
    result = await session.execute(
        select(Tool).where(Tool.workspace_id == workspace_id)
    )
    existing = {t.name: t for t in result.scalars().all()}
    tool_map: dict[str, uuid.UUID] = {}

    for tpl in TOOL_TEMPLATES:
        if tpl["name"] in existing:
            logger.info("  Tool '%s' already exists, skipping.", tpl["name"])
            tool_map[tpl["name"]] = existing[tpl["name"]].id
            continue

        tool = Tool(
            workspace_id=workspace_id,
            name=tpl["name"],
            description=tpl.get("description"),
            type=tpl["type"],
            is_enabled=tpl.get("is_enabled", False),
            connection_config=tpl.get("connection_config"),
            schema_def=tpl.get("schema_def"),
            transport=tpl.get("transport"),
            command=tpl.get("command"),
            args=tpl.get("args"),
            env=tpl.get("env"),
            status=tpl.get("status", MCPServerStatus.ACTIVE),
            created_by="system",
            updated_by="system",
        )
        session.add(tool)
        await session.flush()
        tool_map[tool.name] = tool.id
        logger.info("  ✅ Created tool: %s (%s)", tool.name, tool.id)

    return tool_map


async def _seed_child_tools(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    tool_map: dict[str, uuid.UUID],
    ws: "Workspace",
) -> None:
    """Seed pre-defined MCP_TOOL children linked to their parent MCP servers."""
    # Check existing child tools
    result = await session.execute(
        select(Tool).where(
            Tool.workspace_id == workspace_id,
            Tool.type == ToolType.MCP_TOOL,
        )
    )
    existing_names = {t.name for t in result.scalars().all()}

    created_count = 0
    for defn in MCP_TOOL_CHILDREN:
        if defn["name"] in existing_names:
            continue

        parent_name = defn["parent_server"]
        parent_id = tool_map.get(parent_name)
        if not parent_id:
            logger.warning(
                "  ⚠ Parent server '%s' not found for child tool '%s', skipping.",
                parent_name, defn["name"],
            )
            continue

        # Generate embedding for semantic search
        vec = None
        try:
            from services.embedding_service import embedding_service
            vec = embedding_service.embed_tool(
                name=defn["name"],
                description=defn.get("description"),
                schema_def=None,
                model_name=ws.embedding_model,
            )
        except Exception as e:
            logger.warning("  Embedding failed for '%s': %s", defn["name"], e)

        child = Tool(
            workspace_id=workspace_id,
            name=defn["name"],
            description=defn.get("description"),
            type=ToolType.MCP_TOOL,
            is_enabled=False,
            parent_id=str(parent_id),
            status=MCPServerStatus.DISABLED,
            embedding=vec,
            created_by="system",
            updated_by="system",
        )
        session.add(child)
        created_count += 1

    if created_count > 0:
        await session.flush()
        logger.info("  ✅ Created %d MCP child tools", created_count)


async def _seed_agents(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    tool_map: dict[str, uuid.UUID],
) -> None:
    """Seed agent definitions, linking them to tools via tool_map."""
    result = await session.execute(
        select(Agent).where(Agent.workspace_id == workspace_id)
    )
    existing_names = {a.name for a in result.scalars().all()}

    for defn in AGENT_DEFINITIONS:
        if defn["name"] in existing_names:
            logger.info("  Agent '%s' already exists, skipping.", defn["name"])
            continue

        # Resolve attached tool IDs
        attached: list[uuid.UUID] = []
        attach_name = defn.get("_attach_tool")
        if attach_name and attach_name in tool_map:
            attached.append(tool_map[attach_name])

        agent = Agent(
            workspace_id=workspace_id,
            name=defn["name"],
            system_prompt=defn.get("system_prompt"),
            llm_provider=defn.get("llm_provider"),
            llm_model=defn.get("llm_model"),
            attached_tool_ids=attached if attached else None,
            created_by="system",
            updated_by="system",
        )
        session.add(agent)
        await session.flush()
        logger.info("  ✅ Created agent: %s (%s)", agent.name, agent.id)


async def _reset_default_workspace(session: AsyncSession) -> None:
    """Delete the entire default workspace and all cascaded children."""
    result = await session.execute(
        select(Workspace).where(Workspace.is_default == True)  # noqa: E712
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        logger.info("No default workspace found to reset.")
        return

    logger.warning("Deleting default workspace '%s' and all children...", ws.name)
    await session.delete(ws)
    await session.flush()
    logger.info("✅ Default workspace deleted.")


# ═══════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════

async def seed(reset: bool = False) -> None:
    """Run the full seeding process."""
    factory = await _get_session_factory()

    async with factory() as session:
        try:
            if reset:
                await _reset_default_workspace(session)
                await session.commit()

            # 1. Ensure workspace
            ws = await _ensure_default_workspace(session)

            # 2. Seed MCP server / tool templates
            logger.info("Seeding MCP server and tool templates...")
            tool_map = await _seed_tools(session, ws.id)

            # 2.5. Seed MCP child tools (pre-discovered tool definitions)
            logger.info("Seeding MCP child tools...")
            await _seed_child_tools(session, ws.id, tool_map, ws)

            # 3. Seed agents
            logger.info("Seeding agent definitions...")
            await _seed_agents(session, ws.id, tool_map)

            await session.commit()
            logger.info("🎉 Default workspace seeding complete!")

        except Exception:
            await session.rollback()
            logger.exception("Seeding failed — rolled back.")
            raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the System Default Workspace with template Agents and Tools."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and re-create the default workspace from scratch.",
    )
    args = parser.parse_args()

    asyncio.run(seed(reset=args.reset))


if __name__ == "__main__":
    main()
