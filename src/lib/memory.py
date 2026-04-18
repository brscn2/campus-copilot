"""Cognee Cloud memory layer — search and retrieval via cogwit-sdk."""

from __future__ import annotations

import os
from typing import Any

import structlog

from src.config import get_settings
from src.exceptions import CogneeRetrievalError

# cogwit_sdk reads COGWIT_API_BASE at import time — set before importing
_boot_settings = get_settings()
if _boot_settings.cognee_api_url:
    os.environ["COGWIT_API_BASE"] = _boot_settings.cognee_api_url

logger = structlog.get_logger(__name__)

_client: Any = None


def _get_client() -> Any:
    """Lazy-init the cogwit SDK client."""
    global _client  # noqa: PLW0603
    if _client is None:
        settings = get_settings()
        os.environ["COGWIT_API_BASE"] = settings.cognee_api_url
        from cogwit_sdk import CogwitConfig, cogwit

        _client = cogwit(CogwitConfig(api_key=settings.cognee_api_key))
    return _client


def _dataset_name(course_id: str) -> str:
    """Build the Cognee dataset name for a course."""
    settings = get_settings()
    return f"{settings.cognee_dataset_prefix}{course_id}"


async def _search(query: str, dataset: str | None = None) -> list[str]:
    """Run a GRAPH_COMPLETION search and return result strings."""
    client = _get_client()
    try:
        results = await client.search(
            query_text=query,
            query_type=client.SearchType.GRAPH_COMPLETION,
        )
        texts: list[str] = []
        for r in results:
            text = str(r.search_result) if hasattr(r, "search_result") else str(r)
            if len(text) > 10:
                texts.append(text)
        return texts
    except Exception as exc:
        logger.error("cognee_search_failed", query=query, exc_info=True)
        raise CogneeRetrievalError(f"Cognee search failed: {exc}") from exc


async def query_course_knowledge(
    course_id: str,
    query: str,
) -> list[str]:
    """Query the Cognee knowledge graph for a course.

    Args:
        course_id: Course identifier (used to build dataset name).
        query: Natural language question about lecture content.

    Returns:
        LLM-synthesized answers grounded in the knowledge graph.
    """
    dataset = _dataset_name(course_id)
    logger.info("cognee_query_knowledge", course_id=course_id, dataset=dataset, query=query)
    return await _search(query, dataset)


async def get_core_concepts(course_id: str) -> list[dict[str, Any]]:
    """Retrieve all core concepts with sub-concepts for a course.

    Args:
        course_id: Course identifier.

    Returns:
        List of dicts with 'name' and 'sub_concepts' keys.
    """
    dataset = _dataset_name(course_id)
    logger.info("cognee_get_core_concepts", course_id=course_id, dataset=dataset)
    query = (
        "List all core concepts in this knowledge graph. "
        "For each core concept, list its sub-concepts and leaf concepts. "
        "Return as a structured hierarchy."
    )
    results = await _search(query, dataset)
    concepts: list[dict[str, Any]] = []
    for r in results:
        concepts.append({"name": r[:200], "raw": r})
    return concepts


async def get_exercise_concept_map(
    course_id: str,
    exercise_name: str,
) -> dict[str, Any]:
    """Map exercise questions to the concepts they test.

    Args:
        course_id: Course identifier.
        exercise_name: Name or number of the exercise sheet.

    Returns:
        Dict mapping exercise questions to concept names.
    """
    dataset = _dataset_name(course_id)
    logger.info(
        "cognee_exercise_map",
        course_id=course_id,
        exercise=exercise_name,
        dataset=dataset,
    )
    query = (
        f"Which core concepts and leaf concepts does exercise '{exercise_name}' test? "
        f"Map each exercise question to the specific concepts it covers."
    )
    results = await _search(query, dataset)
    return {"exercise": exercise_name, "concept_mappings": results}


async def get_quiz_material(
    course_id: str,
    core_concept: str,
) -> list[str]:
    """Get leaf concepts under a core concept for quiz generation.

    Args:
        course_id: Course identifier.
        core_concept: The core concept to drill into.

    Returns:
        List of leaf concept descriptions with definitions.
    """
    dataset = _dataset_name(course_id)
    logger.info(
        "cognee_quiz_material",
        course_id=course_id,
        concept=core_concept,
        dataset=dataset,
    )
    query = (
        f"List all leaf concepts under the core concept '{core_concept}'. "
        f"For each leaf concept, provide its precise definition and any key formulas or facts "
        f"that would be useful for generating quiz questions."
    )
    return await _search(query, dataset)


async def get_prerequisites(
    course_id: str,
    topic: str,
) -> list[str]:
    """Get prerequisite concepts for a topic.

    Args:
        course_id: Course identifier.
        topic: The topic to find prerequisites for.

    Returns:
        List of prerequisite concept descriptions.
    """
    dataset = _dataset_name(course_id)
    logger.info(
        "cognee_prerequisites",
        course_id=course_id,
        topic=topic,
        dataset=dataset,
    )
    query = (
        f"What prerequisite concepts are needed to understand '{topic}'? "
        f"List them in order from most fundamental to most advanced."
    )
    return await _search(query, dataset)


async def add_to_memory(
    *,
    user_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Ingest content into the knowledge graph via Cognee API.

    Args:
        user_id: Student identifier for namespace isolation.
        content: Text content to ingest.
        metadata: Optional metadata to attach.
    """
    settings = get_settings()
    logger.info("memory_add", user_id=user_id, content_length=len(content))

    import httpx

    url = f"{settings.cognee_api_url}/api/v1/add"
    headers = {"X-Api-Key": settings.cognee_api_key}
    payload = {
        "data": content,
        "dataset_name": f"student_{user_id}",
    }
    if metadata:
        payload["metadata"] = metadata  # type: ignore[assignment]

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()


async def query_memory(
    *,
    user_id: str,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Query the knowledge graph for relevant student context.

    Args:
        user_id: Student identifier for namespace isolation.
        query: Natural language query.
        top_k: Number of results to return.

    Returns:
        List of matching documents with content and metadata.
    """
    logger.info("memory_query", user_id=user_id, query=query, top_k=top_k)
    try:
        results = await _search(query)
        return [{"content": r, "source": "cognee"} for r in results[:top_k]]
    except CogneeRetrievalError:
        logger.warning("memory_query_fallback", user_id=user_id)
        return []
