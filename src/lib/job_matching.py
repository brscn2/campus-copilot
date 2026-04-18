"""Job matching via Cognee knowledge graph.

Pipeline:
1. Fetch jobs from SerpAPI
2. Ingest job descriptions into Cognee dataset "jobs_munich"
3. Build a rich student profile query (courses, grades, skills, experience)
4. Query Cognee GRAPH_COMPLETION to find matching jobs with reasoning
5. Fallback to Haiku-based matching if Cognee is unavailable
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from src.config import get_settings
from src.lib.logging import get_logger

logger = get_logger(__name__)

JOBS_DATASET = "jobs_munich"
_match_cache: dict[str, list[dict[str, Any]]] = {}


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


async def ingest_jobs(jobs: list[dict[str, Any]]) -> int:
    """Ingest job listings into Cognee knowledge graph.

    Each job becomes a text document with title, company, description, requirements.
    Returns count of successfully ingested jobs.
    """
    if not jobs:
        return 0

    logger.info("job_ingest_start", count=len(jobs))
    ingested = 0

    for job in jobs:
        doc = (
            f"Job Title: {job.get('title', '')}\n"
            f"Company: {job.get('company', '')}\n"
            f"Location: {job.get('location', '')}\n"
            f"Type: {job.get('kind', '')}\n"
            f"Salary: {job.get('salary', '')}\n"
            f"Description: {job.get('description', '')[:2000]}\n"
        )
        filename = f"job_{job.get('id', 'unknown')[:20]}.txt"
        if await _cognee_add(JOBS_DATASET, doc, filename):
            ingested += 1

    if ingested > 0:
        logger.info("job_ingest_cognify", count=ingested)
        await _cognee_cognify([JOBS_DATASET])

    logger.info("job_ingest_complete", ingested=ingested, total=len(jobs))
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
        "Looking for working student positions, internships, or entry-level roles "
        "in Munich related to AI, machine learning, software engineering, or 3D computer vision."
    )

    return " ".join(parts)


async def match_jobs_via_cognee(
    jobs: list[dict[str, Any]],
    grades: list[dict[str, Any]],
    lectures: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    identity: dict[str, Any],
    kind: str = "working_student",
) -> list[dict[str, Any]]:
    """Match jobs to student profile using Cognee knowledge graph.

    1. Ingest jobs into Cognee (if not already done)
    2. Query with student profile
    3. Parse results and attach match scores
    4. Fall back to Haiku if Cognee fails
    """
    has_profile = bool(grades or lectures or skills or identity.get("first_name"))
    if kind in _match_cache and has_profile:
        return _match_cache[kind]

    profile_query = _build_profile_query(grades, lectures, skills, identity)

    await ingest_jobs(jobs)

    logger.info("job_match_query_start", kind=kind)
    results = await _cognee_search(
        f"Based on this student profile, which jobs are the best match and why? "
        f"Rank by relevance and explain the connection.\n\n{profile_query}",
        JOBS_DATASET,
    )

    if results:
        matched = _parse_cognee_matches(jobs, results)
        if matched:
            _match_cache[kind] = matched
            return matched

    logger.info("job_match_fallback_to_haiku", kind=kind)
    matched = await _match_via_haiku(jobs, profile_query)
    _match_cache[kind] = matched
    return matched


def _parse_cognee_matches(
    jobs: list[dict[str, Any]],
    cognee_results: list[str],
) -> list[dict[str, Any]]:
    """Parse Cognee graph completion results and attach to job listings."""
    full_text = " ".join(cognee_results).lower()

    scored: list[dict[str, Any]] = []
    for job in jobs:
        title_lower = job.get("title", "").lower()
        company_lower = job.get("company", "").lower()

        mentions = full_text.count(title_lower[:30]) + full_text.count(company_lower)
        score = min(95, 40 + mentions * 15)

        reason = ""
        for result in cognee_results:
            if title_lower[:20] in result.lower() or company_lower in result.lower():
                sentences = result.split(".")
                for s in sentences:
                    if title_lower[:20] in s.lower() or company_lower in s.lower():
                        reason = s.strip()[:150]
                        break
                if reason:
                    break

        scored.append({
            **job,
            "match_score": score,
            "reasoning": reason or f"Matches your profile in {job.get('location', 'Munich')}.",
        })

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored


async def _match_via_haiku(
    jobs: list[dict[str, Any]],
    profile: str,
) -> list[dict[str, Any]]:
    """Fallback: use Haiku to score jobs against student profile."""
    from src.lib.bedrock import get_haiku_model_id, invoke_model

    jobs_text = "\n".join(
        f"- [{i}] {j.get('title', '')} at {j.get('company', '')} ({j.get('kind', '')})"
        for i, j in enumerate(jobs[:10])
    )

    prompt = (
        f"Rate each job's relevance (0-100) for this student. "
        f"Return ONLY a JSON array of objects with index, score, reason.\n\n"
        f"Student: {profile}\n\nJobs:\n{jobs_text}"
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
        if start >= 0 and end > start:
            scores = json.loads(text[start:end])
        else:
            scores = []
    except Exception:
        logger.warning("haiku_job_match_failed", exc_info=True)
        scores = []

    score_map: dict[int, dict[str, Any]] = {}
    for s in scores:
        if isinstance(s, dict) and "index" in s:
            score_map[s["index"]] = s

    scored: list[dict[str, Any]] = []
    for i, job in enumerate(jobs[:10]):
        match = score_map.get(i, {})
        scored.append({
            **job,
            "match_score": match.get("score", 50),
            "reasoning": match.get("reason", ""),
        })

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored
