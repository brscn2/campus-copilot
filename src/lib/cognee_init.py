"""Lazy initialization for the Cognee Cloud SDK."""

from __future__ import annotations

import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)

_initialized = False


async def ensure_cognee() -> None:
    """Connect to Cognee Cloud exactly once, using our app settings."""
    global _initialized  # noqa: PLW0603
    if _initialized:
        return

    import cognee

    settings = get_settings()
    await cognee.serve(url=settings.cognee_api_url, api_key=settings.cognee_api_key)
    _initialized = True
    logger.info("cognee_cloud_connected", url=settings.cognee_api_url)
