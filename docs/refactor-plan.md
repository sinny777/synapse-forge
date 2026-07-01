# SynapseForge Backend & Frontend Refactor Plan

## Top-Level Overview

**Goal:** Refactor the `backend/` package structure to follow Python/FastAPI best practices — separating concerns into dedicated sub-packages — without touching any business logic or breaking any existing functionality. Minor cleanup also covers the frontend and docs folder.

**Scope:**
- Backend `api/` restructured into feature-based sub-packages with proper separation of routers, schemas, and dependencies
- `db/` layer stays intact (already well-structured)
- `services/` layer stays intact (already well-structured)
- `main.py` import paths updated to match new structure
- Frontend: no structural changes needed (already follows Angular conventions), but minor cleanup of an unused test file
- Docs: remove stale/deleted docs, keep only valid ones
- No logic changes, no renames of modules that affect external consumers (API URLs stay identical)

**Non-goals:**
- Rewriting business logic
- Changing API endpoint URLs
- Modifying the `db/` or `services/` layers (already correctly structured)
- Frontend component or service refactoring

---

## Current Problems

1. **`api/` is a flat dumping ground** — 20 files mixing routers, a utilities/dependencies file, and no grouping by domain or responsibility
2. **`api/models.py` name clash** — there's both `api/models.py` (Model archival router) and `db/models.py` (Pydantic domain models), which is confusing
3. **`api/router.py` name clash** — there's `api/router.py` (semantic tool retrieval endpoint) but `router` is also a common FastAPI variable name
4. **Stale docs** — `docs/DYNAMIC_LANGGRAPH_ARCHITECTURE.md` is the moved copy of the deleted `backend/services/DYNAMIC_LANGGRAPH_ARCHITECTURE.md`; keep it but verify it's valid
5. **`frontend/src/app/test_tabs.ts`** — a stray test file sitting in the app root, not part of any module

---

## Proposed Backend Package Structure

```
backend/
├── main.py                        # FastAPI entry point (updated imports only)
├── requirements.txt
├── .env.example
│
├── api/                           # HTTP layer — routers only
│   ├── __init__.py
│   ├── dependencies.py            # Shared DI: get_current_user, require_workspace_access
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/auth.py
│   │
│   ├── workspaces/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/workspaces.py
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/tools.py
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/agents.py
│   │
│   ├── orchestrations/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/orchestrations.py
│   │
│   ├── llm_configs/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/llm_configs.py
│   │
│   ├── router_predict/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/router.py (renamed package to avoid clash)
│   │
│   ├── workflow/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/workflow.py
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/data.py
│   │
│   ├── model_registry/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/models.py (renamed to avoid clash with db/models.py)
│   │
│   ├── datasets/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/datasets.py
│   │
│   ├── scenarios/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/scenarios.py
│   │
│   ├── execute/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/execute.py
│   │
│   ├── workspace_cloning/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/workspace_cloning.py
│   │
│   ├── workspace_environment/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/workspace_environment.py
│   │
│   ├── env_config/
│   │   ├── __init__.py
│   │   └── router.py              # ← was api/env_config.py
│   │
│   └── categories/
│       ├── __init__.py
│       └── router.py              # ← was api/categories.py
│
├── db/                            # Unchanged
│   ├── engine.py
│   ├── models.py
│   ├── schemas.py
│   └── redis_pool.py
│
├── services/                      # Unchanged
│   ├── embedding_service.py
│   ├── router_service.py
│   ├── mcp_service.py
│   ├── artifact_manager.py
│   ├── ibm_cos_service.py
│   ├── conversation_service.py
│   ├── langgraph_dynamic_agent_executor.py
│   └── workspace_docker_service.py
│
├── tool_router/                   # Unchanged (standalone engine)
│
└── setup/                         # Unchanged
```

---

## Sub-Tasks

---

### Sub-Task 1 — Remove Stale Files

**Intent:** Delete files that are no longer needed to keep the repository clean before the refactor begins.

**Expected Outcomes:**
- `frontend/src/app/test_tabs.ts` is removed
- No broken references remain after removal

**Todo List:**
1. Delete `frontend/src/app/test_tabs.ts`
2. Verify no Angular module or component imports `test_tabs.ts`

**Relevant Context:**
- [`frontend/src/app/test_tabs.ts`](frontend/src/app/test_tabs.ts) — stray test utility file not imported by any module

**Status:** `[ ] pending`

---

### Sub-Task 2 — Create Feature Sub-Packages in `api/`

**Intent:** Move each flat router file in `api/` into its own feature sub-package (`api/<feature>/router.py`), while preserving every line of logic exactly as-is. The two naming-conflict files (`api/models.py` → `api/model_registry/` and `api/router.py` → `api/router_predict/`) get renamed to avoid shadowing `db/models.py` and the FastAPI `router` variable convention.

**Expected Outcomes:**
- Every file previously in `backend/api/*.py` (except `__init__.py` and `dependencies.py`) now lives at `backend/api/<feature>/router.py`
- Each sub-package has its own `__init__.py` that exports the `APIRouter` instance as `router` (e.g. `from api.auth import router as auth_router`)
- `api/dependencies.py` stays at the top level (shared across all features)
- `api/__init__.py` is updated to reflect the new structure

**Todo List:**
1. For each feature listed below, create the directory `api/<feature>/`, add `__init__.py`, and create `router.py` by copying the existing flat file content verbatim:
   - `api/auth/router.py` ← `api/auth.py`
   - `api/workspaces/router.py` ← `api/workspaces.py`
   - `api/tools/router.py` ← `api/tools.py`
   - `api/agents/router.py` ← `api/agents.py`
   - `api/orchestrations/router.py` ← `api/orchestrations.py`
   - `api/llm_configs/router.py` ← `api/llm_configs.py`
   - `api/router_predict/router.py` ← `api/router.py`
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
2. Each `api/<feature>/__init__.py` should export the APIRouter: `from .router import router`
3. Verify all intra-api imports (e.g. any file that imports `from api.dependencies import ...`) are updated to the new path (dependencies.py stays at `api/dependencies.py`)
4. Delete the original flat `api/*.py` router files after the new structure is confirmed correct

**Relevant Context:**
- [`backend/api/`](backend/api/) — all current flat router files
- [`backend/api/dependencies.py`](backend/api/dependencies.py) — shared DI helpers, stays at top-level of `api/`
- [`backend/main.py`](backend/main.py) — imports all routers; will be updated in Sub-Task 3

**Status:** `[ ] pending`

---

### Sub-Task 3 — Update `main.py` Import Paths

**Intent:** Update `backend/main.py` to import routers from the new sub-package paths. No other changes to `main.py`.

**Expected Outcomes:**
- `main.py` imports all routers from `api.<feature>` instead of flat `api.<filename>`
- The application starts cleanly with `uvicorn main:app --reload` — no import errors

**Todo List:**
1. Open `backend/main.py` and identify every `from api.<x> import ...` statement
2. Replace each import with the new path (e.g. `from api.auth import router as auth_router` → `from api.auth import router as auth_router` — path stays same since `__init__.py` re-exports; verify each one)
3. Specifically handle the two renamed packages:
   - Old: `from api.router import router as ...` → New: `from api.router_predict import router as router_predict_router`
   - Old: `from api.models import router as ...` → New: `from api.model_registry import router as model_registry_router`
4. Confirm router variable names and `app.include_router()` calls remain semantically identical

**Relevant Context:**
- [`backend/main.py`](backend/main.py) — entry point with all `app.include_router()` calls

**Status:** `[ ] pending`

---

### Sub-Task 4 — Fix Intra-Package Imports Inside Routers

**Intent:** Any router file that imports from another `api/` module (e.g. `from api.dependencies import require_workspace_access`) must have its imports verified after the move. Since `dependencies.py` stays at `api/dependencies.py`, these imports should require no changes — but each router file must be checked.

**Expected Outcomes:**
- All router files import `dependencies` correctly as `from api.dependencies import ...`
- No router file references another router file directly (there should be none, but verify)
- All imports from `db.*` and `services.*` are unchanged

**Todo List:**
1. `grep` all new `api/<feature>/router.py` files for any `from api.` imports
2. Confirm each resolves correctly relative to the new file location
3. Fix any broken relative/absolute import paths found

**Relevant Context:**
- [`backend/api/dependencies.py`](backend/api/dependencies.py) — the only shared `api/` module imported by other routers

**Status:** `[ ] pending`

---

### Sub-Task 5 — Smoke-Test the Refactored Application

**Intent:** Verify the application starts without errors and all endpoints are reachable after the structural changes.

**Expected Outcomes:**
- `uvicorn main:app --reload` starts without any `ImportError` or `ModuleNotFoundError`
- FastAPI's OpenAPI docs at `http://localhost:8000/docs` lists all expected endpoints
- At minimum, `GET /api/workspaces` and `GET /api/categories` return HTTP 200 (or 401 for auth-protected routes)

**Todo List:**
1. Start the backend with `cd backend && uvicorn main:app --reload`
2. Check the startup logs for any import errors
3. Hit `http://localhost:8000/docs` and confirm all routers are registered
4. Run a quick `curl http://localhost:8000/api/categories` — should return category data
5. If any errors appear, trace the import chain and fix

**Relevant Context:**
- [`backend/main.py`](backend/main.py) — entry point
- `backend/.env.example` — required env vars for DB connections

**Status:** `[ ] pending`

---

### Sub-Task 6 — Update `api/__init__.py`

**Intent:** Update the top-level `api/__init__.py` to document the new package structure and optionally aggregate all routers for easy import in `main.py`.

**Expected Outcomes:**
- `api/__init__.py` reflects the new sub-package layout with brief docstring or router aggregation list
- Optionally: `api/__init__.py` exports a `all_routers` list that `main.py` can iterate over (reduces boilerplate)

**Todo List:**
1. Read the current `api/__init__.py` content
2. Update it to document the new feature sub-package structure
3. Optionally refactor `main.py` to use a router list pattern if it reduces import clutter

**Relevant Context:**
- [`backend/api/__init__.py`](backend/api/__init__.py) — current package-level docstring

**Status:** `[ ] pending`

---

## Implementation Order

```
Sub-Task 1  →  Sub-Task 2  →  Sub-Task 3  →  Sub-Task 4  →  Sub-Task 5  →  Sub-Task 6
(clean up)    (move files)    (fix main.py)   (fix imports)   (smoke test)   (docs)
```

Sub-Tasks 2, 3, and 4 are tightly coupled and should be done in order. Sub-Task 1 is independent and can run first. Sub-Task 5 requires all prior steps.

---

## Files NOT Changed

| File/Folder | Reason |
|---|---|
| `backend/db/` | Already well-structured with clear separation (engine, models, schemas, redis) |
| `backend/services/` | Already well-structured (one service per file, clear naming) |
| `backend/tool_router/` | Standalone sub-application, not part of this refactor |
| `backend/setup/` | Database seed scripts, not part of the API layer |
| `frontend/src/app/` | Angular structure already follows conventions; no structural changes needed |
| `docs/DYNAMIC_LANGGRAPH_ARCHITECTURE.md` | Valid moved copy — keep |
| All API endpoint URLs | Must not change (zero consumer impact) |
| All business logic | Must not change |
