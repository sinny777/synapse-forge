"""
SynapseForge — IBM Cloud Object Storage (COS) Service

Handles uploading, downloading, and checking artifacts on IBM COS.
Features:
  - Supports IAM API Key authentication via `ibm-cos-sdk`
  - Supports HMAC Access/Secret Key authentication via standard S3
  - Graceful mock fallback for local development if credentials are not configured
  - Workspace-scoped key formatting (e.g., workspaces/<workspace_id>/<artifact_type>/<filename>)
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import shutil

logger = logging.getLogger("ntr.services.ibm_cos")

# Try importing the official IBM COS SDK or fall back to standard boto3
try:
    import ibm_boto3
    from ibm_botocore.client import Config
    from ibm_botocore.exceptions import ClientError
    HAS_IBM_SDK = True
except ImportError:
    try:
        import boto3
        from botocore.client import Config
        from botocore.exceptions import ClientError
        ibm_boto3 = boto3  # Fall back to boto3
        HAS_IBM_SDK = False
    except ImportError:
        HAS_IBM_SDK = False
        ClientError = Exception


class IBMCOSService:
    """
    Service to manage interactions with IBM Cloud Object Storage.
    Loads configurations from environment variables.
    """

    def __init__(self):
        # Load from .env
        self.endpoint = os.getenv("IBM_COS_ENDPOINT", "").strip()
        self.api_key = os.getenv("IBM_COS_API_KEY_ID", "").strip()
        self.instance_id = os.getenv("IBM_COS_SERVICE_INSTANCE_ID", "").strip()
        self.default_bucket = os.getenv("IBM_COS_BUCKET_NAME", "synapse-forge").strip()
        
        # Optional HMAC credentials
        self.hmac_access_key = os.getenv("IBM_COS_ACCESS_KEY_ID", "").strip()
        self.hmac_secret_key = os.getenv("IBM_COS_SECRET_ACCESS_KEY", "").strip()

        self.is_mock = False
        self.client = None

        # Determine if we should run in Mock mode (if no credentials are provided)
        has_iam = bool(self.api_key and self.instance_id and self.endpoint)
        has_hmac = bool(self.hmac_access_key and self.hmac_secret_key and self.endpoint)

        if not (has_iam or has_hmac):
            logger.warning(
                "IBM Cloud Object Storage credentials not fully configured in .env. "
                "Running in MOCK storage mode (local directory simulation under 'data/cos_mock')."
            )
            self.is_mock = True
            self.mock_dir = Path("data/cos_mock")
            self.mock_dir.mkdir(parents=True, exist_ok=True)
            self.endpoint = "mock-cos.local"
        else:
            self._init_cos_client(has_iam, has_hmac)

    def _init_cos_client(self, has_iam: bool, has_hmac: bool):
        """Initialize the boto3/ibm_boto3 client based on credentials."""
        try:
            if has_iam and HAS_IBM_SDK:
                logger.info("Initializing IBM COS client using IAM API Key auth.")
                self.client = ibm_boto3.client(
                    service_name="s3",
                    ibm_api_key_id=self.api_key,
                    ibm_service_instance_id=self.instance_id,
                    config=Config(signature_version="oauth"),
                    endpoint_url=self.endpoint,
                )
            else:
                # Fall back to HMAC or standard S3 auth (works with boto3 / ibm_boto3)
                logger.info("Initializing S3-compatible COS client using HMAC Access Keys.")
                # If both IAM and HMAC were missing or SDK wasn't there, we use HMAC
                access_key = self.hmac_access_key or self.api_key
                secret_key = self.hmac_secret_key or "secret"
                self.client = ibm_boto3.client(
                    service_name="s3",
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    config=Config(signature_version="s3v4"),
                    endpoint_url=self.endpoint,
                )
        except Exception as e:
            logger.error(f"Failed to initialize IBM COS client: {e}. Falling back to MOCK storage.", exc_info=True)
            self.is_mock = True
            self.mock_dir = Path("data/cos_mock")
            self.mock_dir.mkdir(parents=True, exist_ok=True)

    def ensure_bucket_exists(self, bucket_name: Optional[str] = None) -> str:
        """Verify that a bucket exists, or create it if it does not."""
        bucket = bucket_name or self.default_bucket
        if self.is_mock:
            mock_bucket_dir = self.mock_dir / bucket
            mock_bucket_dir.mkdir(parents=True, exist_ok=True)
            return bucket

        try:
            self.client.head_bucket(Bucket=bucket)
            logger.debug(f"Bucket '{bucket}' already exists and is accessible.")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code in ["404", "NoSuchBucket"]:
                logger.info(f"Bucket '{bucket}' not found. Creating bucket...")
                try:
                    # IBM COS usually expects LocationConstraint inside CreateBucketConfiguration,
                    # but simple create works for default regions or standard setup.
                    self.client.create_bucket(Bucket=bucket)
                    logger.info(f"Successfully created IBM COS bucket: {bucket}")
                except Exception as create_err:
                    logger.error(f"Failed to create bucket '{bucket}': {create_err}")
                    raise create_err
            else:
                logger.error(f"Error checking bucket '{bucket}': {e}")
                raise e
        return bucket

    def upload_file(self, local_path: Path, object_key: str, bucket_name: Optional[str] = None) -> str:
        """
        Upload a local file to IBM COS.
        Returns the public/reference URL.
        """
        bucket = self.ensure_bucket_exists(bucket_name)
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found for upload: {local_path}")

        if self.is_mock:
            target_path = self.mock_dir / bucket / object_key
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, target_path)
            logger.info(f"[Mock COS] Uploaded '{local_path}' to 'cos://{bucket}/{object_key}'")
            return f"cos://{self.endpoint}/{bucket}/{object_key}"

        try:
            logger.info(f"Uploading file '{local_path}' to '{bucket}/{object_key}'...")
            self.client.upload_file(
                Filename=str(local_path),
                Bucket=bucket,
                Key=object_key
            )
            cos_url = f"cos://{bucket}/{object_key}"
            logger.info(f"✓ Uploaded successfully. URL: {cos_url}")
            return cos_url
        except Exception as e:
            logger.error(f"Failed to upload file '{local_path}' to COS: {e}")
            raise e

    def download_file(self, object_key: str, local_path: Path, bucket_name: Optional[str] = None) -> Path:
        """Download an object from IBM COS to a local file path."""
        bucket = bucket_name or self.default_bucket
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if self.is_mock:
            source_path = self.mock_dir / bucket / object_key
            if not source_path.exists():
                raise FileNotFoundError(f"[Mock COS] Object '{object_key}' not found in bucket '{bucket}'")
            shutil.copy2(source_path, local_path)
            logger.info(f"[Mock COS] Downloaded 'cos://{bucket}/{object_key}' to '{local_path}'")
            return local_path

        try:
            logger.info(f"Downloading from COS '{bucket}/{object_key}' to '{local_path}'...")
            self.client.download_file(
                Bucket=bucket,
                Key=object_key,
                Filename=str(local_path)
            )
            logger.info(f"✓ Downloaded successfully.")
            return local_path
        except Exception as e:
            logger.error(f"Failed to download object '{object_key}' from COS: {e}")
            raise e

    def upload_directory(self, local_dir: Path, key_prefix: str, bucket_name: Optional[str] = None) -> str:
        """
        Upload a full directory (e.g. model checkpoint folder) recursively to IBM COS.
        Returns the parent reference URL.
        """
        bucket = self.ensure_bucket_exists(bucket_name)
        local_dir = Path(local_dir)
        if not local_dir.is_dir():
            raise NotADirectoryError(f"Local path is not a directory: {local_dir}")

        if self.is_mock:
            target_dir = self.mock_dir / bucket / key_prefix
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(local_dir, target_dir)
            logger.info(f"[Mock COS] Uploaded directory '{local_dir}' to 'cos://{bucket}/{key_prefix}'")
            return f"cos://{self.endpoint}/{bucket}/{key_prefix}"

        try:
            logger.info(f"Uploading directory '{local_dir}' to '{bucket}/{key_prefix}'...")
            for item in local_dir.rglob("*"):
                if item.is_file():
                    # Calculate relative key
                    rel_path = item.relative_to(local_dir)
                    item_key = f"{key_prefix}/{rel_path}".replace("\\", "/")
                    logger.debug(f"Uploading sub-file {item} -> {item_key}")
                    self.client.upload_file(
                        Filename=str(item),
                        Bucket=bucket,
                        Key=item_key
                    )
            cos_url = f"cos://{bucket}/{key_prefix}"
            logger.info(f"✓ Directory uploaded successfully. Base URL: {cos_url}")
            return cos_url
        except Exception as e:
            logger.error(f"Failed to upload directory '{local_dir}' to COS: {e}")
            raise e

    def download_directory(self, key_prefix: str, local_dir: Path, bucket_name: Optional[str] = None) -> Path:
        """
        Download all objects with a key prefix (e.g. model directory) from COS to local folder.
        """
        bucket = bucket_name or self.default_bucket
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        if self.is_mock:
            source_dir = self.mock_dir / bucket / key_prefix
            if not source_dir.exists():
                logger.warning(f"[Mock COS] Source directory 'cos://{bucket}/{key_prefix}' does not exist.")
                return local_dir
            # Merge mock directory into local
            for item in source_dir.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(source_dir)
                    dest = local_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
            logger.info(f"[Mock COS] Downloaded directory 'cos://{bucket}/{key_prefix}' to '{local_dir}'")
            return local_dir

        try:
            logger.info(f"Downloading directory prefix '{key_prefix}' from COS to '{local_dir}'...")
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    # Calculate relative path
                    rel_key = key[len(key_prefix):].lstrip("/")
                    if not rel_key:
                        continue
                    
                    target_file = local_dir / rel_key
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    logger.debug(f"Downloading key {key} -> {target_file}")
                    self.client.download_file(
                        Bucket=bucket,
                        Key=key,
                        Filename=str(target_file)
                    )
            logger.info("✓ Directory prefix downloaded successfully.")
            return local_dir
        except Exception as e:
            logger.error(f"Failed to download directory prefix '{key_prefix}' from COS: {e}")
            raise e

    def delete_prefix(self, key_prefix: str, bucket_name: Optional[str] = None):
        """Delete all objects matching the key prefix."""
        bucket = bucket_name or self.default_bucket
        if self.is_mock:
            target = self.mock_dir / bucket / key_prefix
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    os.remove(target)
            logger.info(f"[Mock COS] Deleted prefix 'cos://{bucket}/{key_prefix}'")
            return

        try:
            logger.info(f"Deleting COS prefix '{key_prefix}' in bucket '{bucket}'...")
            paginator = self.client.get_paginator("list_objects_v2")
            objects_to_delete = []
            for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix):
                for obj in page.get("Contents", []):
                    objects_to_delete.append({"Key": obj["Key"]})

            if objects_to_delete:
                # Max 1000 items per delete call in standard S3
                for i in range(0, len(objects_to_delete), 1000):
                    chunk = objects_to_delete[i:i+1000]
                    self.client.delete_objects(
                        Bucket=bucket,
                        Delete={"Objects": chunk}
                    )
            logger.info(f"✓ Successfully deleted {len(objects_to_delete)} objects.")
        except Exception as e:
            logger.error(f"Failed to delete COS prefix '{key_prefix}': {e}")


# Singleton instance for platform-wide usage
cos_service = IBMCOSService()
