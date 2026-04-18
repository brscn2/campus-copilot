"""Cognee Cloud memory layer — knowledge graph for cross-session retrieval."""

from __future__ import annotations

from typing import Any

import structlog
from cogwit_sdk import CogwitConfig, SearchType, cogwit

from src.config import get_settings

logger = structlog.get_logger(__name__)

_client: cogwit | None = None


def _get_client() -> cogwit | None:
    """Lazy-init the Cognee Cloud client."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.cognee_api_key:
            return None
        _client = cogwit(CogwitConfig(api_key=settings.cognee_api_key))
    return _client


async def add_to_memory(
    *,
    user_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Ingest content into Cognee Cloud knowledge graph."""
    client = _get_client()
    if client is None:
        return
    try:
        dataset_name = f"student_{user_id}"
        logger.info("memory_add", user_id=user_id, content_length=len(content))
        response = await client.add(data=content, dataset_name=dataset_name)
        if hasattr(response, "dataset_id"):
            await client.cognify(datasets=[dataset_name])
    except Exception:
        logger.warning("memory_add_failed", user_id=user_id, exc_info=True)


async def query_memory(
    *,
    user_id: str,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Query Cognee Cloud knowledge graph for relevant context."""
    client = _get_client()
    if client is None:
        return []
    try:
        logger.info("memory_query", user_id=user_id, query=query)
        response = await client.search(
            query_text=query,
            query_type=SearchType.GRAPH_COMPLETION,
        )
        if isinstance(response, list):
            results: list[dict[str, Any]] = []
            for r in response[:top_k]:
                text = str(r.search_result) if hasattr(r, "search_result") else str(r)
                results.append({"text": text})
            return results
        if hasattr(response, "result") and response.result:
            return [{"text": str(response.result)}]
        return []
    except Exception:
        logger.warning("memory_query_failed", user_id=user_id, exc_info=True)
        return []
