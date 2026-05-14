# Neural Tool Router - 🚀 Quick Start Guide

Get up and running with the modern Neural Tool Router platform in just a few minutes! 

This guide covers setting up the full-stack architecture: a **FastAPI backend** with PostgreSQL, and an **Angular frontend** dashboard.

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** & npm
- **PostgreSQL 14+** (running locally or remotely)
- API keys (OpenAI, Anthropic, etc. for LLM generation/execution)

---

## 1. Backend Setup (FastAPI + PostgreSQL)

### Install Dependencies
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Configuration
Create a `.env` file in the `backend/` directory:

```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/neural_tool_router

# API Keys
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

### Database Initialization & Seeding
Apply database migrations and seed the initial master data. The seed script pre-loads useful MCP servers (Mediclaim, UHNW Banking, Local File System, etc.) into your workspace:

```bash
# Run Alembic migrations to create tables
alembic upgrade head

# Seed master data
python setup/seed_master_data.py
```

### Start the Backend Server
```bash
uvicorn api.main:app --reload --port 8000
```
The backend API will now be running at `http://localhost:8000`.

---

## 2. Frontend Setup (Angular)

Open a new terminal window:

```bash
cd frontend
npm install
npm start
```
The application will compile and launch the dashboard at `http://localhost:4200`.

---

## 3. Platform Workflow

Open `http://localhost:4200` in your browser. The Neural Tool Router is built around a centralized configuration dashboard and a 3-phase execution pipeline.

### Tool Registry
Navigate to the **Tool Registry** via the left navigation rail.
- **Enable Servers**: Enable the pre-seeded MCP Servers (like the UHNW Banking Server).
- **Auto-Discovery**: Enabling a server automatically discovers and enables all of its child tools.
- **Edit Modal**: Click the Edit icon to view JSON configurations and inspect discovered tools.

### Phase 1: Generate Synthetic Data
- Go to the **Generate** tab.
- Select your active tools and choose a Teacher LLM.
- Generate diverse, synthetic natural language queries that map directly to your enabled tools. This data forms the bedrock for training your router.

### Phase 2: Train Model
- Go to the **Train** tab.
- Fine-tune a semantic embedding model (e.g., `all-MiniLM-L6-v2`) on your synthetic dataset using contrastive learning.
- Watch the live loss graph to monitor training convergence.

### Phase 3: Run Orchestrator
- Go to the **Run** tab.
- Execute natural language queries against your trained model.
- The system evaluates the query, uses Reciprocal Rank Fusion (RRF) to retrieve the best tools, and passes them to a LangGraph-powered Agent Orchestrator to execute operations.

---

## 📁 Architecture Overview

```text
neural-tool-router/
├── backend/                  # FastAPI & Python Orchestrator
│   ├── api/                  # REST API Endpoints
│   ├── db/                   # SQLAlchemy Models & Migrations
│   ├── services/             # MCP Discovery, Embeddings, Training Logic
│   ├── orchestrator/         # LangGraph Execution Engine
│   └── setup/                # Seed scripts
├── frontend/                 # Angular UI Application
│   ├── src/app/
│   │   ├── components/       # UI Components (Registry, Generate, Train, Run)
│   │   ├── services/         # API Service Clients
│   │   └── styles/           # IBM Carbon Design System overrides
├── docs/                     # Platform Documentation
└── examples/                 # Sample FastMCP Servers (Banking, Mediclaim)
```

## Troubleshooting

- **Database Connection Errors**: Ensure PostgreSQL is running and the `DATABASE_URL` in your `.env` is correct.
- **Angular Build Errors**: Ensure you have run `npm install` to download `carbon-components-angular` and other UI dependencies.
- **Tools Failing to Discover**: Ensure the Python environment running the backend has access to necessary binaries (e.g., `npx` for JavaScript-based MCP servers).

## Next Steps

- Check [`ARCHITECTURE.md`](ARCHITECTURE.md) for detailed deep-dives into the database schema, LangGraph agent design, and UI interactions.
- Refer to the [`examples/`](../examples/) folder to see how to build custom Python-based FastMCP servers to integrate with the router.