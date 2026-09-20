import asyncio
import json
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


def _public_read_policy(bucket: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            ],
        }
    )


def _ensure_public_read(client: "S3Client", bucket: str) -> None:
    """Product photos are fetched straight by the buyer's browser, so the objects must be readable.

    A bucket that already carries a policy is left alone: whoever wrote it knew what the
    bucket is for, and a CDN in front of it may well require something narrower.
    """
    try:
        client.get_bucket_policy(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchBucketPolicy":
            raise
        client.put_bucket_policy(Bucket=bucket, Policy=_public_read_policy(bucket))
        logger.info("granted public read on bucket %s", bucket)


def _ensure_bucket_sync(settings: Settings) -> None:
    client = build_s3_client(settings)
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket"}:
            raise
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("created bucket %s", settings.s3_bucket)
    _ensure_public_read(client, settings.s3_bucket)


async def ensure_bucket(settings: Settings) -> None:
    """Create the upload bucket when missing, so a fresh environment works without manual steps."""
    await asyncio.to_thread(_ensure_bucket_sync, settings)


async def put_object(settings: Settings, key: str, data: bytes, content_type: str) -> str:
    """Uploads to the object store and answers with the URL the browser will fetch.

    The file never touches the backend container's disk: a container is replaced on every
    deploy, and two replicas would not even see the same disk.
    """

    def _put() -> None:
        build_s3_client(settings).put_object(
            Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
        )

    await asyncio.to_thread(_put)
    return public_url(settings, key)


async def delete_object(settings: Settings, key: str) -> None:
    """Best effort: a leftover object costs storage, a missing one breaks a page."""

    def _delete() -> None:
        build_s3_client(settings).delete_object(Bucket=settings.s3_bucket, Key=key)

    try:
        await asyncio.to_thread(_delete)
    except ClientError:
        logger.exception("could not delete object %s", key)


def public_url(settings: Settings, key: str) -> str:
    base = settings.s3_public_url or f"{settings.s3_endpoint_url.rstrip('/')}/{settings.s3_bucket}"
    return f"{base.rstrip('/')}/{key}"


def key_from_url(settings: Settings, url: str) -> str | None:
    """The reverse of public_url, for deleting the object a stored row points at."""
    base = public_url(settings, "")
    return url.removeprefix(base) if url.startswith(base) else None


async def storage_healthy(settings: Settings) -> bool:
    def _check() -> bool:
        try:
            build_s3_client(settings).head_bucket(Bucket=settings.s3_bucket)
        except ClientError:
            return False
        return True

    return await asyncio.to_thread(_check)
