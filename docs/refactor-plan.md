# SynapseForge Backend & Frontend Refactor Plan

## Top-Level Overview

**Goal:** Refactor the `backend/` package structure to follow Python/FastAPI best practices — separating concerns into feature-based sub-packages — without touching any business logic or breaking any existing functionality. Minor cleanup also covers the frontend.

**Scope:**
- `backend/api/` — restructured into feature-based sub-packages; `main.py` simplified using a router registry pattern
- `backend/tool_router/` — dead backup files removed; `__init__.py` populated; `LiteLLMChatOpenAI` adapter extracted; import style standardised to absolute
- `frontend/src/app/test_tabs.ts` — stray file removed
- No changes to `backend/db/`, `backend/services/`, `backend/setup/`, or any frontend components/services

**Non-goals:**
- Rewriting business logic
- Changing API endpoint URLs
- Modifying the `db/` or `services/` layers (already correctly structured)
- Frontend component or service refactoring
- Adding tests or fixing the `status_tracker` thread-safety issue (separate concern)

---

## Current Problems

### `api/` Issues
1. **Flat dumping ground** — 20 files with no domain grouping
2. **`api/models.py` name clash** — shadows `db/models.py` (Pydantic domain models)
3. **`api/router.py` name clash** — "router" is also the common FastAPI variable name used in every file
4. **`main.py` is cluttered** — 20+ individual import lines, one per router file; no aggregation

### `tool_router/` Issues
5. **Dead backup files** — `agent_service_hybrid.py` and `agent_service_real_backup.py` are stale copies never imported
6. **`mock_mcp_server.py` misplaced** — standalone test server sitting at package root
7. **Empty `__init__.py`** — nothing is exported; external callers import individual submodules
8. **`LiteLLMChatOpenAI` defined inline** — 23-line custom adapter defined inside `executors/langgraph_executor.py`; belongs in a shared location
9. **Mixed import styles** — some files use `from tool_router.X import Y` (absolute), others use `from .X import Y` (relative); should be consistent

### Frontend
10. **`test_tabs.ts` stray file** — sits in the Angular app root, not imported by any module

---

## Proposed Package Structure

### `api/` — After Refactor

```
backend/api/
├── __init__.py          ← exports ALL_ROUTERS list for main.py
├── dependencies.py      ← stays at top-level (shared DI helpers)
│
├── auth/
│   ├── __init__.py      ← from .router import router
│   └── router.py        ← was api/auth.py
│
├── workspaces/
│   ├── __init__.py
│   └── router.py        ← was api/workspaces.py
│
├── tools/
│   ├── __init__.py
│   └── router.py        ← was api/tools.py
│
├── agents/
│   ├── __init__.py
│   └── router.py        ← was api/agents.py
│
├── orchestrations/
│   ├── __init__.py
│   └── router.py        ← was api/orchestrations.py
│
├── llm_configs/
│   ├── __init__.py
│   └── router.py        ← was api/llm_configs.py
│
├── neural_router/
│   ├── __init__.py
│   └── router.py        ← was api/router.py  [renamed: "neural_router" describes function]
│
├── workflow/
│   ├── __init__.py
│   └── router.py        ← was api/workflow.py
│
├── data/
│   ├── __init__.py
│   └── router.py        ← was api/data.py
│
├── model_registry/
│   ├── __init__.py
│   └── router.py        ← was api/models.py  [renamed: avoids shadow with db/models.py]
│
├── datasets/
│   ├── __init__.py
│   └── router.py        ← was api/datasets.py
│
├── scenarios/
│   ├── __init__.py
│   └── router.py        ← was api/scenarios.py
│
├── execute/
│   ├── __init__.py
│   └── router.py        ← was api/execute.py
│
├── workspace_cloning/
│   ├── __init__.py
│   └── router.py        ← was api/workspace_cloning.py
│
├── workspace_environment/
│   ├── __init__.py
│   └── router.py        ← was api/workspace_environment.py
│
├── env_config/
│   ├── __init__.py
│   └── router.py        ← was api/env_config.py
│
└── categories/
    ├── __init__.py
    └── router.py        ← was api/categories.py
```

**Naming rationale for the two renames:**
- `api/router.py` → `api/neural_router/` — "neural router" precisely describes this endpoint's purpose (semantic/neural tool retrieval) and avoids the `router` variable name clash
- `api/models.py` → `api/model_registry/` — "model registry" describes the archival/versioning function and avoids shadowing `db/models.py`

### `api/__init__.py` — Router Registry Pattern

`api/__init__.py` will export a single `ALL_ROUTERS` list so `main.py` can register all routes in one loop:

```python
# api/__init__.py
from api.auth import router as auth_router
from api.workspaces import router as workspaces_router
# ... all 17 routers ...

ALL_ROUTERS = [
    auth_router,
    workspaces_router,
    # ...
]
```

```python
# main.py (simplified)
from api import ALL_ROUTERS

for router in ALL_ROUTERS:
    app.include_router(router)
```

### `tool_router/` — After Cleanup

```
backend/tool_router/
├── __init__.py             ← exports key public symbols (config, MCPClient, AgentOrchestrator, etc.)
│
├── config.py               ← unchanged
├── agent_service.py        ← unchanged
├── generator.py            ← unchanged
├── trainer.py              ← unchanged
├── runtime.py              ← unchanged
├── mcp_client.py           ← unchanged
├── status_tracker.py       ← unchanged
│
├── common/
│   ├── __init__.py         ← unchanged
│   ├── events.py           ← unchanged
│   ├── models.py           ← unchanged
│   ├── mcp_manager.py      ← unchanged
│   └── llm_adapters.py     ← NEW: LiteLLMChatOpenAI extracted from langgraph_executor.py
│
├── executors/
│   ├── __init__.py         ← unchanged
│   ├── base_executor.py    ← unchanged
│   ├── mock_executor.py    ← unchanged
│   ├── langgraph_executor.py  ← import LiteLLMChatOpenAI from common.llm_adapters
│   └── beeai_executor.py   ← unchanged
│
└── utils/
    ├── __init__.py         ← unchanged
    ├── archive.py          ← unchanged
    └── mock_mcp_server.py  ← MOVED from package root (test utility, not production)

# DELETED:
# tool_router/agent_service_hybrid.py   (backup, never imported)
# tool_router/agent_service_real_backup.py (backup, never imported)
```

---

## Sub-Tasks

---

### Sub-Task 1 — Remove Stale Files

**Intent:** Delete dead backup files and the stray frontend test file before the refactor begins.

**Expected Outcomes:**
- `backend/tool_router/agent_service_hybrid.py` deleted
- `backend/tool_router/agent_service_real_backup.py` deleted
- `frontend/src/app/test_tabs.ts` deleted
- No remaining imports of these files anywhere in the codebase

**Todo List:**
1. `grep` the codebase to confirm none of the three files are imported anywhere
2. Delete `backend/tool_router/agent_service_hybrid.py`
3. Delete `backend/tool_router/agent_service_real_backup.py`
4. Delete `frontend/src/app/test_tabs.ts`

**Relevant Context:**
- [`backend/tool_router/agent_service_hybrid.py`](backend/tool_router/agent_service_hybrid.py)
- [`backend/tool_router/agent_service_real_backup.py`](backend/tool_router/agent_service_real_backup.py)
- [`frontend/src/app/test_tabs.ts`](frontend/src/app/test_tabs.ts)

**Status:** `[x] done`

---

### Sub-Task 2 — Restructure `api/` into Feature Sub-Packages

**Intent:** Move each flat router file in `api/` into its own feature sub-package (`api/<feature>/router.py`), preserving every line of logic exactly as-is. Two files get descriptive renames to eliminate naming conflicts.

**Expected Outcomes:**
- Every file previously in `backend/api/*.py` (except `__init__.py` and `dependencies.py`) lives at `backend/api/<feature>/router.py`
- Each sub-package `__init__.py` re-exports the router: `from .router import router`
- `api/dependencies.py` remains at the top level (shared across all features)
- Original flat `api/*.py` router files are deleted

**Todo List:**
1. For each feature below, create `api/<feature>/`, add `__init__.py` (with `from .router import router`), and create `router.py` with the exact content of the original file:
   - `api/auth/router.py` ← `api/auth.py`
   - `api/workspaces/router.py` ← `api/workspaces.py`
   - `api/tools/router.py` ← `api/tools.py`
   - `api/agents/router.py` ← `api/agents.py`
   - `api/orchestrations/router.py` ← `api/orchestrations.py`
   - `api/llm_configs/router.py` ← `api/llm_configs.py`
   - `api/neural_router/router.py` ← `api/router.py`
   - `api/workflow/router.py` ← `api/workflow.py`
   - `api/data/router.py` ← `api/data.py`
   - `api/model_registry/router.py` ← `api/models.py`
   - `api/datasets/router.py` ← `api/datasets.py`
   - `api/scenarios/router.py` ← `api/scenarios.py`
   - `api/execute/router.py` ← `api/execute.py`
   - `api/workspace_cloning/router.py` ← `api/workspace_cloning.py`
   - `api/workspace_environment/router.py` ← `api/workspace_environment.py`
   - `api/env_config/router.py` ← `api/env_config.py`
   - `api/categories/router.py` ← `api/categories.py`
2. Delete all original flat `api/*.py` router files (keep `__init__.py` and `dependencies.py`)
3. Verify all internal imports within each `router.py` are correct: `from api.dependencies import ...` still resolves (path unchanged)

**Relevant Context:**
- [`backend/api/`](backend/api/) — all current flat router files
- [`backend/api/dependencies.py`](backend/api/dependencies.py) — shared DI; stays at `api/dependencies.py`

**Status:** `[x] done` — 17 routers loaded, 69 routes registered, all spot-checks passed

---

### Sub-Task 3 — Update `api/__init__.py` with Router Registry & Simplify `main.py`

**Intent:** Populate `api/__init__.py` with an `ALL_ROUTERS` list so `main.py` can register every route in a single loop, eliminating the 20+ individual import lines.

**Expected Outcomes:**
- `api/__init__.py` imports all 17 routers and exports `ALL_ROUTERS`
- `backend/main.py` replaces individual `include_router()` calls with a single `for router in ALL_ROUTERS` loop
- Application starts cleanly; all endpoints appear in `/docs`

**Todo List:**
1. Write `api/__init__.py`:
   - Import each router from its sub-package: `from api.auth import router as auth_router`, etc.
   - Define `ALL_ROUTERS: list[APIRouter] = [auth_router, workspaces_router, ...]`
2. Update `backend/main.py`:
   - Replace all individual `from api.X import router as X_router` import lines with `from api import ALL_ROUTERS`
   - Replace all `app.include_router(X_router)` calls with `for r in ALL_ROUTERS: app.include_router(r)`
   - Keep all other `main.py` content (lifespan, middleware, etc.) unchanged

**Relevant Context:**
- [`backend/main.py`](backend/main.py) — current entry point with 20+ router imports
- [`backend/api/__init__.py`](backend/api/__init__.py) — will become the router registry

**Status:** `[x] done`

---

### Sub-Task 4 — Clean Up `tool_router/`

**Intent:** Remove dead backup files, move `mock_mcp_server.py` to `utils/`, extract the inline `LiteLLMChatOpenAI` adapter to `common/llm_adapters.py`, and populate `tool_router/__init__.py` with public exports.

**Expected Outcomes:**
- No backup/dead files remain in `tool_router/`
- `mock_mcp_server.py` lives at `tool_router/utils/mock_mcp_server.py`
- `LiteLLMChatOpenAI` lives at `tool_router/common/llm_adapters.py`; `langgraph_executor.py` imports from there
- `tool_router/__init__.py` exports the key public API: `config`, `MCPClient`, `ToolSchema`, `agent_orchestrator`, `update_status`

**Todo List:**
1. Create `tool_router/common/llm_adapters.py`:
   - Extract the `LiteLLMChatOpenAI` class definition verbatim from `executors/langgraph_executor.py`
2. Update `tool_router/executors/langgraph_executor.py`:
   - Replace the inline class definition with `from tool_router.common.llm_adapters import LiteLLMChatOpenAI`
3. Move `tool_router/mock_mcp_server.py` to `tool_router/utils/mock_mcp_server.py`
4. Update `tool_router/__init__.py` to export public symbols:
   ```python
   from tool_router.config import config
   from tool_router.mcp_client import MCPClient, ToolSchema
   from tool_router.agent_service import agent_orchestrator
   from tool_router.status_tracker import update_status
   ```
5. Verify no file imports `mock_mcp_server` from the old path; update any references found
6. Verify the `langgraph_executor.py` change doesn't break `LangGraphExecutor` behaviour (import-only change)

**Relevant Context:**
- [`backend/tool_router/executors/langgraph_executor.py`](backend/tool_router/executors/langgraph_executor.py) — contains inline `LiteLLMChatOpenAI`
- [`backend/tool_router/__init__.py`](backend/tool_router/__init__.py) — currently empty
- [`backend/tool_router/mock_mcp_server.py`](backend/tool_router/mock_mcp_server.py) — misplaced test utility

**Status:** `[x] done`

---

### Sub-Task 5 — Smoke-Test the Refactored Application

**Intent:** Verify the application starts without errors and all endpoints are reachable after all structural changes.

**Expected Outcomes:**
- `uvicorn main:app --reload` starts with no `ImportError` or `ModuleNotFoundError`
- FastAPI OpenAPI docs at `http://localhost:8000/docs` lists all expected endpoints
- `GET /api/categories` returns data (no auth required)
- `GET /api/workspaces` returns 401 (auth-required endpoint — confirms router is registered and auth works)

**Todo List:**
1. Start the backend: `cd backend && uvicorn main:app --reload`
2. Check startup logs for any import errors
3. Open `http://localhost:8000/docs` — confirm all routers are present
4. `curl http://localhost:8000/api/categories` — expect category data (200 OK)
5. `curl http://localhost:8000/api/workspaces` — expect 401 (not 404)
6. Fix any errors found by tracing the import chain

**Relevant Context:**
- [`backend/main.py`](backend/main.py)
- [`backend/.env.example`](backend/.env.example) — required env vars

**Status:** `[x] done` — 17 routers / 69 routes registered; all 11 spot-check endpoints confirmed present

---

## Implementation Order

```
Sub-Task 1         →  Sub-Task 2         →  Sub-Task 3         →  Sub-Task 4         →  Sub-Task 5
Remove dead files     Restructure api/      Simplify main.py      Clean tool_router/    Smoke test
```

Sub-Tasks 2 and 3 are tightly coupled (do in sequence). Sub-Task 1 and Sub-Task 4 are independent of each other but should run after Sub-Task 1 (clean slate first). Sub-Task 5 requires all prior steps.

---

## Files NOT Changed

| File/Folder | Reason |
|---|---|
| `backend/db/` | Already well-structured: engine, models, schemas, redis each in their own file |
| `backend/services/` | Already well-structured: one service per file, clear naming |
| `backend/setup/` | DB seed scripts, not part of the API layer |
| `frontend/src/app/` | Angular structure already follows conventions |
| `docs/DYNAMIC_LANGGRAPH_ARCHITECTURE.md` | Valid architecture doc — keep |
| All API endpoint URLs | Must not change (zero consumer impact) |
| All business logic | Must not change |

---

## Rename Reference

| Old path | New path | Reason |
|---|---|---|
| `api/router.py` | `api/neural_router/router.py` | Describes function (neural/semantic tool retrieval); eliminates `router` name clash |
| `api/models.py` | `api/model_registry/router.py` | Describes function (model archival/versioning); eliminates shadow with `db/models.py` |
| `tool_router/mock_mcp_server.py` | `tool_router/utils/mock_mcp_server.py` | Test utility belongs with other utilities |
| `LiteLLMChatOpenAI` (inline in langgraph_executor.py) | `tool_router/common/llm_adapters.py` | Shared adapter class extracted to common/ |
