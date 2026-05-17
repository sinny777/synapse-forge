"""
SynapseForge — Artifact Manager

Manages the lifecycle of pipeline artifacts (generation & training) between
the local runtime filesystem, IBM Cloud Object Storage (COS), and the database.
"""

import os
import shutil
import logging
import uuid
from pathlib import Path
from typing import Optional, List

from services.ibm_cos_service import cos_service
import db.engine as db_engine
from db.models import PipelineArtifact
from sqlalchemy import select

logger = logging.getLogger("ntr.services.artifact_manager")


class ArtifactManager:
    """
    Orchestrates the upload, download, database registration, and cleanup of
    synthetic generation (Phase 1) and fine-tuning (Phase 2) artifacts.
    """

    @staticmethod
    def _get_cos_prefix(workspace_id: uuid.UUID, phase: str, artifact_type: str) -> str:
        """Helper to create standardized, isolated COS object key prefixes."""
        return f"workspaces/{workspace_id}/{phase}/{artifact_type}"

    @classmethod
    async def upload_and_register_file(
        cls,
        workspace_id: uuid.UUID,
        phase: str,
        artifact_type: str,
        local_file_path: Path,
        bucket_name: Optional[str] = None,
    ) -> Optional[PipelineArtifact]:
        """
        Uploads a local file to IBM COS, registers it in the database,
        and deletes the local file.
        """
        local_file_path = Path(local_file_path)
        if not local_file_path.exists():
            logger.warning(f"Skipping upload: Local file not found at {local_file_path}")
            return None

        filename = local_file_path.name
        cos_key = f"{cls._get_cos_prefix(workspace_id, phase, artifact_type)}/{filename}"

        try:
            # 1. Upload to COS
            cos_url = cos_service.upload_file(
                local_path=local_file_path,
                object_key=cos_key,
                bucket_name=bucket_name,
            )

            # 2. Register in Database
            async with db_engine._session_factory() as session:
                # Remove any existing artifact of the same type in this workspace/phase
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == workspace_id,
                    PipelineArtifact.phase == phase,
                    PipelineArtifact.artifact_type == artifact_type,
                    PipelineArtifact.name == filename,
                )
                existing = (await session.execute(stmt)).scalars().first()
                if existing:
                    await session.delete(existing)

                artifact = PipelineArtifact(
                    workspace_id=workspace_id,
                    phase=phase,
                    artifact_type=artifact_type,
                    name=filename,
                    cos_bucket=bucket_name or cos_service.default_bucket,
                    cos_key=cos_key,
                    cos_endpoint=cos_service.endpoint,
                    url=cos_url,
                    created_by="system",
                    updated_by="system",
                )
                session.add(artifact)
                await session.commit()
                await session.refresh(artifact)

            logger.info(f"✓ Registered file artifact: {artifact_type} ({filename}) -> {cos_url}")

            # 3. Delete local copy
            if local_file_path.exists():
                os.remove(local_file_path)
                logger.info(f"✓ Deleted local copy of {local_file_path}")

            return artifact

        except Exception as e:
            logger.error(f"Failed to upload and register file artifact {artifact_type}: {e}", exc_info=True)
            raise e

    @classmethod
    async def upload_and_register_directory(
        cls,
        workspace_id: uuid.UUID,
        phase: str,
        artifact_type: str,
        local_dir_path: Path,
        dir_name: str,
        bucket_name: Optional[str] = None,
    ) -> Optional[PipelineArtifact]:
        """
        Uploads a local directory recursively to IBM COS, registers it in the DB,
        and deletes the local directory.
        """
        local_dir_path = Path(local_dir_path)
        if not local_dir_path.exists() or not local_dir_path.is_dir():
            logger.warning(f"Skipping upload: Local directory not found at {local_dir_path}")
            return None

        cos_key = f"{cls._get_cos_prefix(workspace_id, phase, artifact_type)}/{dir_name}"

        try:
            # 1. Upload directory to COS
            cos_url = cos_service.upload_directory(
                local_dir=local_dir_path,
                key_prefix=cos_key,
                bucket_name=bucket_name,
            )

            # 2. Register in Database
            async with db_engine._session_factory() as session:
                # Remove any existing artifact of the same type in this workspace/phase
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == workspace_id,
                    PipelineArtifact.phase == phase,
                    PipelineArtifact.artifact_type == artifact_type,
                    PipelineArtifact.name == dir_name,
                )
                existing = (await session.execute(stmt)).scalars().first()
                if existing:
                    await session.delete(existing)

                artifact = PipelineArtifact(
                    workspace_id=workspace_id,
                    phase=phase,
                    artifact_type=artifact_type,
                    name=dir_name,
                    cos_bucket=bucket_name or cos_service.default_bucket,
                    cos_key=cos_key,
                    cos_endpoint=cos_service.endpoint,
                    url=cos_url,
                    created_by="system",
                    updated_by="system",
                )
                session.add(artifact)
                await session.commit()
                await session.refresh(artifact)

            logger.info(f"✓ Registered directory artifact: {artifact_type} ({dir_name}) -> {cos_url}")

            # 3. Delete local copy
            if local_dir_path.exists():
                shutil.rmtree(local_dir_path)
                logger.info(f"✓ Deleted local copy of directory {local_dir_path}")

            return artifact

        except Exception as e:
            logger.error(f"Failed to upload and register directory artifact {artifact_type}: {e}", exc_info=True)
            raise e

    @classmethod
    async def download_file_if_needed(
        cls,
        workspace_id: uuid.UUID,
        phase: str,
        artifact_type: str,
        local_file_path: Path,
        bucket_name: Optional[str] = None,
    ) -> bool:
        """
        Ensures a file exists locally. If it does not, fetches its reference from the DB,
        downloads it from COS, and caches it locally.
        """
        local_file_path = Path(local_file_path)
        if local_file_path.exists():
            return True

        filename = local_file_path.name
        logger.info(f"Local file {filename} not found. Checking COS database registry...")

        try:
            async with db_engine._session_factory() as session:
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == workspace_id,
                    PipelineArtifact.phase == phase,
                    PipelineArtifact.artifact_type == artifact_type,
                    PipelineArtifact.name == filename,
                )
                artifact = (await session.execute(stmt)).scalars().first()

            if not artifact:
                logger.warning(
                    f"No registered database reference found for workspace={workspace_id}, "
                    f"phase={phase}, type={artifact_type}, name={filename}"
                )
                return False

            logger.info(f"Found registered reference in DB. Downloading from COS: {artifact.url}")
            cos_service.download_file(
                object_key=artifact.cos_key,
                local_path=local_file_path,
                bucket_name=bucket_name or artifact.cos_bucket,
            )
            return True

        except Exception as e:
            logger.error(f"Failed to download file from COS: {e}", exc_info=True)
            return False

    @classmethod
    async def download_directory_if_needed(
        cls,
        workspace_id: uuid.UUID,
        phase: str,
        artifact_type: str,
        local_dir_path: Path,
        dir_name: str,
        bucket_name: Optional[str] = None,
    ) -> bool:
        """
        Ensures a directory exists locally. If it does not, fetches its reference from the DB,
        downloads it from COS, and caches it locally.
        """
        local_dir_path = Path(local_dir_path)
        if local_dir_path.exists() and any(local_dir_path.iterdir()):
            # Exists and is not empty
            return True

        logger.info(f"Local directory {dir_name} not found or empty. Checking COS database registry...")

        try:
            async with db_engine._session_factory() as session:
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == workspace_id,
                    PipelineArtifact.phase == phase,
                    PipelineArtifact.artifact_type == artifact_type,
                    PipelineArtifact.name == dir_name,
                )
                artifact = (await session.execute(stmt)).scalars().first()

            if not artifact:
                logger.warning(
                    f"No registered database reference found for workspace={workspace_id}, "
                    f"phase={phase}, type={artifact_type}, name={dir_name}"
                )
                return False

            logger.info(f"Found registered reference in DB. Downloading directory from COS: {artifact.url}")
            cos_service.download_directory(
                key_prefix=artifact.cos_key,
                local_dir=local_dir_path,
                bucket_name=bucket_name or artifact.cos_bucket,
            )
            return True

        except Exception as e:
            logger.error(f"Failed to download directory from COS: {e}", exc_info=True)
            return False

    @classmethod
    def cleanup_empty_workspace_directories(cls, workspace_id: uuid.UUID) -> None:
        """
        Recursively walks the workspace directory and deletes any empty subdirectories,
        and finally the workspace directory itself if it is empty.
        """
        try:
            workspace_dir = Path(__file__).parent.parent.absolute() / "data" / "workspaces" / str(workspace_id)
            if not workspace_dir.exists():
                return
            
            # Helper to recursively clean empty dirs
            def _clean_dir(d: Path):
                if not d.is_dir():
                    return
                # Clean children first
                for child in list(d.iterdir()):
                    if child.is_dir():
                        _clean_dir(child)
                # If now empty, delete
                if not any(d.iterdir()):
                    logger.info(f"Cleaning up empty workspace subdirectory: {d}")
                    d.rmdir()

            _clean_dir(workspace_dir)
        except Exception as e:
            logger.warning(f"Error cleaning up empty workspace directories for {workspace_id}: {e}")
    @classmethod
    def upload_and_register_file_sync(
        cls,
        workspace_id: uuid.UUID,
        phase: str,
        artifact_type: str,
        local_file_path: Path,
        bucket_name: Optional[str] = None,
    ) -> Optional[PipelineArtifact]:
        """
        Synchronous wrapper for upload_and_register_file.
        Uses synchronous database operations to avoid event loop conflicts in background threads.
        """
        local_file_path = Path(local_file_path)
        if not local_file_path.exists():
            logger.warning(f"Skipping upload: Local file not found at {local_file_path}")
            return None

        filename = local_file_path.name
        cos_key = f"{cls._get_cos_prefix(workspace_id, phase, artifact_type)}/{filename}"

        try:
            # 1. Upload to COS (synchronous)
            cos_url = cos_service.upload_file(
                local_path=local_file_path,
                object_key=cos_key,
                bucket_name=bucket_name,
            )

            # 2. Register in Database (synchronous)
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            
            # Build database URL from environment variables (same as db.engine)
            user = os.getenv("POSTGRES_USER", "ntr_user")
            password = os.getenv("POSTGRES_PASSWORD", "ntr_secret_2026")
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            db = os.getenv("POSTGRES_DB", "synapse_forge")
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
            
            sync_engine = create_engine(database_url, echo=False)
            SyncSession = sessionmaker(bind=sync_engine)
            
            with SyncSession() as session:
                # Remove any existing artifact of the same type in this workspace/phase
                from sqlalchemy import select
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == workspace_id,
                    PipelineArtifact.phase == phase,
                    PipelineArtifact.artifact_type == artifact_type,
                    PipelineArtifact.name == filename,
                )
                existing = session.execute(stmt).scalars().first()
                if existing:
                    session.delete(existing)

                artifact = PipelineArtifact(
                    workspace_id=workspace_id,
                    phase=phase,
                    artifact_type=artifact_type,
                    name=filename,
                    cos_bucket=bucket_name or cos_service.default_bucket,
                    cos_key=cos_key,
                    cos_endpoint=cos_service.endpoint,
                    url=cos_url,
                    created_by="system",
                    updated_by="system",
                )
                session.add(artifact)
                session.commit()
                session.refresh(artifact)

            logger.info(f"✓ Registered file artifact: {artifact_type} ({filename}) -> {cos_url}")

            # 3. Delete local copy
            if local_file_path.exists():
                os.remove(local_file_path)
                logger.info(f"✓ Deleted local copy of {local_file_path}")

            return artifact

        except Exception as e:
            logger.error(f"Failed to upload and register file artifact {artifact_type}: {e}", exc_info=True)
            raise e

    @classmethod
    def upload_and_register_directory_sync(
        cls,
        workspace_id: uuid.UUID,
        phase: str,
        artifact_type: str,
        local_dir_path: Path,
        dir_name: str,
        bucket_name: Optional[str] = None,
    ) -> Optional[PipelineArtifact]:
        """
        Synchronous wrapper for upload_and_register_directory.
        Uses synchronous database operations to avoid event loop conflicts in background threads.
        """
        local_dir_path = Path(local_dir_path)
        if not local_dir_path.exists() or not local_dir_path.is_dir():
            logger.warning(f"Skipping upload: Local directory not found at {local_dir_path}")
            return None

        cos_key = f"{cls._get_cos_prefix(workspace_id, phase, artifact_type)}/{dir_name}"

        try:
            # 1. Upload directory to COS (synchronous)
            cos_url = cos_service.upload_directory(
                local_dir=local_dir_path,
                key_prefix=cos_key,
                bucket_name=bucket_name,
            )

            # 2. Register in Database (synchronous)
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            
            # Build database URL from environment variables (same as db.engine)
            user = os.getenv("POSTGRES_USER", "ntr_user")
            password = os.getenv("POSTGRES_PASSWORD", "ntr_secret_2026")
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            db = os.getenv("POSTGRES_DB", "synapse_forge")
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
            
            sync_engine = create_engine(database_url, echo=False)
            SyncSession = sessionmaker(bind=sync_engine)
            
            with SyncSession() as session:
                # Remove any existing artifact of the same type in this workspace/phase
                from sqlalchemy import select
                stmt = select(PipelineArtifact).where(
                    PipelineArtifact.workspace_id == workspace_id,
                    PipelineArtifact.phase == phase,
                    PipelineArtifact.artifact_type == artifact_type,
                    PipelineArtifact.name == dir_name,
                )
                existing = session.execute(stmt).scalars().first()
                if existing:
                    session.delete(existing)

                artifact = PipelineArtifact(
                    workspace_id=workspace_id,
                    phase=phase,
                    artifact_type=artifact_type,
                    name=dir_name,
                    cos_bucket=bucket_name or cos_service.default_bucket,
                    cos_key=cos_key,
                    cos_endpoint=cos_service.endpoint,
                    url=cos_url,
                    created_by="system",
                    updated_by="system",
                )
                session.add(artifact)
                session.commit()
                session.refresh(artifact)

            logger.info(f"✓ Registered directory artifact: {artifact_type} ({dir_name}) -> {cos_url}")

            # 3. Delete local copy
            if local_dir_path.exists():
                shutil.rmtree(local_dir_path)
                logger.info(f"✓ Deleted local copy of directory {local_dir_path}")

            return artifact

        except Exception as e:
            logger.error(f"Failed to upload and register directory artifact {artifact_type}: {e}", exc_info=True)
            raise e

