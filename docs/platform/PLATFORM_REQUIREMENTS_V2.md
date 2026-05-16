# SynapseOS (Agentic AI Platform) - Requirements & Architecture Document

## 1. Project Overview
SynapseOS transforms a standalone routing utility (`NeuralToolRouter`) into a comprehensive, multi-tenant **Agentic AI Platform**. It supports both synchronous workflows (LangGraph) and asynchronous event-driven choreographies (Kafka), backed by shared Redis state and OpenTelemetry tracing.

**Core Differentiators:** 
1. **NeuralToolRouter Middleware:** Pre-evaluates prompts to inject only the top-K relevant tool schemas into the LLM, reducing latency and hallucinations.
2. **Containerized Execution Environments:** The platform acts as a Control Plane. Every user's workspace runs in a dynamically provisioned, isolated Docker container containing their specific Agents, NeuralToolRouter model, and MCP Servers.
3. **Template/Default Workspace:** A built-in repository of pre-configured Agents (Research, RAG, Coding) and MCP Tools that users can clone into their own custom workspaces.

## 2. Technology Stack
*   **Control Plane (Backend API):** Python 3.11+, FastAPI, SQLAlchemy (Async), Docker SDK (`docker` Python package).
*   **Data Plane (Workspace Containers):** Isolated Python runtimes executing LangGraph, Kafka Consumers, and local MCP Servers.
*   **Primary Database:** PostgreSQL with `pgvector` (Stores configurations, embeddings, and telemetry metadata).
*   **State & Messaging:** Redis (Shared state checkpointer) and Confluent Kafka (Pub/Sub Event Bus).
*   **Tracing:** OpenTelemetry (Context propagation across sync/async boundaries).
*   **Frontend:** Angular (latest) with IBM Carbon Design System (`@carbon/angular`).

---

## 3. Core Architectural Concepts

### 3.1 The "Default Workspace" & Cloning
*   A system-level workspace (`is_default=True`) accessible to all users as read-only.
*   **Pre-loaded Agents:** Research Agent, FrontEnd Coding Agent, RAG Agent.
*   **Pre-loaded Tools:** Standard REST API templates, local File System MCP, Web Search MCP.
*   Users can browse this workspace and click "Clone to My Workspace", creating deep copies of these entities in their database isolated by their `workspace_id`.

### 3.2 Control Plane vs. Data Plane (Container Isolation)
*   **Control Plane:** The central FastAPI app serving the UI, managing the PostgreSQL database, and issuing Docker commands.
*   **Data Plane (Workspace Runner):** When a user clicks "Start Environment", the Control Plane uses the Docker SDK to spin up a custom container. This container mounts the user's specific `NeuralToolRouter` trained weights, starts the MCP servers defined in their DB, and initializes the LangGraph/Kafka execution engine.

### 3.3 Hybrid Mesh (Sync + Async execution)
*   Agents share a unified Redis state (`workspace:{id}:workflow:{workflow_id}`).
*   LangGraph handles synchronous execution; Kafka topics handle asynchronous handoffs between agents.
*   OpenTelemetry headers (`traceparent`) are injected into Kafka messages to ensure unbroken observability in the UI.

---

## 4. Data Models (PostgreSQL Schema)

*   **Workspace**
    *   `id` (UUID, PK)
    *   `name` (String)
    *   `is_default` (Boolean, Default: False)
    *   `status` (Enum: `STOPPED`, `RUNNING`, `FAILED`) - Tracks container status.

*   **Tool** (id, workspace_id, name, description, type, connection_config, schema, embedding)
*   **Agent** (id, workspace_id, name, system_prompt, llm_provider, llm_model, attached_tool_ids)
*   **Orchestration** (id, workspace_id, name, framework, architecture_type, config)

---

## 5. Frontend Requirements (Angular + IBM Carbon)

### 5.1 Workspace Management & Environment Controls
*   **Header:** Workspace Switcher dropdown.
*   **Environment Toolbar:** In a custom workspace, show a prominent indicator (e.g., `cds-tag`) showing Environment Status (Running/Stopped). Include "Start Environment" and "Stop Environment" buttons.

### 5.2 Default Workspace Gallery (Marketplace)
*   A dedicated view when the "Default Workspace" is selected.
*   Displays pre-built Agents and Tools as cards (`cds-tile`).
*   Each card has a primary action: "Clone to Workspace" (opens a modal to select the destination workspace).

### 5.3 Unified Builder & Tracing
*   **Hybrid Graph Builder:** Visual canvas mapping LangGraph edges (Sync) and Kafka topics (Async). Includes a "Code Mode" toggle with Monaco Editor.
*   **Observability Dashboard:** A grouped timeline fetching OpenTelemetry data, visualizing the execution across the isolated Docker container.

---

## 6. Backend Requirements (FastAPI Control Plane)

### 6.1 Workspace & Cloning APIs
*   `GET /api/workspaces/default/agents`
*   `POST /api/workspaces/{src_id}/clone-resource/{resource_type}/{resource_id}` -> Payload contains `destination_workspace_id`.

### 6.2 Docker Orchestration APIs (Workspace Runner)
*   `POST /api/workspaces/{id}/environment/start`: 
    1. Reads workspace config from DB.
    2. Generates a dynamic `docker-compose.yml` or uses Docker Python SDK.
    3. Spins up the container attached to the shared Redis/Kafka network.
*   `POST /api/workspaces/{id}/environment/stop`: Tears down the container.

### 6.3 API Gateway Proxy
*   `POST /api/workspaces/{id}/execute`: The Control Plane receives this from the UI and proxies it to the running Data Plane container's internal API to trigger the workflow.

---

## 7. Execution Strategy (For IDE AI Agent)

*   **Phase 1: DB & Default Templates.** Add `is_default` to DB. Create a seeding script to populate the DB with the Research Agent, Coding Agent, and RAG Agent.
*   **Phase 2: Cloning Logic.** Implement the deep-copy backend APIs to duplicate templates into custom workspaces.
*   **Phase 3: Docker Control Plane.** Integrate the `docker` Python package. Write the `WorkspaceRunner` service to dynamically spin up/down containers per workspace.
*   **Phase 4: Agent Engine & Hybrid Mesh.** Ensure the LangGraph and Kafka execution logic runs gracefully *inside* the generated Docker container.
*   **Phase 5: Frontend Market & Controls.** Build the Default Workspace UI, Clone buttons, and Start/Stop Container controls in Angular.
*   **Phase 6: Unified Builder & Tracing.** Implement the visual drag-and-drop hybrid builder and OpenTelemetry trace viewer.