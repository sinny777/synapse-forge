# SynapseForge — Quick Start Guide

Get the full-stack Agentic AI Platform running locally in under 10 minutes.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Backend API & NeuralToolRouter engine |
| Node.js | 18+ | Angular frontend & MCP server runtimes |
| PostgreSQL | 14+ | With the `pgvector` extension enabled |
| Redis | 7+ | Caching & LangGraph checkpointing |
| LLM API Key | — | At least one of: OpenAI, Anthropic, Google, Ollama (local) |

---

## 1. Clone & Setup

```bash
git clone https://github.com/sinny777/synapse-forge.git
cd synapse-forge
```

---

## 2. Infrastructure (PostgreSQL + Redis)

### Option A: Use Docker (Recommended for fresh installs)

```bash
docker compose --profile infra up -d
```

This starts PostgreSQL 16 (pgvector) and Redis 7 with default credentials.

### Option B: Use existing PostgreSQL & Redis

If you already have these running, just ensure pgvector is enabled:

```bash
# In your existing PostgreSQL database:
psql -U <user> -d <db> -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Then configure connection details in `backend/.env` (see step 3).

---

## 3. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

Edit `backend/.env` with your database credentials and API keys:

```bash
# ── Database ──────────────────────────────────────
POSTGRES_USER=ntr_user
POSTGRES_PASSWORD=ntr_secret_2026
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=neural_tool_router

# ── Redis ─────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=ntr_redis_2026

# ── LLM Keys (at least one) ──────────────────────
OPENAI_API_KEY=sk-your-key-here
# ANTHROPIC_API_KEY=sk-ant-your-key-here
# Or use Ollama for local models (no key needed):
# OLLAMA_API_BASE=http://localhost:11434
TEACHER_MODEL=ollama/granite4.1:8b
EXPANSION_MODEL=ollama/granite4.1:8b
HEAVY_MODEL=ollama/granite4.1:8b
```

---

## 4. Database: Reset & Seed

SynapseForge uses a direct schema management approach (no Alembic migrations) for rapid prototyping.

### Reset the database & seed default data

```bash
# From backend/ with venv activated:
python -m setup.reset_db
```

This single command will:

1. **Drop** all existing tables
2. **Recreate** the full schema from SQLAlchemy ORM models (Workspace, Tool, Agent, Orchestration)
3. **Ensure** the `pgvector` extension is available
4. **Seed** the "System Default Workspace" with pre-built templates

### What gets seeded

**Workspace:** `System Default Workspace` (`is_default=True`, read-only)

**MCP Servers (8) + REST Template (1):**

| Name | Type | Discovered Tools | Details |
|---|---|---|---|
| Mediclaim MCP Server | MCP_SERVER | 6 | Mock server from `examples/beeai_mediclaim_processing/` |
| UHNW Banking MCP Server | MCP_SERVER | 10 | Mock server from `examples/langgraph_UHNW_banking/` |
| Local File System | MCP_SERVER | — | `npx @modelcontextprotocol/server-filesystem` |
| SQLite Database | MCP_SERVER | — | `uvx mcp-server-sqlite` |
| Web Fetch Server | MCP_SERVER | — | `uvx mcp-server-fetch` |
| Firecrawl MCP | MCP_SERVER | — | `npx firecrawl-mcp` (requires API key) |
| Brave Search MCP | MCP_SERVER | — | `npx @modelcontextprotocol/server-brave-search` (requires API key) |
| Perplexity MCP | MCP_SERVER | — | `npx @perplexity-ai/mcp-server` (requires API key) |
| REST API Template | REST | — | Generic REST API tool skeleton |

**Pre-seeded MCP Child Tools (16):**

The Mediclaim and Banking MCP Servers come with pre-defined tool definitions so they appear in the UI's "Discovered Tools" panel without requiring a live server connection:

| Parent Server | Tool Name | Description |
|---|---|---|
| Mediclaim | `get_policy_details` | Retrieve insurance policy details |
| Mediclaim | `check_coverage_limits` | Check treatment coverage limits |
| Mediclaim | `fetch_discharge_summary` | Fetch hospital discharge summary |
| Mediclaim | `verify_hospital_bills` | Verify itemized hospital bills |
| Mediclaim | `calculate_claimable_amount` | Calculate claimable amount after co-pay |
| Mediclaim | `submit_mediclaim` | Submit final mediclaim for processing |
| Banking | `get_portfolio_summary` | Portfolio holdings & YTD performance |
| Banking | `get_unrealized_gains_losses` | Open positions and P/L status |
| Banking | `get_live_market_data` | Real-time price & analyst ratings |
| Banking | `get_market_news` | Breaking news sentiment |
| Banking | `execute_trade` | Place buy/sell orders |
| Banking | `simulate_capital_gains_tax` | Estimate tax bill for proposed sale |
| Banking | `get_tax_loss_harvesting_options` | Recommend positions to offset gains |
| Banking | `run_aml_transaction_check` | AML check for large wires |
| Banking | `update_card_limit` | Temporarily raise spending limits |
| Banking | `initiate_wire_transfer` | Wire money to external accounts |

> **Total seeded resources:** 25 tools (9 servers + 16 child tools) + 8 agents

**Agents (8) — from example applications:**

| Name | Origin | Attached MCP |
|---|---|---|
| Policy Agent | BeeAI Mediclaim | Mediclaim MCP Server |
| Billing Agent | BeeAI Mediclaim | Mediclaim MCP Server |
| Claim Processing Agent | BeeAI Mediclaim | Mediclaim MCP Server |
| Portfolio Manager Agent | LangGraph Banking | UHNW Banking MCP Server |
| Trading & Market Analyst Agent | LangGraph Banking | UHNW Banking MCP Server |
| Tax & Compliance Officer Agent | LangGraph Banking | UHNW Banking MCP Server |
| Premium Concierge Agent | LangGraph Banking | UHNW Banking MCP Server |
| Banking Supervisor Agent | LangGraph Banking | *(Supervisor — routes to other agents)* |

### Other reset options

```bash
# Reset schema only (skip seeding):
python -m setup.reset_db --no-seed

# Re-seed the default workspace without touching schema:
python -m setup.seed_default_workspace

# Re-seed with a fresh slate (delete old default workspace first):
python -m setup.seed_default_workspace --reset
```

> **Note:** The backend also has automatic schema drift detection on startup.
> Set `DB_AUTO_RESET=true` in `.env` (the default) to auto-reset when models change.

---

## 5. Start the Backend

```bash
# From backend/ with venv activated:
python main.py
```

The FastAPI server starts at **http://localhost:8000**.
API docs available at: **http://localhost:8000/docs**

---

## 6. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the Angular dev server
npm start
```

The Angular app starts at **http://localhost:4200**.

---

## 7. Verify the Setup

Once both servers are running:

1. Open **http://localhost:4200** in your browser
2. Log in via Google or GitHub OAuth
3. The **System Default Workspace** should appear in the workspace switcher
4. Navigate to the **Tool Registry** — you should see 9 MCP servers/tools (all disabled, read-only)
5. Click any MCP server to view its **Discovered Tools** in the modal (e.g., 6 tools for Mediclaim, 10 for Banking)
6. Navigate to **Agent Studio** — you should see 8 pre-built agent definitions (read-only)
7. Create your own workspace and **Import Master Tools** to clone templates into it

---

## 8. Cloning Resources

The Default Workspace is **read-only** — users cannot edit, enable, or delete resources in it. To use the templates:

### From the UI
1. Switch to your **custom workspace** in the workspace selector
2. In the Tool Registry, click **"Import Master Tools"**
3. Select the MCP servers you want to clone → click **Import**
4. The selected servers and their child tools are deep-copied with new UUIDs

### From the API

```bash
# Clone tools from the Default Workspace into your workspace
curl -X POST http://localhost:8000/api/clone/tools \
  -H 'Content-Type: application/json' \
  -d '{
    "destination_workspace_id": "<your-workspace-id>",
    "resource_ids": ["<tool-id-1>", "<tool-id-2>"]
  }'

# Clone agents
curl -X POST http://localhost:8000/api/clone/agents \
  -H 'Content-Type: application/json' \
  -d '{
    "destination_workspace_id": "<your-workspace-id>",
    "resource_ids": ["<agent-id-1>"]
  }'

# Clone a single resource
curl -X POST http://localhost:8000/api/clone/tool/<tool-id> \
  -H 'Content-Type: application/json' \
  -d '{"destination_workspace_id": "<your-workspace-id>"}'
```

> **Note:** When cloning MCP servers, all child tools are automatically included. Agent tool attachments are remapped to the cloned tool IDs.

---

## Project Structure

```
synapse-forge/
├── backend/                    # FastAPI Control Plane
│   ├── main.py                 # Application entry point
│   ├── api/                    # Route handlers
│   │   ├── workspaces.py       # /api/workspaces CRUD
│   │   ├── tools.py            # /api/workspaces/{id}/tools CRUD
│   │   ├── agents.py           # /api/workspaces/{id}/agents CRUD
│   │   ├── workspace_cloning.py # /api/clone/* (deep-copy resources)
│   │   ├── auth.py             # OAuth2 (Google, GitHub) + JWT sessions
│   │   └── ...                 # orchestrations, router, workflow, etc.
│   ├── db/
│   │   ├── engine.py           # Async SQLAlchemy engine & session management
│   │   ├── models.py           # ORM models (Workspace, Tool, Agent, Orchestration)
│   │   └── schemas.py          # Pydantic v2 request/response schemas
│   ├── services/               # Business logic layer
│   ├── setup/
│   │   ├── reset_db.py         # ⚡ Drop + recreate schema + seed
│   │   ├── seed_default_workspace.py  # Default workspace seeder
│   │   └── seed_master_data.py # Master MCP server templates (via API)
│   ├── tool_router/            # NeuralToolRouter engine (train, generate, runtime)
│   ├── .env                    # Environment configuration (not committed)
│   └── requirements.txt        # Python dependencies
├── frontend/                   # Angular + IBM Carbon UI
├── docker-compose.yml          # Infrastructure services (PostgreSQL, Redis)
├── docs/
│   └── platform/
│       └── PLATFORM_REQUIREMENTS_V2.md  # Architecture & requirements spec
├── examples/                   # Multi-agent example applications
│   ├── langgraph_UHNW_banking/
│   └── beeai_mediclaim_processing/
└── infra/                      # DB init scripts
```

---

## Key Concepts

### Default Workspace & Cloning
The **System Default Workspace** (`is_default=True`) is a read-only template workspace accessible to all users. It contains pre-built Agents and MCP Tool configurations that users can **clone** into their own private workspaces.

- **Read-only enforcement:** UI hides edit/delete buttons and disables all form inputs
- **Detection:** Uses the `is_default` boolean flag from the backend (not name matching)
- **Cloning API:** `POST /api/clone/tools` and `POST /api/clone/agents` for batch operations
- **Child tools included:** Cloning an MCP server automatically clones its discovered child tools

### Workspace Status
Each workspace tracks its environment lifecycle via a `status` enum:
- **STOPPED** — No container running (default)
- **RUNNING** — Workspace container is active
- **FAILED** — Container encountered an error

### API Routes

| Route | Method | Description |
|---|---|---|
| `/api/workspaces` | GET, POST | List/create workspaces |
| `/api/workspaces/{id}/tools` | GET, POST | List/register tools in a workspace |
| `/api/workspaces/{id}/agents` | GET, POST | List/create agents in a workspace |
| `/api/clone/tools` | POST | Batch-clone tools between workspaces |
| `/api/clone/agents` | POST | Batch-clone agents between workspaces |
| `/api/clone/{type}/{id}` | POST | Clone a single resource |
| `/api/auth/login/google` | GET | Google OAuth2 login |
| `/api/auth/login/github` | GET | GitHub OAuth2 login |

### Schema Management (No Alembic)
During rapid prototyping, we use `reset_db.py` instead of Alembic migrations. The backend also has built-in schema drift detection that auto-resets on startup when `DB_AUTO_RESET=true`.

---

## Example Applications

The repository includes two multi-agent examples that demonstrate NeuralToolRouter in action:

### LangGraph UHNW Private Banking

```bash
cd examples/langgraph_UHNW_banking
python multi_agent_orchestrator.py --llm ollama --model granite4.1:8b
```

### IBM BeeAI Mediclaim Processing

```bash
cd examples/beeai_mediclaim_processing
python multi_agent_orchestrator.py --llm ollama --model llama3
```

Both examples are fully instrumented with **Langfuse** for observability. Add your Langfuse credentials to `.env` to enable tracing.

---

## Troubleshooting

### PostgreSQL connection refused
- Ensure PostgreSQL is running: `docker compose --profile infra up -d` or check your local instance
- Verify credentials in `backend/.env` match your database configuration
- Ensure pgvector extension is enabled: `CREATE EXTENSION IF NOT EXISTS vector;`

### Redis connection refused
- Ensure Redis is running and the password in `.env` matches
- Default: `REDIS_PASSWORD=ntr_redis_2026`

### Schema errors on startup
- Run `python -m setup.reset_db` to wipe and recreate all tables
- Or set `DB_AUTO_RESET=true` in `.env` for automatic drift detection

### Frontend build errors
- Ensure Node.js 18+ is installed
- Delete `node_modules` and re-install: `rm -rf node_modules && npm install`

### MCP server not connecting
- Ensure `npx` and `uvx` are available in your PATH
- Check tool configurations in the Tool Registry UI

---

## Getting Help

- **Full Documentation**: See [README.md](README.md)
- **Architecture**: See [PLATFORM_REQUIREMENTS_V2.md](docs/platform/PLATFORM_REQUIREMENTS_V2.md)
- **Examples**: Check the [examples/](examples/) directory
- **Issues**: [GitHub Issues](https://github.com/sinny777/synapse-forge/issues)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

---

**Built with ❤️ for the Agentic AI community by [Gurvinder Singh](https://github.com/sinny777)**