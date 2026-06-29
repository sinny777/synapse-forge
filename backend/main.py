"""
SynapseForge — FastAPI Application Entry Point

This is the thin application shell. All route handlers live in the
``api/`` package.  This file is responsible only for:
  1. Loading environment variables
  2. Configuring logging
  3. Lifespan hooks (DB + Redis init/close)
  4. CORS middleware
  5. Mounting all API routers
"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)
print(f"[Main] Loaded environment from: {env_path}")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("fastapi_app")

# File handler so logs are readable even without a live terminal session
_log_file = Path(__file__).parent / "agent_debug.log"
_fh = logging.FileHandler(_log_file, mode="a", encoding="utf-8")
_fh.setLevel(logging.INFO)
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger().addHandler(_fh)


# ---------------------------------------------------------------------------
# FastAPI Lifespan — initialise & tear down DB + Redis connections
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    - Startup:  connect to MongoDB and Redis.
    - Shutdown: close all connections gracefully.
    """
    from db.engine import init_db, close_db
    from db.redis_pool import init_redis, close_redis

    logger.info("🚀 Starting SynapseForge platform services...")

    # --- Startup ---
    try:
        await init_db()
        logger.info("✅ MongoDB connected")
    except Exception as e:
        logger.warning(f"⚠️  MongoDB not available (running without DB): {e}")

    try:
        await init_redis()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.warning(f"⚠️  Redis not available (running without cache): {e}")

    yield  # Application runs here

    # --- Shutdown ---
    logger.info("🛑 Shutting down platform services...")
    try:
        await close_redis()
    except Exception:
        pass
    try:
        await close_db()
    except Exception:
        pass
    logger.info("👋 All connections closed.")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(title="SynapseForge API", lifespan=lifespan)

import os
secret_key = os.environ.get("SECRET_KEY", "super-secret-key-for-dev")
app.add_middleware(SessionMiddleware, secret_key=secret_key)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Mount all API routers
# ---------------------------------------------------------------------------

# --- Auth ---
from api.auth import router as auth_router

# --- Platform CRUD (Phase 3 & 4) ---
from api.workspaces import router as workspaces_router
from api.tools import router as tools_router
from api.agents import router as agents_router
from api.orchestrations import router as orchestrations_router
from api.router import router as router_predict_router
from api.workspace_cloning import router as cloning_router
from api.workspace_environment import router as environment_router
from api.llm_configs import router as llm_configs_router

from api.categories import router as categories_router

# --- Standalone Workflow Pipeline ---
from api.workflow import router as workflow_router
from api.data import router as data_router
from api.models import router as models_router
from api.datasets import router as datasets_router
from api.env_config import router as env_config_router
from api.scenarios import router as scenarios_router
try:
    from api.execute import router as execute_router
    print("✓ Execute router imported successfully")
except Exception as e:
    print(f"✗ Failed to import execute router: {e}")
    import traceback
    traceback.print_exc()
    execute_router = None

# Platform routes
app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(tools_router)
app.include_router(agents_router)
app.include_router(orchestrations_router)
app.include_router(router_predict_router)
app.include_router(cloning_router)
app.include_router(environment_router)
app.include_router(llm_configs_router)
app.include_router(categories_router)

# Standalone workflow routes
app.include_router(workflow_router)
app.include_router(data_router)
app.include_router(models_router)
app.include_router(datasets_router)
app.include_router(env_config_router)
app.include_router(scenarios_router)
if execute_router is not None:
    app.include_router(execute_router)
    print("✓ Execute router registered")
    # Debug: Print all orchestrator routes
    print("\n=== Registered Orchestrator Routes ===")
    for route in app.routes:
        if hasattr(route, 'path') and 'orchestrator' in route.path:
            methods = getattr(route, 'methods', set())
            print(f"  {methods} {route.path}")
    print("=====================================\n")
else:
    print("✗ Execute router not registered due to import error")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
