"""Cognee + S3 Vectors memory abstraction."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def add_to_memory(
    *,
    user_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Ingest content into the knowledge graph.

    Args:
        user_id: Student identifier for namespace isolation.
        content: Text content to ingest.
        metadata: Optional metadata to attach.
    """
    # TODO(brscn): Wire to Cognee Cloud once API key is configured
    logger.info("memory_add", user_id=user_id, content_length=len(content))


async def query_memory(
    *,
    user_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Query the knowledge graph for relevant context.

    Args:
        user_id: Student identifier for namespace isolation.
        query: Natural language query.
        top_k: Number of results to return.

    Returns:
        List of matching documents with content and metadata.
    """
    # TODO(brscn): Wire to Cognee Cloud once API key is configured
    logger.info("memory_query", user_id=user_id, query=query, top_k=top_k)
    return []
