"""Thesis matching via Cognee knowledge graph.

Pipeline:
1. Fetch thesis opportunities from TUMonline mock data
2. Ingest thesis descriptions into Cognee dataset "thesis_tum"
3. Build a student profile query (courses, grades, skills)
4. Query Cognee GRAPH_COMPLETION to find matching theses with reasoning
5. Fallback to Haiku-based matching if Cognee is unavailable
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from src.config import get_settings
from src.lib.logging import get_logger

logger = get_logger(__name__)

THESIS_DATASET = "thesis_tum"
_match_cache: list[dict[str, Any]] | None = None


async def _cognee_add(dataset: str, content: str, filename: str) -> bool:
    """Ingest a text document into a Cognee dataset."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.cognee_api_url}/api/v1/add",
                data={"datasetName": dataset},
                files=[("data", (filename, content.encode(), "text/plain"))],
                headers={"X-Api-Key": settings.cognee_api_key},
            )
            resp.raise_for_status()
            return True
    except Exception:
        logger.warning("cognee_add_failed", dataset=dataset, filename=filename, exc_info=True)
        return False


async def _cognee_cognify(datasets: list[str]) -> bool:
    """Trigger Cognee cognify on datasets."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.cognee_api_url}/api/v1/cognify",
                json={"datasets": datasets},
                headers={
                    "X-Api-Key": settings.cognee_api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return True
    except Exception:
        logger.warning("cognee_cognify_failed", datasets=datasets, exc_info=True)
        return False


async def _cognee_search(query: str, dataset: str) -> list[str]:
    """Search Cognee knowledge graph."""
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
        return texts
    except Exception:
        logger.warning("cognee_search_failed", dataset=dataset, exc_info=True)
        return []


async def ingest_theses(theses: list[dict[str, Any]]) -> int:
    """Ingest thesis listings into Cognee knowledge graph.

    Each thesis becomes a text document with topic, chair, professor, tags.
    Returns count of successfully ingested theses.
    """
    if not theses:
        return 0

    logger.info("thesis_ingest_start", count=len(theses))
    ingested = 0

    for thesis in theses:
        doc = (
            f"Thesis Topic: {thesis.get('topic', '')}\n"
            f"Chair: {thesis.get('chair', '')}\n"
            f"Professor: {thesis.get('professor_name', '')}\n"
            f"Description: {thesis.get('description', '')}\n"
            f"Tags: {', '.join(thesis.get('tags', []))}\n"
        )
        filename = f"thesis_{thesis.get('id', 'unknown')}.txt"
        if await _cognee_add(THESIS_DATASET, doc, filename):
            ingested += 1

    if ingested > 0:
        logger.info("thesis_ingest_cognify", count=ingested)
        await _cognee_cognify([THESIS_DATASET])

    logger.info("thesis_ingest_complete", ingested=ingested, total=len(theses))
    return ingested


def _build_profile_query(
    grades: list[dict[str, Any]],
    lectures: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    identity: dict[str, Any],
) -> str:
    """Build a rich natural language profile for Cognee graph query."""
    name = f"{identity.get('first_name', '')} {identity.get('last_name', '')}".strip()
    parts: list[str] = []

    parts.append(f"{name} is a M.Sc. Informatik student at TU Munich.")

    if grades:
        passed = [g for g in grades if g.get("grade_float") and g["grade_float"] <= 4.0]
        if passed:
            course_strs = [f"{g['title']} ({g['grade']})" for g in passed]
            parts.append(f"Completed courses: {', '.join(course_strs)}.")

    if lectures:
        lecture_names = [lec.get("title", "") for lec in lectures if lec.get("title")][:8]
        if lecture_names:
            parts.append(f"Currently enrolled in: {', '.join(lecture_names)}.")

    if skills:
        top = [s["name"] for s in skills[:10]]
        parts.append(f"Technical skills: {', '.join(top)}.")

    parts.append(
        "Looking for a thesis topic in AI, machine learning, software engineering, "
        "systems, or 3D computer vision at TUM."
    )

    return " ".join(parts)


async def match_theses_via_cognee(
    theses: list[dict[str, Any]],
    grades: list[dict[str, Any]],
    lectures: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    identity: dict[str, Any],
) -> list[dict[str, Any]]:
    """Match theses to student profile using Cognee knowledge graph.

    1. Ingest theses into Cognee (if not already done)
    2. Query with student profile
    3. Parse results and attach match scores
    4. Fall back to Haiku if Cognee fails
    """
    global _match_cache  # noqa: PLW0603
    has_profile = bool(grades or lectures or skills or identity.get("first_name"))
    if _match_cache is not None and has_profile:
        return _match_cache

    profile_query = _build_profile_query(grades, lectures, skills, identity)

    await ingest_theses(theses)

    logger.info("thesis_match_query_start")
    results = await _cognee_search(
        f"Based on this student profile, which thesis topics are the best match and why? "
        f"Rank by relevance and explain the connection.\n\n{profile_query}",
        THESIS_DATASET,
    )

    if results:
        matched = _parse_cognee_matches(theses, results)
        if matched:
            _match_cache = matched
            return matched

    logger.info("thesis_match_fallback_to_haiku")
    matched = await _match_via_haiku(theses, profile_query)
    _match_cache = matched
    return matched


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting (bold, italic, bullets, headers) from text."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-–•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _parse_cognee_matches(
    theses: list[dict[str, Any]],
    cognee_results: list[str],
) -> list[dict[str, Any]]:
    """Parse Cognee graph completion results and attach to thesis listings."""
    full_text = " ".join(cognee_results).lower()

    scored: list[dict[str, Any]] = []
    for thesis in theses:
        topic_lower = thesis.get("topic", "").lower()
        chair_lower = thesis.get("chair", "").lower()

        mentions = full_text.count(topic_lower[:30]) + full_text.count(chair_lower[:30])
        score = min(95, 40 + mentions * 15)

        reason = ""
        for result in cognee_results:
            if topic_lower[:20] in result.lower() or chair_lower[:20] in result.lower():
                sentences = result.split(".")
                for s in sentences:
                    if topic_lower[:20] in s.lower() or chair_lower[:20] in s.lower():
                        reason = _strip_markdown(s.strip()[:200])
                        break
                if reason:
                    break

        scored.append({
            "id": thesis.get("id", ""),
            "professor": thesis.get("professor_name", ""),
            "chair": thesis.get("chair", ""),
            "topic": thesis.get("topic", ""),
            "tags": thesis.get("tags", []),
            "source_url": thesis.get("source_url", ""),
            "match_score": score,
            "reasoning": reason or f"Relevant to your coursework at {thesis.get('chair', 'TUM')}.",
        })

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored


async def _match_via_haiku(
    theses: list[dict[str, Any]],
    profile: str,
) -> list[dict[str, Any]]:
    """Fallback: use Haiku to score theses against student profile."""
    from src.lib.bedrock import get_haiku_model_id, invoke_model

    theses_text = "\n".join(
        f"- [{i}] {t.get('topic', '')} at {t.get('chair', '')} "
        f"(Prof. {t.get('professor_name', '')})"
        for i, t in enumerate(theses[:10])
    )

    prompt = (
        f"Rate each thesis topic's relevance (0-100) for this student. "
        f"Return ONLY a JSON array of objects with index, score, reason.\n\n"
        f"Student: {profile}\n\nThesis topics:\n{theses_text}"
    )

    try:
        result = await invoke_model(
            model_id=get_haiku_model_id(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.0,
        )
        text = result.get("content", [{}])[0].get("text", "[]")
        start = text.find("[")
        end = text.rfind("]") + 1
        scores = json.loads(text[start:end]) if start >= 0 and end > start else []
    except Exception:
        logger.warning("haiku_thesis_match_failed", exc_info=True)
        scores = []

    score_map: dict[int, dict[str, Any]] = {}
    for s in scores:
        if isinstance(s, dict) and "index" in s:
            score_map[s["index"]] = s

    scored: list[dict[str, Any]] = []
    for i, thesis in enumerate(theses[:10]):
        match = score_map.get(i, {})
        scored.append({
            "id": thesis.get("id", ""),
            "professor": thesis.get("professor_name", ""),
            "chair": thesis.get("chair", ""),
            "topic": thesis.get("topic", ""),
            "tags": thesis.get("tags", []),
            "source_url": thesis.get("source_url", ""),
            "match_score": match.get("score", 50),
            "reasoning": match.get("reason", ""),
        })

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored
