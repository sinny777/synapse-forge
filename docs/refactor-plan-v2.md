# SynapseForge — API Package Refactor Plan v2

## Top-Level Overview

**Goal:** Refactor the 17 feature sub-packages in `backend/api/` into 7 domain-aligned packages where each package has clean internal separation of concern:
`router.py` (route handlers) · `schemas.py` (Pydantic models) · `helpers.py` (utilities) · `service.py` (business logic).

Duplicated cross-cutting helpers are consolidated into `api/common/`.

**Scope:**
- Consolidate 17 → 7 domain packages (zero URL changes)
- Split each monolithic `router.py` into `router.py` + `schemas.py` + `helpers.py` + `service.py` where warranted
- Extract shared duplicated utilities into `api/common/`
- No changes to `db/`, `services/`, `tool_router/`, `main.py`, or any frontend file

**Non-goals:**
- Changing API endpoint URLs
- Modifying business logic
- Touching the `db/`, `services/`, or `tool_router/` layers

---

## Proposed Domain Package Structure

```
backend/api/
├── __init__.py               ← Updated ALL_ROUTERS list
├── dependencies.py           ← Unchanged (shared DI)
│
├── common/                   ← NEW: shared utilities used across domains
│   ├── __init__.py
│   ├── utils.py              ← _model_from_doc, _get_workspace_or_404,
│   │                            _sse_event, _generate_embedding,
│   │                            _safe_json, _utc_iso
│   └── exceptions.py         ← (future; stubbed now)
│
├── auth/                     ← Unchanged domain (1 router)
│   ├── __init__.py
│   ├── router.py             ← Route handlers only
│   ├── schemas.py            ← LoginRequest
│   ├── config.py             ← SECRET_KEY, serializer, oauth, demo creds
│   └── helpers.py            ← _make_auth_response, _make_token_cookie_response,
│                                _callback_uri
│
├── workspaces/               ← Unchanged domain (1 router, simple CRUD)
│   ├── __init__.py
│   └── router.py             ← Uses api/common/utils.py helpers
│
├── configurations/           ← MERGED: categories + env_config + llm_configs
│   ├── __init__.py
│   ├── router.py             ← All route handlers for the 3 former packages
│   ├── schemas.py            ← (LLMConfig schemas already in db/schemas.py;
│   │                            this file empty/stub unless new schemas needed)
│   └── helpers.py            ← _llm_config_from_doc, _get_workspace
│
├── resources/                ← MERGED: tools + agents + orchestrations
│   ├── __init__.py
│   ├── router.py             ← All route handlers for the 3 resource types
│   ├── schemas.py            ← Schemas defined IN the old router files:
│   │                            (all CRUD schemas already in db/schemas.py,
│   │                             so this holds any request-only models not there)
│   ├── helpers.py            ← _tool_from_doc, _agent_from_doc,
│   │                            _orchestration_from_doc,
│   │                            _validate_collaborators,
│   │                            _build_agent_read_payload,
│   │                            _load_agent_tools, _load_agent_llm_config,
│   │                            _load_collaborator_agents,
│   │                            _mask_tool_secrets, _resolve_provider_model,
│   │                            _apply_llm_credentials
│   └── service.py            ← _execute_single_agent, _select_tools_for_prompt,
│                                _build_mcp_client_for_tools (complex execution logic)
│
├── workspace_ops/            ← MERGED: workspace_cloning + workspace_environment
│   ├── __init__.py           ← (was two separate packages; same workspace concern)
│   ├── router.py             ← All route handlers
│   ├── schemas.py            ← CloneBatchRequest, CloneSingleRequest,
│   │                            CloneResult, CloneWorkflowResourcesRequest,
│   │                            EnvironmentActionResponse
│   ├── helpers.py            ← _resolve_source_workspace,
│   │                            _get_docker_service, get_docker_service
│   └── service.py            ← _clone_tool, _clone_agent
│
├── execution/                ← MERGED: execute (orchestrator SSE) + neural_router predict
│   ├── __init__.py
│   ├── router.py             ← Route handlers: execute + predict
│   ├── schemas.py            ← ExecuteRequest
│   └── helpers.py            ← _sse_event (single canonical copy)
│
└── neural_router_pipeline/   ← MERGED: workflow + data + datasets + model_registry + scenarios
    ├── __init__.py
    ├── router.py             ← All route handlers: generate, train, run, evaluate,
    │                            status, data, datasets, models, scenarios
    ├── schemas.py            ← GenerateConfig, TrainConfig, RunConfig, EvaluateConfig,
    │                            ArchiveModelRequest, ArchiveDatasetRequest,
    │                            LoadDatasetRequest, AgentExecuteRequest (standalone),
    │                            SyntheticDataUpdate
    └── helpers.py            ← _apply_dict_to_obj, _update_global_config,
                                 _ensure_run_artifacts_downloaded
```

### Consolidation Summary

| New domain package | Old packages merged | Rationale |
|---|---|---|
| `auth/` | auth (unchanged) | Auth is its own domain |
| `workspaces/` | workspaces (unchanged) | Root entity — standalone |
| `configurations/` | categories + env_config + llm_configs | All configuration/taxonomy data |
| `resources/` | tools + agents + orchestrations | All workspace-scoped CRUD entities |
| `workspace_ops/` | workspace_cloning + workspace_environment | Both operate on workspace lifecycle |
| `execution/` | execute + neural_router | Both are execution/invocation endpoints |
| `neural_router_pipeline/` | workflow + data + datasets + model_registry + scenarios | All belong to the 3-phase NTR pipeline |

**17 packages → 7 domain packages**

---

## Internal File Responsibilities

### Every domain package follows this layout:

| File | Holds | Notes |
|---|---|---|
| `router.py` | `@router.get/post/put/delete` handlers only | Imports from schemas.py, helpers.py, service.py |
| `schemas.py` | Pydantic request/response models defined in THIS domain | Only schemas not already in `db/schemas.py` |
| `helpers.py` | Pure utility functions: doc converters, formatters, small wrappers | No DB mutations |
| `service.py` | Complex business logic with async DB operations | Only in `resources/` and `workspace_ops/` |
| `config.py` | Module-level constants + initialized objects | Only in `auth/` |

### `api/common/utils.py` — Shared Utilities

Consolidates duplicated helpers found across multiple routers:

| Function | Currently duplicated in |
|---|---|
| `model_from_doc(doc, ModelClass)` | agents, tools, workspaces, orchestrations, llm_configs, workspace_cloning (6×) |
| `get_workspace_or_404(db, workspace_id)` | agents, tools, orchestrations (3×) |
| `sse_event(type, label, detail, ...)` | agents, execute (2×) |
| `generate_embedding(ws, name, desc, schema)` | tools, workspace_cloning (2×) |
| `safe_json(value)` | agents (internal) |
| `utc_iso()` | agents (internal) |

---

## Sub-Tasks

---

### Sub-Task 1 — Create `api/common/` with shared utilities

**Intent:** Consolidate duplicated utility functions from across all routers into one shared module so every domain package can import them instead of re-implementing them.

**Expected Outcomes:**
- `api/common/__init__.py` and `api/common/utils.py` exist
- `utils.py` contains: `model_from_doc`, `get_workspace_or_404`, `sse_event`, `generate_embedding`, `safe_json`, `utc_iso`
- All functions are pure (no side effects), documented, and typed

**Todo List:**
1. Create `backend/api/common/__init__.py`
2. Create `backend/api/common/utils.py` with all shared utilities extracted from their source files:
   - `model_from_doc(doc, model_class)` — generic MongoDB doc → Pydantic model
   - `get_workspace_or_404(db, workspace_id)` — fetch workspace or raise 404
   - `sse_event(event_type, label, detail, ...)` — format SSE data frame (canonical copy)
   - `generate_embedding(ws, name, description, schema_def)` — delegate to `embedding_service`
   - `safe_json(value)` — safe JSON serialization
   - `utc_iso()` — current UTC timestamp as ISO string

**Relevant Context:**
- [`backend/api/agents/router.py`](backend/api/agents/router.py) — source of `_sse_event`, `_safe_json`, `_utc_iso`
- [`backend/api/execute/router.py`](backend/api/execute/router.py) — source of duplicate `_sse_event`
- [`backend/api/tools/router.py`](backend/api/tools/router.py) — source of `_generate_embedding`

**Status:** `[x] done`

---

### Sub-Task 2 — Refactor `auth/` package

**Intent:** Split the monolithic `auth/router.py` into `config.py` (OAuth setup), `schemas.py` (LoginRequest), `helpers.py` (response builders), and `router.py` (handlers only).

**Expected Outcomes:**
- `auth/config.py`: SECRET_KEY, serializer, DEMO_EMAIL/PASSWORD, oauth registration
- `auth/schemas.py`: `LoginRequest`
- `auth/helpers.py`: `_make_auth_response`, `_make_token_cookie_response`, `_callback_uri`
- `auth/router.py`: Only the 7 route handler functions; imports from the new files
- `auth/__init__.py`: Exports `router` and `get_current_user`

**Todo List:**
1. Create `auth/config.py` — extract all module-level config and OAuth setup
2. Create `auth/schemas.py` — extract `LoginRequest`
3. Create `auth/helpers.py` — extract the three helper functions
4. Rewrite `auth/router.py` to import from the new files; remove extracted code
5. Update `auth/__init__.py` to still export `router` and `get_current_user`

**Relevant Context:**
- [`backend/api/auth/router.py`](backend/api/auth/router.py) — full source

**Status:** `[x] done`

---

### Sub-Task 3 — Refactor `workspaces/` package

**Intent:** Extract the one helper function into `api/common/utils.py` (it is just `_workspace_from_doc` = `model_from_doc`); `router.py` becomes pure handlers.

**Expected Outcomes:**
- `workspaces/router.py` uses `model_from_doc` from `api/common/utils.py` instead of its own `_workspace_from_doc`
- No other files needed in this package

**Todo List:**
1. Replace `_workspace_from_doc` call sites in `workspaces/router.py` with the shared `model_from_doc(doc, Workspace)` from `api/common/utils.py`
2. Remove the private function definition

**Relevant Context:**
- [`backend/api/workspaces/router.py`](backend/api/workspaces/router.py)
- `api/common/utils.py` (created in Sub-Task 1)

**Status:** `[x] done`

---

### Sub-Task 4 — Create `configurations/` domain package

**Intent:** Merge `categories/`, `env_config/`, and `llm_configs/` into a single `configurations/` package with proper file separation.

**Expected Outcomes:**
- `configurations/router.py`: All route handlers from the three merged packages
- `configurations/helpers.py`: `_llm_config_from_doc`, `_get_workspace` (uses `model_from_doc` from common)
- `configurations/__init__.py`: Exports `router`
- Old `categories/`, `env_config/`, `llm_configs/` packages deleted
- `api/__init__.py` updated: replaces 3 imports with 1

**Todo List:**
1. Create `backend/api/configurations/` directory with `__init__.py`
2. Create `configurations/helpers.py` with `_llm_config_from_doc` and `_get_workspace`
3. Create `configurations/router.py` combining all route handlers from the 3 packages (exact same handler code, same prefixes)
4. Delete `categories/`, `env_config/`, `llm_configs/` packages
5. Update `api/__init__.py` to import from `api.configurations`

**Relevant Context:**
- [`backend/api/categories/router.py`](backend/api/categories/router.py)
- [`backend/api/env_config/router.py`](backend/api/env_config/router.py)
- [`backend/api/llm_configs/router.py`](backend/api/llm_configs/router.py)

**Status:** `[x] done`

---

### Sub-Task 5 — Create `resources/` domain package

**Intent:** Merge `tools/`, `agents/`, and `orchestrations/` into `resources/` with proper separation: route handlers in `router.py`, utilities in `helpers.py`, complex execution logic in `service.py`.

**Expected Outcomes:**
- `resources/router.py`: All CRUD route handlers (tools, agents, orchestrations); imports from helpers + service
- `resources/helpers.py`: All `_*_from_doc` converters (use `model_from_doc` from common), `_validate_collaborators`, `_build_agent_read_payload`, `_load_agent_*`, `_mask_tool_secrets`, `_resolve_provider_model`, `_apply_llm_credentials`
- `resources/service.py`: `execute_single_agent`, `select_tools_for_prompt`, `build_mcp_client_for_tools` (the complex SSE generator and tool selection logic from `agents/router.py`)
- `resources/__init__.py`: Exports `router`
- Old `tools/`, `agents/`, `orchestrations/` packages deleted
- `api/__init__.py` updated

**Todo List:**
1. Create `backend/api/resources/` directory with `__init__.py`
2. Create `resources/helpers.py` — extract all helper/utility functions from the three old router files; replace private `_*_from_doc` calls with `model_from_doc` from common
3. Create `resources/service.py` — extract `_execute_single_agent`, `_select_tools_for_prompt`, `_build_mcp_client_for_tools` from agents router; these become module-level async functions
4. Create `resources/router.py` — route handlers only; imports from helpers.py, service.py, api/common/utils.py
5. Delete `tools/`, `agents/`, `orchestrations/` packages
6. Update `api/__init__.py`

**Relevant Context:**
- [`backend/api/agents/router.py`](backend/api/agents/router.py) — ~1350 lines; bulk goes to helpers + service
- [`backend/api/tools/router.py`](backend/api/tools/router.py)
- [`backend/api/orchestrations/router.py`](backend/api/orchestrations/router.py)

**Status:** `[x] done`

---

### Sub-Task 6 — Create `workspace_ops/` domain package

**Intent:** Merge `workspace_cloning/` and `workspace_environment/` into `workspace_ops/` with proper separation.

**Expected Outcomes:**
- `workspace_ops/schemas.py`: CloneBatchRequest, CloneSingleRequest, CloneResult, CloneWorkflowResourcesRequest, EnvironmentActionResponse
- `workspace_ops/helpers.py`: `_resolve_source_workspace`, `_get_docker_service`, `get_docker_service`
- `workspace_ops/service.py`: `_clone_tool`, `_clone_agent` (async DB mutation logic)
- `workspace_ops/router.py`: All route handlers only
- Old packages deleted; `api/__init__.py` updated

**Todo List:**
1. Create `backend/api/workspace_ops/` with `__init__.py`
2. Create `workspace_ops/schemas.py` — extract all Pydantic models from both router files
3. Create `workspace_ops/helpers.py` — extract utility functions
4. Create `workspace_ops/service.py` — extract `_clone_tool`, `_clone_agent`
5. Create `workspace_ops/router.py` — handlers only
6. Delete `workspace_cloning/`, `workspace_environment/` packages
7. Update `api/__init__.py`

**Relevant Context:**
- [`backend/api/workspace_cloning/router.py`](backend/api/workspace_cloning/router.py)
- [`backend/api/workspace_environment/router.py`](backend/api/workspace_environment/router.py)

**Status:** `[x] done`

---

### Sub-Task 7 — Create `execution/` domain package

**Intent:** Merge `execute/` (orchestration SSE) and `neural_router/` (semantic predict) into `execution/`. Both are invocation endpoints — one executes an orchestration, the other retrieves relevant tools. `_sse_event` already lives in `api/common/utils.py` after Sub-Task 1.

**Expected Outcomes:**
- `execution/schemas.py`: `ExecuteRequest`
- `execution/helpers.py`: `_get_redis_or_none`
- `execution/router.py`: `execute_orchestration` + `router_predict` handlers; uses `sse_event` from `api/common/utils.py`
- Old `execute/`, `neural_router/` packages deleted; `api/__init__.py` updated

**Todo List:**
1. Create `backend/api/execution/` with `__init__.py`
2. Create `execution/schemas.py` — extract `ExecuteRequest` from execute/router.py
3. Create `execution/helpers.py` — extract `_get_redis_or_none` from neural_router/router.py
4. Create `execution/router.py` — combine both sets of route handlers; use `sse_event` from common
5. Delete `execute/`, `neural_router/` packages
6. Update `api/__init__.py`

**Relevant Context:**
- [`backend/api/execute/router.py`](backend/api/execute/router.py)
- [`backend/api/neural_router/router.py`](backend/api/neural_router/router.py)

**Status:** `[x] done`

---

### Sub-Task 8 — Create `neural_router_pipeline/` domain package

**Intent:** Merge `workflow/`, `data/`, `datasets/`, `model_registry/`, and `scenarios/` into `neural_router_pipeline/`. All five deal with the 3-phase NTR pipeline (generate → train → run), pipeline artifacts, and standalone agent scenario execution.

**Expected Outcomes:**
- `neural_router_pipeline/schemas.py`: GenerateConfig, TrainConfig, RunConfig, EvaluateConfig, ArchiveModelRequest, ArchiveDatasetRequest, LoadDatasetRequest, SyntheticDataUpdate, AgentExecuteRequest (standalone)
- `neural_router_pipeline/helpers.py`: `_apply_dict_to_obj`, `_update_global_config`, `_ensure_run_artifacts_downloaded`
- `neural_router_pipeline/router.py`: All route handlers from the 5 old packages
- Old 5 packages deleted; `api/__init__.py` updated to 1 import

**Todo List:**
1. Create `backend/api/neural_router_pipeline/` with `__init__.py`
2. Create `neural_router_pipeline/schemas.py` — extract all Pydantic request models from the 5 router files
3. Create `neural_router_pipeline/helpers.py` — extract helper functions from workflow/router.py
4. Create `neural_router_pipeline/router.py` — combine all route handlers from the 5 old packages
5. Delete `workflow/`, `data/`, `datasets/`, `model_registry/`, `scenarios/` packages
6. Update `api/__init__.py` — 5 imports replaced with 1

**Relevant Context:**
- [`backend/api/workflow/router.py`](backend/api/workflow/router.py) — ~750 lines
- [`backend/api/model_registry/router.py`](backend/api/model_registry/router.py)
- [`backend/api/scenarios/router.py`](backend/api/scenarios/router.py)
- `backend/api/data/router.py`
- `backend/api/datasets/router.py`

**Status:** `[x] done`

---

### Sub-Task 9 — Update `api/__init__.py` and Smoke-Test

**Intent:** Update the router registry so `ALL_ROUTERS` reflects the new 7-package structure, then verify the application starts without errors and all endpoints are present.

**Expected Outcomes:**
- `api/__init__.py` imports 7 routers (was 17)
- `uvicorn main:app --reload` starts with no import errors
- All 69 previously registered routes are still registered (exact same set)
- `GET /api/categories`, `POST /api/router/predict`, `POST /api/orchestrator/{id}/execute`, `GET /api/generate` all resolve correctly

**Todo List:**
1. Rewrite `api/__init__.py` with 7 imports + updated `ALL_ROUTERS`
2. Start backend: `cd backend && venv/bin/uvicorn main:app --reload`
3. Run import validation: `venv/bin/python3 -c "from api import ALL_ROUTERS; from main import app; print(len([r for r in app.routes if hasattr(r,'path')]), 'routes')"` — must print 69
4. Spot-check all previously verified endpoints are still present
5. Fix any import errors found

**Relevant Context:**
- [`backend/api/__init__.py`](backend/api/__init__.py) — current 17-router registry
- [`backend/main.py`](backend/main.py)

**Status:** `[x] done` — 10 routers registered, 69 routes verified, all spot-check endpoints present

---

## Implementation Order

```
Sub-Task 1          →  Sub-Tasks 2–8 (parallel order)                    →  Sub-Task 9
Create common/          2: auth/        5: resources/     7: execution/      Smoke-test
                        3: workspaces/  6: workspace_ops/ 8: pipeline/
                        4: configs/
```

Sub-Tasks 2–8 are independent of each other and can be done in any order. Sub-Task 1 must be done first (common utilities needed by everything). Sub-Task 9 must be done last.

---

## Files NOT Changed

| File | Reason |
|---|---|
| `backend/db/` | Already well-structured |
| `backend/services/` | Infrastructure services unchanged |
| `backend/tool_router/` | Already cleaned up in v1 refactor |
| `backend/main.py` | Only `ALL_ROUTERS` import; unchanged |
| `frontend/` | Zero frontend impact |
| All API endpoint URLs | Must remain identical |
| All business logic | No logic changes |

---

## Rename Reference (v2 additions)

| Removed packages (17) | Replaced by (7) |
|---|---|
| `auth/` | `auth/` (refactored internally) |
| `workspaces/` | `workspaces/` (cleaned up) |
| `categories/` + `env_config/` + `llm_configs/` | `configurations/` |
| `tools/` + `agents/` + `orchestrations/` | `resources/` |
| `workspace_cloning/` + `workspace_environment/` | `workspace_ops/` |
| `execute/` + `neural_router/` | `execution/` |
| `workflow/` + `data/` + `datasets/` + `model_registry/` + `scenarios/` | `neural_router_pipeline/` |
