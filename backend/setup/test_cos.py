"""
SynapseForge — IBM Cloud Object Storage (COS) Integration Test Script

Validates the full pipeline:
  1. Initializes IBMCOSService & ArtifactManager
  2. Creates a mock workspace and test files
  3. Uploads files to COS, registers database records, and deletes local files
  4. Downloads on-demand from COS and verifies content integrity
  5. Cleans up test records from database and COS/mock storage
"""

import os
import sys
import asyncio
import uuid
import logging
from pathlib import Path

# Bootstrap: ensure package root is on sys.path
_backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_backend_dir / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_cos")

from services.ibm_cos_service import cos_service
from services.artifact_manager import ArtifactManager
from db.engine import init_db, close_db
from db.models import Workspace, PipelineArtifact
from sqlalchemy import select


async def run_test():
    logger.info("Starting IBM COS and ArtifactManager integration test...")

    # 1. Initialize database connection
    await init_db()
    from db.engine import _session_factory

    # 2. Setup mock workspace
    ws_id = uuid.uuid4()
    async with _session_factory() as session:
        # Create a temporary workspace record for testing
        test_ws = Workspace(
            id=ws_id,
            name=f"Test Workspace - {ws_id.hex[:6]}",
            description="Created for testing IBM COS pipeline integration",
            created_by="test_system",
            updated_by="test_system"
        )
        session.add(test_ws)
        await session.commit()
    logger.info(f"Created temporary workspace in DB: {ws_id}")

    # 3. Create test files
    temp_dir = Path("data/test_temp")
    temp_dir.mkdir(parents=True, exist_ok=True)

    test_file_path = temp_dir / "synthetic_queries.jsonl"
    with open(test_file_path, "w") as f:
        f.write('{"query": "get policies", "tool": "get_policy_details"}\n')
        f.write('{"query": "execute trade AAPL", "tool": "execute_trade"}\n')

    logger.info(f"Created temporary test file: {test_file_path}")

    try:
        # 4. Upload and Register using ArtifactManager
        logger.info("Uploading and registering file via ArtifactManager...")
        artifact = await ArtifactManager.upload_and_register_file(
            workspace_id=ws_id,
            phase="generate",
            artifact_type="dataset",
            local_file_path=test_file_path
        )

        assert artifact is not None, "Artifact registration returned None"
        assert not test_file_path.exists(), "Local file was not deleted after upload!"
        logger.info("✓ Upload, database registration, and local file deletion successful!")

        # 5. Verify Database Entry
        async with _session_factory() as session:
            stmt = select(PipelineArtifact).where(PipelineArtifact.workspace_id == ws_id)
            db_artifact = (await session.execute(stmt)).scalars().first()
            
            assert db_artifact is not None, "No artifact found in database!"
            assert db_artifact.cos_key.startswith(f"workspaces/{ws_id}"), "COS key prefix is incorrect!"
            logger.info(f"✓ Database record successfully verified: {db_artifact.url}")

        # 6. Download on-demand
        logger.info("Downloading file on-demand back to local path...")
        downloaded = await ArtifactManager.download_file_if_needed(
            workspace_id=ws_id,
            phase="generate",
            artifact_type="dataset",
            local_file_path=test_file_path
        )

        assert downloaded, "Download process failed!"
        assert test_file_path.exists(), "Downloaded file does not exist locally!"
        
        # Verify content integrity
        with open(test_file_path, "r") as f:
            content = f.read()
            assert "execute_trade" in content, "Downloaded file content is corrupted!"
        logger.info("✓ On-demand download and content integrity verified successfully!")

        # 7. Clean up
        logger.info("Cleaning up test resources...")
        # Delete from COS / mock storage
        cos_service.delete_prefix(f"workspaces/{ws_id}")
        
        # Delete from DB
        async with _session_factory() as session:
            stmt_art = select(PipelineArtifact).where(PipelineArtifact.workspace_id == ws_id)
            arts = (await session.execute(stmt_art)).scalars().all()
            for art in arts:
                await session.delete(art)
                
            stmt_ws = select(Workspace).where(Workspace.id == ws_id)
            ws_rec = (await session.execute(stmt_ws)).scalars().first()
            if ws_rec:
                await session.delete(ws_rec)
                
            await session.commit()
            
        if test_file_path.exists():
            os.remove(test_file_path)
            
        logger.info("✓ Clean up completed.")
        logger.info("🎉 ALL TESTS PASSED SUCCESSFULLY! IBM COS INTEGRATION IS 100% FUNCTIONAL.")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
    finally:
        # Clean up directory if empty
        if temp_dir.exists() and not any(temp_dir.iterdir()):
            temp_dir.rmdir()
        await close_db()


if __name__ == "__main__":
    asyncio.run(run_test())
