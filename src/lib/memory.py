"""Cognee Cloud memory layer — cogwit SDK for course queries, HTTP for student memory."""

from __future__ import annotations

import os
from typing import Any

import httpx
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
    """Run a GRAPH_COMPLETION search and return result strings.

    Uses the raw HTTP API when a dataset is specified (cogwit SDK doesn't
    support dataset-scoped queries), falls back to cogwit SDK otherwise.
    """
    if dataset is not None:
        return await _search_via_http(query, dataset)

    client = _get_client()
    try:
        search_kwargs: dict[str, Any] = {
            "query_text": query,
            "query_type": client.SearchType.GRAPH_COMPLETION,
        }
        if dataset is not None:
            search_kwargs["dataset"] = dataset
        results = await client.search(**search_kwargs)
        texts: list[str] = []
        for r in results:
            text = str(r.search_result) if hasattr(r, "search_result") else str(r)
            if len(text) > 10:
                texts.append(text)
        return texts
    except Exception as exc:
        logger.error("cognee_search_failed", query=query, exc_info=True)
        raise CogneeRetrievalError(f"Cognee search failed: {exc}") from exc


async def _search_via_http(query: str, dataset: str) -> list[str]:
    """Search Cognee via raw HTTP API with dataset scoping."""
    import httpx

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.cognee_api_url}/api/v1/search",
                json={
                    "query": query,
                    "search_type": "GRAPH_COMPLETION",
                    "datasets": [dataset],
                },
                headers={"X-Api-Key": settings.cognee_api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        texts: list[str] = []
        if isinstance(data, list):
            for item in data:
                text = str(item.get("search_result", item)) if isinstance(item, dict) else str(item)
                if len(text) > 10:
                    texts.append(text)
        elif isinstance(data, dict):
            for value in data.values():
                text = str(value)
                if len(text) > 10:
                    texts.append(text)

        logger.info("cognee_http_search_done", dataset=dataset, results=len(texts))
        return texts
    except Exception as exc:
        logger.error("cognee_http_search_failed", query=query, dataset=dataset, exc_info=True)
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
        "Return as a structured JSON hierarchy."
    )
    results = await _search(query, dataset)
    concepts: list[dict[str, Any]] = []

    for r in results:
        parsed = _try_parse_concepts_json(r)
        if parsed:
            concepts.extend(parsed)
        else:
            concepts.append({"name": r[:200], "sub_concepts": [], "leaf_concepts": [], "raw": r})

    logger.info("cognee_concepts_parsed", course_id=course_id, count=len(concepts))
    return concepts


def _try_parse_concepts_json(raw: str) -> list[dict[str, Any]] | None:
    """Try to parse a Cognee GRAPH_COMPLETION response as structured concept JSON.

    Cognee returns concept hierarchies wrapped in Python list repr like:
      ['{"Concept A": {"sub_concepts": [...], "leaf_concepts": [...]}}']
    This function unwraps and splits that into individual concept dicts.
    """
    import ast
    import json

    text = raw.strip()

    # Cognee wraps responses in Python list repr: ['{ json }']
    # Try ast.literal_eval first to unwrap cleanly
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed_list = ast.literal_eval(text)
            if isinstance(parsed_list, list) and parsed_list:
                text = str(parsed_list[0])
        except (ValueError, SyntaxError):
            text = text[1:-1].strip()
            if text.startswith("'") and text.endswith("'"):
                text = text[1:-1]

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    concepts: list[dict[str, Any]] = []
    for name, details in data.items():
        if not isinstance(details, dict):
            continue
        concepts.append(
            {
                "name": name,
                "sub_concepts": details.get("sub_concepts", []),
                "leaf_concepts": details.get("leaf_concepts", []),
                "raw": json.dumps({name: details}),
            }
        )
    return concepts if concepts else None


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

    url = f"{settings.cognee_api_url}/api/v1/add"
    headers = {"X-Api-Key": settings.cognee_api_key}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            data={"datasetName": f"student_{user_id}"},
            files=[("data", ("content.txt", content.encode(), "text/plain"))],
            headers=headers,
        )
        resp.raise_for_status()


async def query_memory(
    *,
    user_id: str,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Query the knowledge graph for relevant student context.

    Uses the HTTP API with dataset scoping so results are isolated to this
    student's memory, not the entire tenant.

    Args:
        user_id: Student identifier for namespace isolation.
        query: Natural language query.
        top_k: Number of results to return.

    Returns:
        List of matching documents with content and metadata.
    """
    logger.info("memory_query", user_id=user_id, query=query, top_k=top_k)
    dataset = f"student_{user_id}"
    try:
        results = await _search(query, dataset=dataset)
        return [{"content": r, "source": "cognee"} for r in results[:top_k]]
    except CogneeRetrievalError:
        logger.warning("memory_query_fallback", user_id=user_id)
        return []
