"""
SynapseForge — Database Reset & Re-seed Script

Drops ALL collections, recreates indexes, and seeds
the default workspace with template Agents and Tools.

⚠️  DESTRUCTIVE — intended for rapid prototyping only.
    Does NOT use migrations.

Usage:
    # From the backend/ directory with venv activated:
    python -m setup.reset_db              # full reset + seed
    python -m setup.reset_db --no-seed    # reset schema only, skip seeding
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure the backend package root is on sys.path and .env is loaded
# ---------------------------------------------------------------------------
_backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_backend_dir / ".env")

from db.engine import init_db, reset_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("reset_db")


# ═══════════════════════════════════════════════════════════════════════════
# Core reset logic
# ═══════════════════════════════════════════════════════════════════════════

async def reset_schema() -> None:
    """
    Connect to MongoDB, drop ALL collections, and recreate indexes.
    """
    logger.info("Connecting to MongoDB...")
    await init_db()
    
    logger.warning("🗑  Dropping ALL collections...")
    await reset_db()
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
            "Drop all collections, recreate indexes, "
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
    print("║  ⚠️  This will DROP all collections and recreate them.  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    asyncio.run(run(skip_seed=args.no_seed))


if __name__ == "__main__":
    main()

# Made with Bob
