# Agentic AI Platform - Requirements & Architecture Document

## 1. Project Overview
This project transforms an existing standalone utility (`SynapseForge`) into a comprehensive, multi-tenant **Agentic AI Platform**. The platform allows users to create workspaces, define AI Agents, connect tools (via REST or Model Context Protocol - MCP), and orchestrate multi-agent workflows using frameworks like LangGraph.

**Core Differentiator:** 
Unlike standard agent frameworks that dump hundreds of tool schemas into an LLM's context window, this platform uses **SynapseForge** as a semantic middleware. The router pre-evaluates user prompts and injects only the top-K highly relevant tool schemas into the LLM's context.

## 2. Technology Stack
*   **Backend:** Python 3.11+, FastAPI, SQLAlchemy (Async), Pydantic v2.
*   **Primary Database:** PostgreSQL with `pgvector` extension (handles both relational data and vector embeddings).
*   **Caching & State:** Redis (Caches tool schemas, semantic router hits, and manages LangGraph session memory).
*   **Orchestration Framework:** LangGraph (with abstraction layer for future frameworks).
*   **Routing Engine:** SynapseForge (Custom semantic embedding/classifier).
*   **Frontend:** Angular (latest), RxJS.
*   **UI Framework:** IBM Carbon Design System for Angular (`@carbon/angular`).

---

## 3. Core Architectural Concepts

### 3.1 Multi-Tenancy (Workspaces)
Every entity is tied to a `workspace_id`. The `SynapseForge` must only evaluate tools belonging to the active workspace. PostgreSQL Row-Level Security (RLS) or strict ORM filtering must be applied.

### 3.2 The "Filter" Pattern (SynapseForge Refactor)
`SynapseForge` acts purely as a semantic filter, NOT an executor. 
*   **Input:** `user_prompt`, `workspace_id`
*   **Process:** Embeds the prompt, compares against the PostgreSQL `pgvector` database of tools registered in `workspace_id`. Checks Redis cache first.
*   **Output:** Top `K` Tool Schemas.
*   **Integration:** Passed to `langchain_core`'s `bind_tools()` before the LangGraph LLM node executes.

### 3.3 Redis Caching & Checkpointing
*   **Router Cache:** Store `hash(prompt + workspace_id)` in Redis. If a user asks the exact same question, bypass embedding generation and return the cached tool schemas.
*   **Graph State:** Use Redis as the `checkpointer` for LangGraph to maintain conversation memory across multi-turn interactions.

---

## 4. Data Models (PostgreSQL Schema)

*   **Workspace**
    *   `id` (UUID, PK)
    *   `name` (String)
    *   `created_at` (Datetime)

*   **Tool**
    *   `id` (UUID, PK)
    *   `workspace_id` (UUID, FK, Indexed)
    *   `name` (String)
    *   `description` (Text)
    *   `type` (Enum: `REST`, `MCP_SERVER`)
    *   `connection_config` (JSONB)
    *   `schema` (JSONB - the OpenAPI/Function schema)
    *   `embedding` (Vector - `pgvector` type for SynapseForge similarity search)

*   **Agent**
    *   `id` (UUID, PK)
    *   `workspace_id` (UUID, FK, Indexed)
    *   `name` (String)
    *   `system_prompt` (Text)
    *   `llm_provider` (String)
    *   `llm_model` (String)
    *   `attached_tool_ids` (ARRAY[UUID])

*   **Orchestration**
    *   `id` (UUID, PK)
    *   `workspace_id` (UUID, FK, Indexed)
    *   `name` (String)
    *   `framework` (Enum: `LANGGRAPH`, `CREWAI`, `AUTOGEN`)
    *   `architecture_type` (Enum: `REACT`, `SUPERVISOR`, `PLANNER`)
    *   `config` (JSONB - map of agent roles)

---

## 5. Frontend Requirements (Angular + IBM Carbon)

### 5.1 App Shell
*   **Header (`cds-header`):** Contains Global Workspace Switcher. Updates a `WorkspaceService` (BehaviorSubject).
*   **Sidenav (`cds-sidenav`):** Navigation links.

### 5.2 Modules & Views
1.  **Dashboard:** High-level metrics (`cds-grid`, `cds-tile`).
2.  **Tool Registry:** 
    *   `cds-tabs` for "Custom Tools" and "MCP Servers".
    *   Form to register a new tool (triggers backend to generate and store `pgvector` embedding).
3.  **Agent Studio:**
    *   Reactive form to create Agents. Multi-select (`cds-combo-box`) to attach Tools.
4.  **Orchestrator Builder:**
    *   Select framework and Architecture. Dynamic form fields based on architecture.
5.  **Playground / Tracing Panel:**
    *   Left side (70%): Chat interface.
    *   Right side (30%): Tracing timeline (`cds-progress-indicator`) showing real-time events (SSE).

---

## 6. Backend Requirements (FastAPI)

### 6.1 Core Operations & Redis
*   **DB Setup:** Use Alembic for migrations. Ensure `CREATE EXTENSION IF NOT EXISTS vector;` runs on startup.
*   **Redis Init:** Setup an async Redis connection pool on FastAPI startup.

### 6.2 Core API Routes
*   `GET/POST /api/workspaces`
*   `GET/POST /api/workspaces/{id}/tools` (POST generates embedding and saves to DB).
*   `GET/POST /api/workspaces/{id}/agents`
*   `GET/POST /api/workspaces/{id}/orchestrations`
*   `POST /api/router/predict` (Checks Redis -> Generates Embedding -> Queries pgvector -> Returns schemas).
*   `POST /api/orchestrator/{orchestration_id}/execute` 

### 6.3 The LangGraph Engine Implementation
1.  Read the `Orchestration` JSONB config.
2.  Instantiate LangChain LLMs.
3.  **Middleware Injection:** Define node `route_tools` calling `SynapseForge.predict_tools()`.
4.  Bind tool schemas (`llm.bind_tools(filtered_schemas)`).
5.  Pass Redis checkpointer to `StateGraph.compile(checkpointer=redis_checkpointer)`.
6.  Execute graph and stream tracing events (SSE).

---

## 7. Execution Strategy (For IDE AI Agent)

*   **Phase 1: Infrastructure & DB.** Set up `docker-compose.yml` with PostgreSQL (pgvector image) and Redis. Configure FastAPI SQLAlchemy async engine and Redis connection pool.
*   **Phase 2: Data Models.** Implement the SQLAlchemy models (including pgvector columns) and Pydantic schemas. Write Alembic migrations.
*   **Phase 3: Router Refactor.** Update `SynapseForge` to use `pgvector` for semantic search instead of in-memory arrays. Add Redis caching for predictions.
*   **Phase 4: Engine Abstraction.** Implement the `LangGraphEngine`, integrating the Redis Checkpointer for state memory and the router middleware.
*   **Phase 5: Frontend Shell & Services.** Setup Angular with IBM Carbon. Build the App Shell, Sidenav, and Workspace state management.
*   **Phase 6: Frontend Views.** Implement Tool Registry, Agent Studio, and Orchestrator Builder reactive forms.
*   **Phase 7: Observability UI.** Implement the Playground chat and trace log interface connecting to backend SSE.