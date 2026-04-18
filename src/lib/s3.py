"""Thin async wrapper around boto3 S3 for file storage."""

from __future__ import annotations

import asyncio
from typing import Any

import boto3
import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)

_client: Any | None = None


def _get_client() -> Any:
    """Lazy-init the S3 client."""
    global _client  # noqa: PLW0603
    if _client is None:
        settings = get_settings()
        _client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
    return _client


async def upload_file(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload bytes to S3.

    Args:
        key: S3 object key (e.g. 'slides/IN2064/lecture1.pdf').
        data: Raw file bytes.
        content_type: MIME type for the object.

    Returns:
        The S3 key of the uploaded object.
    """
    settings = get_settings()
    client = _get_client()

    await asyncio.to_thread(
        client.put_object,
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    logger.info("s3_upload_done", key=key, size=len(data))
    return key


async def download_file(key: str) -> bytes:
    """Download an object from S3.

    Args:
        key: S3 object key.

    Returns:
        Raw file bytes.
    """
    settings = get_settings()
    client = _get_client()

    response = await asyncio.to_thread(
        client.get_object,
        Bucket=settings.s3_bucket,
        Key=key,
    )
    data: bytes = await asyncio.to_thread(response["Body"].read)
    logger.info("s3_download_done", key=key, size=len(data))
    return data


async def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for downloading an S3 object.

    Args:
        key: S3 object key.
        expires_in: URL expiry in seconds (default 1 hour).

    Returns:
        Presigned URL string.
    """
    settings = get_settings()
    client = _get_client()

    url: str = await asyncio.to_thread(
        client.generate_presigned_url,
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
    return url


async def list_objects(prefix: str) -> list[dict[str, Any]]:
    """List objects under a prefix.

    Args:
        prefix: S3 key prefix (e.g. 'slides/IN2064/').

    Returns:
        List of dicts with 'key', 'size', 'last_modified'.
    """
    settings = get_settings()
    client = _get_client()

    response = await asyncio.to_thread(
        client.list_objects_v2,
        Bucket=settings.s3_bucket,
        Prefix=prefix,
    )

    objects: list[dict[str, Any]] = []
    for obj in response.get("Contents", []):
        objects.append(
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            }
        )
    return objects
