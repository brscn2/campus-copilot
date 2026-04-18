"""Cognee memory layer — knowledge graph for cross-session retrieval."""

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

    cognee.config.set_llm_config(
        {
            "llm_api_key": settings.cognee_api_key or settings.aws_access_key_id,
            "llm_provider": settings.cognee_llm_provider,
            "llm_model": settings.cognee_llm_model,
        }
    )

    cognee.config.set_embedding_config(
        {
            "embedding_provider": settings.cognee_embedding_provider,
            "embedding_model": settings.cognee_embedding_model,
            "embedding_dimensions": settings.cognee_embedding_dimensions,
            "embedding_api_key": settings.cognee_api_key or settings.aws_access_key_id,
        }
    )

    logger.info(
        "cognee_initialized",
        llm_provider=settings.cognee_llm_provider,
        llm_model=settings.cognee_llm_model,
        embedding_provider=settings.cognee_embedding_provider,
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


async def forget_memory(*, user_id: str, dataset_name: str | None = None) -> None:
    """Delete data from Cognee knowledge graph.

    Args:
        user_id: Student identifier for namespace isolation.
        dataset_name: Specific dataset to delete. Defaults to the user's dataset.
    """
    try:
        await _ensure_init()
        target = dataset_name or f"student_{user_id}"
        logger.info("memory_forget", user_id=user_id, dataset=target)
        await cognee.forget(dataset=target)
    except Exception:
        logger.warning("memory_forget_failed", user_id=user_id, exc_info=True)
