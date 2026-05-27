"""
SynapseForge — Database Reset & Re-seed Script

Drops ALL tables, recreates them from the current ORM models, and seeds
the default workspace with template Agents and Tools.

⚠️  DESTRUCTIVE — intended for rapid prototyping only.
    Does NOT use Alembic migrations.

Usage:
    # From the backend/ directory with venv activated:
    python -m setup.reset_db              # full reset + seed
    python -m setup.reset_db --no-seed    # reset schema only, skip seeding
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure the backend package root is on sys.path and .env is loaded
# ---------------------------------------------------------------------------
_backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_backend_dir / ".env")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from db.models import Base

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("reset_db")


# ═══════════════════════════════════════════════════════════════════════════
# Database URL builder (mirrors db/engine.py)
# ═══════════════════════════════════════════════════════════════════════════

def _build_database_url() -> str:
    user = os.getenv("POSTGRES_USER", "ntr_user")
    password = os.getenv("POSTGRES_PASSWORD", "ntr_secret_2026")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "synapse_forge")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


# ═══════════════════════════════════════════════════════════════════════════
# Core reset logic
# ═══════════════════════════════════════════════════════════════════════════

async def reset_schema() -> None:
    """
    Connect to PostgreSQL, drop ALL tables, ensure pgvector extension,
    and recreate the full schema from SQLAlchemy ORM models.
    """
    url = os.getenv("DATABASE_URL") or _build_database_url()
    logger.info("Connecting to PostgreSQL at %s", url.split("@")[-1])

    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        # 1. Drop all existing tables
        logger.warning("🗑  Dropping ALL tables...")
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("   All tables dropped.")

        # 2. Ensure pgvector extension exists (must happen before create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("   pgvector extension verified ✓")

        # 3. Drop stale enum types that SQLAlchemy won't clean up automatically
        #    (prevents "type already exists" errors on re-creation)
        for enum_name in [
            "workspace_status",
            "tool_type",
            "mcp_transport_type",
            "mcp_server_status",
            "orchestration_framework",
            "architecture_type",
            "llm_provider_enum",
        ]:
            await conn.execute(
                text(f"DROP TYPE IF EXISTS {enum_name} CASCADE")
            )
        logger.info("   Stale enum types cleaned up ✓")

        # 4. Recreate all tables from ORM models
        logger.info("📦 Recreating tables from ORM models...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("   All tables created ✓")

    await engine.dispose()
    logger.info("✅ Schema reset complete!")


# ═══════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════

async def run(skip_seed: bool = False) -> None:
    """Full pipeline: reset schema, then optionally seed default data."""
    await reset_schema()

    if not skip_seed:
        logger.info("")
        logger.info("=" * 60)
        logger.info("  Seeding Default Workspace...")
        logger.info("=" * 60)

        from setup.seed_master_data_from_backup import seed_from_backup, DEFAULT_BACKUP_PATH
        await seed_from_backup(DEFAULT_BACKUP_PATH, reset=False)
    else:
        logger.info("Skipping seed (--no-seed flag set).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Drop all tables, recreate the schema from ORM models, "
            "and seed the default workspace. ⚠️ DESTRUCTIVE."
        )
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seeding the default workspace after schema reset.",
    )
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       SynapseForge — Database Reset Utility             ║")
    print("║  ⚠️  This will DROP all tables and recreate them.       ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    asyncio.run(run(skip_seed=args.no_seed))


if __name__ == "__main__":
    main()
