"""
NeuralToolRouter — Async SQLAlchemy Engine & Session Management

Uses asyncpg as the async driver for PostgreSQL.
The engine and session factory are created lazily and attached to the
FastAPI app lifespan so connections are properly cleaned up.
"""

import os
import logging
from typing import AsyncGenerator, Annotated

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text
from fastapi import Depends

logger = logging.getLogger("ntr.db")

# ---------------------------------------------------------------------------
# Module-level singletons (populated by init_db / closed by close_db)
# ---------------------------------------------------------------------------
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_database_url() -> str:
    """
    Construct the async database URL from environment variables.

    Expected env vars (with defaults matching docker-compose.yml):
        POSTGRES_USER     (default: ntr_user)
        POSTGRES_PASSWORD (default: ntr_secret_2026)
        POSTGRES_HOST     (default: localhost)
        POSTGRES_PORT     (default: 5432)
        POSTGRES_DB       (default: neural_tool_router)
    """
    user = os.getenv("POSTGRES_USER", "ntr_user")
    password = os.getenv("POSTGRES_PASSWORD", "ntr_secret_2026")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "neural_tool_router")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


# ---------------------------------------------------------------------------
# Lifecycle helpers — call from FastAPI lifespan
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """
    Initialise the async engine + session factory, verify pgvector,
    and sync tables from ORM models.

    Schema sync behaviour (controlled by DB_AUTO_RESET env var):
      - DB_AUTO_RESET=true  → drop + recreate ALL tables if schema drift
                               is detected (dev mode, default).
      - DB_AUTO_RESET=false → only create missing tables; log a warning
                               if existing tables are out of sync.

    ``create_all()`` alone only creates NEW tables — it cannot add/remove
    columns on existing tables.  The drift detection + auto-reset solves
    this for early development without Alembic migrations.
    """
    global _engine, _session_factory

    url = os.getenv("DATABASE_URL") or _build_database_url()
    logger.info("Connecting to PostgreSQL at %s", url.split("@")[-1])

    _engine = create_async_engine(
        url,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_pre_ping=True,  # detect stale connections
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    from db.models import Base  # local import to avoid circular deps

    auto_reset = os.getenv("DB_AUTO_RESET", "true").lower() == "true"

    async with _engine.begin() as conn:
        # Ensure pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector extension verified ✓")

        # Detect schema drift: compare ORM model columns vs live DB columns
        drift = await conn.run_sync(
            lambda sync_conn: _detect_schema_drift(sync_conn, Base)
        )

        if drift:
            if auto_reset:
                logger.warning(
                    "Schema drift detected (%s). DB_AUTO_RESET=true → "
                    "dropping and recreating all tables...", drift
                )
                await conn.run_sync(Base.metadata.drop_all)
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database tables recreated from models ✓")
            else:
                logger.warning(
                    "Schema drift detected (%s). DB_AUTO_RESET=false → "
                    "tables NOT altered. Set DB_AUTO_RESET=true or update "
                    "the schema manually.", drift
                )
                # Still create any brand-new tables
                await conn.run_sync(Base.metadata.create_all)
        else:
            # No drift — just ensure any new tables exist
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables synced ✓")


def _detect_schema_drift(sync_conn, base) -> str | None:
    """
    Compare ORM model columns against the live database schema.
    Returns a human-readable drift description, or None if in sync.

    Checks performed:
      • Missing tables (exist in ORM but not in DB)
      • Missing columns (exist in ORM model but not in DB table)
      • Extra columns (exist in DB table but not in ORM model)
    """
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    diffs = []

    for table_name, table in base.metadata.tables.items():
        if table_name not in existing_tables:
            diffs.append(f"new table '{table_name}'")
            continue

        # Compare columns
        db_columns = {col["name"] for col in inspector.get_columns(table_name)}
        model_columns = {col.name for col in table.columns}

        missing = model_columns - db_columns
        extra = db_columns - model_columns

        if missing:
            diffs.append(f"'{table_name}' missing columns: {missing}")
        if extra:
            diffs.append(f"'{table_name}' extra columns: {extra}")

    return "; ".join(diffs) if diffs else None


async def reset_db() -> None:
    """
    Drop ALL tables and recreate them from scratch.

    ⚠️  DESTRUCTIVE — use only during development.
    Call this instead of init_db() when you want a clean slate.
    """
    global _engine, _session_factory

    if _engine is None:
        await init_db()
        return

    from db.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All tables dropped.")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        logger.info("All tables recreated from models ✓")


async def close_db() -> None:
    """Dispose the engine and release all pooled connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database connections closed.")
        _engine = None
        _session_factory = None


# ---------------------------------------------------------------------------
# Dependency injection helpers
# ---------------------------------------------------------------------------

def get_async_engine() -> AsyncEngine:
    """Return the current async engine (raises if not initialised)."""
    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _engine


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an ``AsyncSession``.

    Usage in a route::

        @app.get("/items")
        async def list_items(session: AsyncSessionDep):
            result = await session.execute(select(Item))
            return result.scalars().all()
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Shorthand type alias for route signatures
AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
