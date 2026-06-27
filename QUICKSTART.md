# SynapseForge — Quick Start Guide

Get the full-stack Agentic AI Platform running locally in under 10 minutes.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Backend API & NeuralToolRouter engine |
| Node.js | 18+ | Angular frontend & MCP server runtimes |
| MongoDB | 7+ | Primary backend database |
| Milvus | 2.4+ | Semantic vector search service |
| Redis | 7+ | Caching & LangGraph checkpointing |
| Docker | 24+ | Docker Desktop for workspace container orchestration (Control Plane) |
| Ollama | Latest | Local LLM inference (default for development) |

---

## 1. Clone & Setup

```bash
git clone https://github.com/sinny777/synapse-forge.git
cd synapse-forge
```

---

## 2. Infrastructure (MongoDB + Milvus + Redis)

### Option A: Use Docker (Recommended for fresh installs)

```bash
docker compose --profile infra up -d
```

This starts MongoDB 7, Milvus standalone, and Redis 7 with default credentials.

### Option B: Use existing MongoDB, Milvus & Redis

If you already have these running, configure their connection details in
`backend/.env` (see step 3).

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

Edit `backend/.env` with your infrastructure credentials:

```bash
# ── MongoDB ───────────────────────────────────────
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DATABASE=synapse_forge
MONGODB_USER=synapse_user
MONGODB_PASSWORD=synapse_secret_2026
MONGODB_AUTH_DATABASE=admin

# ── Milvus ────────────────────────────────────────
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION_PREFIX=synapse_forge

# ── Redis ─────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6380
REDIS_PASSWORD=synapse_redis_2026

# ── Docker Control Plane (workspace containers) ──
# WORKSPACE_CONTAINER_IMAGE=python:3.11-slim
# DOCKER_NETWORK_NAME=synapse-forge_default

# ── Ollama (Local LLM — default for development) ─
OLLAMA_API_BASE=http://localhost:11434

# ── IBM Cloud Object Storage (COS) ───────────────
IBM_COS_ENDPOINT=https://s3.us-south.cloud-object-storage.appdomain.cloud
IBM_COS_API_KEY_ID=your-ibm-cos-api-key
IBM_COS_SERVICE_INSTANCE_ID=crn:v1:bluemix:public:cloud-object-storage:global:a/your-account-id:your-service-instance-id::
IBM_COS_BUCKET_NAME=synapse-forge
```

> **Note:** LLM provider API keys (OpenAI, Anthropic, Google, etc.) are no longer configured via environment variables. They are managed per-workspace through the **Settings** page in the UI. See [LLM Configuration](#10-llm-configuration) below.

### IBM Cloud Object Storage Setup (Optional but Recommended)

SynapseForge uses IBM Cloud Object Storage (COS) to store all pipeline artifacts:
- **Phase 1 (Generate)**: Synthetic datasets and tool cache
- **Phase 2 (Train)**: Fine-tuned models, FAISS indexes, BM25 indexes

**For Development:** If COS credentials are not configured, the system automatically runs in MOCK mode using local directory simulation under `data/cos_mock`. This is suitable for testing but not recommended for production.

**For Production:** See **[SETUP_COS.md](SETUP_COS.md)** for complete setup instructions including:
- Installing IBM COS SDK
- Getting credentials (HMAC or IAM)
- Creating buckets
- Troubleshooting common issues

**Quick Configuration** in `.env`:
```bash
IBM_COS_ENDPOINT=https://s3.us-south.cloud-object-storage.appdomain.cloud
IBM_COS_BUCKET_NAME=synapse-forge
IBM_COS_ACCESS_KEY_ID=your_access_key_id_here
IBM_COS_SECRET_ACCESS_KEY=your_secret_access_key_here
```

---

## 4. Database: Reset & Seed

SynapseForge now uses MongoDB for primary persistence and Milvus for semantic
tool retrieval.

### Reset the database & seed default data

```bash
# From backend/ with venv activated:
python -m setup.reset_db
```

This command resets the managed MongoDB collections and seeds the
"System Default Workspace" with pre-built templates.

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

**LLM Configurations (3) — Ollama defaults for local development:**

| Name | Provider | Model | Temperature | Max Tokens |
|---|---|---|---|---|
| Teacher Config | Ollama | granite4.1:8b | 0.8 | 2048 |
| Expansion Config | Ollama | granite4.1:8b | 0.3 | 1024 |
| Heavy Config | Ollama | granite4.1:8b | 0.0 | 4096 |

> **Total seeded resources:** 25 tools (9 servers + 16 child tools) + 8 agents + 3 LLM configs

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
7. Navigate to **Settings** — you should see 3 pre-configured LLM configs (Teacher, Expansion, Heavy — all Ollama, read-only)
8. Create your own workspace and **Import Master Tools** to clone templates into it

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

## 9. Docker Control Plane (Workspace Environments)

SynapseForge acts as a **Control Plane** that can spin up isolated Docker containers per workspace. Each container is a **Data Plane** instance running the workspace's agents, tools, and NeuralToolRouter model.

### Prerequisites

- **Docker Desktop** must be running and accessible
- The Docker Python SDK (`docker>=7.0.0`) is included in `requirements.txt`

### Starting a Workspace Environment

```bash
# Start a workspace container
curl -X POST http://localhost:8000/api/workspaces/<workspace-id>/environment/start \
  -H 'Content-Type: application/json'

# Stop a workspace container
curl -X POST http://localhost:8000/api/workspaces/<workspace-id>/environment/stop \
  -H 'Content-Type: application/json'
```

### What Happens

1. The Control Plane pulls the container image (default: `python:3.11-slim`)
2. Creates a container named `sf-workspace-<workspace-id>`
3. Injects `WORKSPACE_ID`, `DATABASE_URL`, and `REDIS_URL` as environment variables
4. Connects the container to the shared Docker network (`synapse-forge_default`)
5. Updates the workspace `status` in PostgreSQL to `RUNNING` or `STOPPED`

### Configuration (Optional)

Add these to `backend/.env` to customize container behaviour:

```bash
# Custom Data Plane image (default: python:3.11-slim)
WORKSPACE_CONTAINER_IMAGE=your-registry/synapse-dataplane:latest

# Docker network name (default: synapse-forge_default)
DOCKER_NETWORK_NAME=synapse-forge_default

# DB/Redis hostnames as seen from inside Docker network
WORKSPACE_DB_HOST=ntr_postgres
WORKSPACE_REDIS_HOST=ntr_redis
```

> **Note:** If Docker is not running, the backend starts normally but the environment start/stop endpoints return HTTP 503.

---

## 10. LLM Configuration

SynapseForge uses **workspace-scoped LLM configurations** stored in the database. This replaces the old approach of putting all LLM API keys in the `.env` file.

### Architecture

- LLM configurations belong to a **workspace** (not global)
- Each config has a **name**, **provider**, **model**, **credentials**, and tuning parameters
- The **Default Workspace** ships with 3 pre-seeded Ollama configs for local development
- **Custom workspaces** let users create their own configs with any supported provider

### Supported Providers

| Provider | Icon | Credential Required | Example Models |
|---|---|---|---|
| Ollama | 🦙 | API Base URL | granite4.1:8b, llama2, mistral |
| OpenAI | 🤖 | API Key | gpt-4o, gpt-4o-mini |
| Anthropic | 🧠 | API Key | claude-3-5-sonnet, claude-3-opus |
| Google AI | 🔷 | API Key | gemini-pro, gemini-1.5-flash |
| IBM Watsonx | 💙 | API Key + Project ID | granite-13b-chat-v2 |
| Groq | ⚡ | API Key | llama-3.1-70b-versatile |
| Azure OpenAI | ☁️ | API Key + Base URL + Version | gpt-4, gpt-35-turbo |
| Cohere | 🌊 | API Key | command-r-plus |
| AWS Bedrock | 🪨 | AWS Key + Secret + Region | anthropic.claude-3-sonnet |
| Vertex AI | 🔺 | Project + Location | gemini-pro |

### Managing Configs via the UI

1. Navigate to **Settings** in the sidebar
2. If on the **Default Workspace**: view the 3 pre-seeded configs (read-only)
3. Switch to a **custom workspace** to create, edit, or delete configs
4. Click **"Add Configuration"** → select a provider → fill in credentials → save

### Managing Configs via the API

```bash
# List LLM configs for a workspace
curl http://localhost:8000/api/workspaces/<workspace-id>/llm-configs

# Create a new LLM config
curl -X POST http://localhost:8000/api/workspaces/<workspace-id>/llm-configs \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "My OpenAI Config",
    "provider": "openai",
    "model_name": "gpt-4o",
    "credentials": {"api_key": "sk-..."},
    "temperature": 0.7,
    "max_tokens": 4096
  }'

# Update a config
curl -X PUT http://localhost:8000/api/workspaces/<workspace-id>/llm-configs/<config-id> \
  -H 'Content-Type: application/json' \
  -d '{"temperature": 0.0}'

# Delete a config
curl -X DELETE http://localhost:8000/api/workspaces/<workspace-id>/llm-configs/<config-id>
```

> **Note:** The Default Workspace's LLM configs are read-only. The API returns HTTP 403 if you attempt to create, update, or delete configs in the default workspace.

---

## 11. IBM Cloud Object Storage (COS) & Pipeline Integration

SynapseForge utilizes **IBM Cloud Object Storage (COS)** to securely store all pipeline artifacts generated during **Phase 1: Generate** (synthetic datasets, tool caches) and **Phase 2: Train** (fine-tuned model checkpoints, FAISS indexes, BM25 indices).

### Architecture & Pipeline Lifecycle Flow

To maintain a secure, distributed, and pristine server environment:
1. **Dynamic LLM Configuration Resolution (Phase 1):** The user's active dropdown selection in the global UI header is dynamically sent to the backend as a UUID. The API resolves this `LLMConfig` UUID directly from the PostgreSQL database, extracts the model name, provider (e.g. Watsonx, OpenAI, Anthropic, Ollama), and encrypted API credentials/endpoints, sets them as environment variables, prefixes the model correctly for LiteLLM routing (e.g. `openai/gpt-4o`, `watsonx/meta-llama/...`), and executes synthetic generation.
2. **Upload & Clean:** As soon as Phase 1 or Phase 2 finishes executing, the generated files (or folders) are uploaded to IBM COS under workspace-specific isolated key paths (`workspaces/{workspace_id}/{phase}/{artifact_type}/{filename}`). Once uploaded, they are registered in the `pipeline_artifacts` database table and instantly deleted from the local disk.
3. **Pristine Local Disk (Automated Directory Cleanup):** Immediately upon success or error of the generation/training phases, the system runs a deep recursive directory walker under the host's `data/workspaces/{workspace_id}/` workspace folder. It wipes out all empty staging folders (`datasets`, `logs`, `models`, etc.) and removes the workspace folder itself, ensuring no stray local folder structures remain on the filesystem.
4. **On-Demand Caching:** Before starting model training, running queries, or evaluating performance, the backend checks for local files. If missing, it queries the database for the active COS reference, downloads the files dynamically back to local workspace cache folders, runs the operations, and streams/serves them on-demand!
5. **Archiving:** Versioned datasets and versioned model archives are automatically synced directly to IBM COS.

### Configuration (`.env`)


Add the following variables to your `backend/.env` file to enable IBM Cloud Object Storage:

```bash
# ── IBM Cloud Object Storage (COS) ────────────────
# Endpoint URL matching your bucket region (e.g. us-south, eu-gb, etc.)
IBM_COS_ENDPOINT=https://s3.us-south.cloud-object-storage.appdomain.cloud
# Default bucket name (will be created automatically if it doesn't exist)
IBM_COS_BUCKET_NAME=synapse-forge-bucket

# Option A: Standard IBM Cloud IAM API Key Authentication (Preferred)
IBM_COS_API_KEY_ID=your-ibm-cos-api-key
IBM_COS_SERVICE_INSTANCE_ID=crn:v1:bluemix:public:cloud-object-storage:global:a/your-account-id:your-service-instance::

# Option B: S3-Compatible HMAC Access Key Authentication (Alternative)
# IBM_COS_ACCESS_KEY_ID=your-hmac-access-key-id
# IBM_COS_SECRET_ACCESS_KEY=your-hmac-secret-access-key
```

### Development Mock Mode

If no credentials are provided in `.env`, the system **automatically falls back to Mock Storage Mode**.
* Mock mode simulates all bucket creations, file uploads, recursively zipped folders, on-demand downloads, and deletion routines locally inside the `data/cos_mock/` directory.
* This ensures that developers can start, build, and test the entire SynapseForge platform out-of-the-box without requiring a live IBM Cloud account or active internet connection!

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
│   │   ├── llm_configs.py      # /api/workspaces/{id}/llm-configs CRUD
│   │   ├── workspace_cloning.py # /api/clone/* (deep-copy resources)
│   │   ├── workspace_environment.py # /api/workspaces/{id}/environment/start|stop
│   │   ├── auth.py             # OAuth2 (Google, GitHub) + JWT sessions
│   │   └── ...                 # orchestrations, router, workflow, etc.
│   ├── db/
│   │   ├── engine.py           # Async SQLAlchemy engine & session management
│   │   ├── models.py           # ORM models (Workspace, Tool, Agent, Orchestration, LLMConfig)
│   │   └── schemas.py          # Pydantic v2 request/response schemas
│   ├── services/               # Business logic layer
│   │   ├── workspace_docker_service.py  # Docker SDK container lifecycle
│   │   ├── embedding_service.py
│   │   ├── router_service.py
│   │   └── mcp_service.py
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
The **System Default Workspace** (`is_default=True`) is a read-only template workspace accessible to all users. It contains pre-built Agents, MCP Tool configurations, and LLM configs that users can **clone** into their own private workspaces.

- **Read-only enforcement:** UI hides edit/delete buttons and disables all form inputs
- **Detection:** Uses the `is_default` boolean flag from the backend (not name matching)
- **Cloning API:** `POST /api/clone/tools` and `POST /api/clone/agents` for batch operations
- **Child tools included:** Cloning an MCP server automatically clones its discovered child tools

### LLM Configuration Model
LLM configurations are **workspace-scoped** database records, not environment variables. Each config stores:
- **name** — user-friendly label (e.g., "Teacher Config", "My GPT-4o")
- **provider** — one of: ollama, openai, anthropic, google, ibm_watsonx, groq, azure, cohere, bedrock, vertex_ai
- **model_name** — the model identifier (e.g., granite4.1:8b, gpt-4o)
- **credentials** — provider-specific auth (api_key, api_base, etc.)
- **temperature** / **max_tokens** — tuning parameters

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
| `/api/workspaces/{id}/llm-configs` | GET, POST | List/create LLM configurations |
| `/api/workspaces/{id}/llm-configs/{cid}` | GET, PUT, DELETE | Read/update/delete an LLM config |
| `/api/workspaces/{id}/environment/start` | POST | Start workspace Docker container |
| `/api/workspaces/{id}/environment/stop` | POST | Stop workspace Docker container |
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

### LLM configs not appearing
- Ensure the database was seeded: `python -m setup.seed_default_workspace`
- Check that the active workspace is selected in the UI workspace switcher
- For custom workspaces, create configs via the Settings page

---

## Getting Help

- **Full Documentation**: See [README.md](README.md)
- **Architecture**: See [PLATFORM_REQUIREMENTS_V2.md](docs/platform/PLATFORM_REQUIREMENTS_V2.md)
- **Examples**: Check the [examples/](examples/) directory
- **Issues**: [GitHub Issues](https://github.com/sinny777/synapse-forge/issues)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

---

**Built with ❤️ for the Agentic AI community by [Gurvinder Singh](https://github.com/sinny777)**