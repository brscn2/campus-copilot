"""Cognee Cloud memory layer — knowledge graph for cross-session retrieval."""

from __future__ import annotations

from typing import Any

import cognee
import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)

_initialized = False


async def _ensure_init() -> None:
    """One-time Cognee config from env vars."""
    global _initialized
    if _initialized:
        return
    settings = get_settings()
    if settings.cognee_api_key:
        cognee.config.set_llm_config(
            {
                "llm_api_key": settings.cognee_api_key,
                "llm_provider": settings.cognee_llm_provider,
            }
        )
    _initialized = True


async def add_to_memory(
    *,
    user_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Ingest content into Cognee knowledge graph.

    Args:
        user_id: Student identifier for namespace isolation.
        content: Text content to ingest.
        metadata: Optional metadata to attach.
    """
    try:
        await _ensure_init()
        dataset_name = f"student_{user_id}"
        logger.info("memory_add", user_id=user_id, content_length=len(content))
        await cognee.remember(content, dataset_name=dataset_name)
    except Exception:
        logger.warning("memory_add_failed", user_id=user_id, exc_info=True)


async def query_memory(
    *,
    user_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Query Cognee knowledge graph for relevant context.

    Args:
        user_id: Student identifier for namespace isolation.
        query: Natural language query.
        top_k: Number of results to return.

    Returns:
        List of matching documents with content and metadata.
    """
    try:
        await _ensure_init()
        logger.info("memory_query", user_id=user_id, query=query, top_k=top_k)
        results = await cognee.recall(
            query,
            datasets=[f"student_{user_id}"],
            top_k=top_k,
        )
        return [
            {"text": str(r.get("text", r)), "score": r.get("score", 0.0)}
            if isinstance(r, dict)
            else {"text": str(r), "score": 0.0}
            for r in results
        ]
    except Exception:
        logger.warning("memory_query_failed", user_id=user_id, exc_info=True)
        return []
