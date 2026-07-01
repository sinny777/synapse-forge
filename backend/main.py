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
import os
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

from api import ALL_ROUTERS

for router in ALL_ROUTERS:
    app.include_router(router)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
