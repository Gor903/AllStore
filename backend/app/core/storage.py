import asyncio
from typing import TYPE_CHECKING

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

logger = get_logger(__name__)


def build_s3_client(settings: Settings) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _ensure_bucket_sync(settings: Settings) -> None:
    client = build_s3_client(settings)
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket"}:
            raise
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("created bucket %s", settings.s3_bucket)


async def ensure_bucket(settings: Settings) -> None:
    """Create the upload bucket when missing, so a fresh environment works without manual steps."""
    await asyncio.to_thread(_ensure_bucket_sync, settings)


async def storage_healthy(settings: Settings) -> bool:
    def _check() -> bool:
        try:
            build_s3_client(settings).head_bucket(Bucket=settings.s3_bucket)
        except ClientError:
            return False
        return True

    return await asyncio.to_thread(_check)
