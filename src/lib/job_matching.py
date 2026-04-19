"""Job matching via Haiku LLM scoring with Cognee knowledge graph ingestion.

Pipeline:
1. Fetch jobs from TheirStack (via search_jobs)
2. Ingest job descriptions into Cognee dataset "jobs_munich" (for knowledge graph)
3. Build a rich student profile query (courses, grades, skills with proficiency)
4. Score jobs against profile via Haiku LLM
5. Cache scored results in memory (10 min) + disk (4 h)
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from src.config import get_settings
from src.lib.logging import get_logger

logger = get_logger(__name__)

JOBS_DATASET = "jobs_munich"

# (kind) -> (expires_at_monotonic, scored_results)
_match_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
MATCH_MEMORY_TTL_SECONDS = 600

HAIKU_MATCH_PROMPT = (
    "You are a career advisor at TU Munich. "
    "Rate each job's relevance for this student.\n\n"
    "## Scoring bands (use the FULL range, differentiate clearly)\n"
    "- 85-95: Direct skill overlap — job requires skills the student demonstrated\n"
    "- 70-84: Strong adjacent fit — related field, most required skills present\n"
    "- 50-69: Moderate fit — some skill overlap but missing key requirements\n"
    "- 30-49: Weak fit — tangential connection to student's background\n"
    "- 10-29: Poor fit — little to no relevance\n\n"
    "IMPORTANT: Vary your scores. No two jobs should receive the same score "
    "unless truly identical in fit. Spread scores across a 30-point range.\n\n"
    "## Student Profile\n{profile}\n\n"
    "## Jobs\n{jobs_text}\n\n"
    'Return ONLY a JSON array. Each element: '
    '{{"index": <int>, "score": <int 10-95>, '
    '"reason": "<one sentence explaining the match>"}}'
)


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
    """Build a rich natural language profile for LLM scoring."""
    name = f"{identity.get('first_name', '')} {identity.get('last_name', '')}".strip()
    parts: list[str] = []

    parts.append(f"{name} is a M.Sc. Informatik student at TU Munich.")

    if grades:
        passed = [g for g in grades if g.get("grade_float") and g["grade_float"] <= 4.0]
        if passed:
            course_strs = [f"{g['title']} (grade: {g['grade']})" for g in passed]
            parts.append(f"Completed courses: {', '.join(course_strs)}.")

    if lectures:
        lecture_names = [lec.get("title", "") for lec in lectures if lec.get("title")][:8]
        if lecture_names:
            parts.append(f"Currently enrolled in: {', '.join(lecture_names)}.")

    if skills:
        skill_strs = [f"{s['name']} ({s.get('level', '?')}%)" for s in skills[:10]]
        parts.append(f"Technical skills with proficiency: {', '.join(skill_strs)}.")

    return " ".join(parts)


def _build_match_cache_key(
    kind: str,
    skills: list[dict[str, Any]],
    grades: list[dict[str, Any]],
) -> str:
    """Build a stable cache key that captures profile essence."""
    skill_names = sorted(s.get("name", "") for s in skills[:10])
    course_codes = sorted(
        g.get("course_code", "") for g in grades if g.get("grade_float", 5.0) <= 4.0
    )
    raw = json.dumps([kind, skill_names, course_codes], sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _disk_match_read(
    cache_key: str, cache_dir: str, ttl_seconds: int
) -> list[dict[str, Any]] | None:
    """Return cached match results if fresh, else None."""
    try:
        path = Path(cache_dir) / f"{cache_key}.json"
        if not path.is_file():
            return None
        if time.time() - path.stat().st_mtime > ttl_seconds:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return None
    except (OSError, ValueError, TypeError):
        return None


def _disk_match_write(
    cache_key: str,
    cache_dir: str,
    value: list[dict[str, Any]],
) -> None:
    """Persist match results to disk. Best-effort."""
    try:
        path = Path(cache_dir) / f"{cache_key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError, TypeError):
        return


async def _match_via_haiku(
    jobs: list[dict[str, Any]],
    profile: str,
) -> list[dict[str, Any]]:
    """Score jobs against student profile using Haiku LLM."""
    from src.lib.bedrock import get_haiku_model_id, invoke_model

    jobs_text = "\n\n".join(
        f"[{i}] {j.get('title', '')} at {j.get('company', '')} ({j.get('kind', '')})\n"
        f"    Location: {j.get('location', '')}\n"
        f"    Description: {j.get('description', '')[:500]}"
        for i, j in enumerate(jobs[:15])
    )

    prompt = HAIKU_MATCH_PROMPT.format(profile=profile, jobs_text=jobs_text)

    try:
        result = await invoke_model(
            model_id=get_haiku_model_id(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.1,
        )
        text = result.get("content", [{}])[0].get("text", "[]")
        start = text.find("[")
        end = text.rfind("]") + 1
        scores = json.loads(text[start:end]) if start >= 0 and end > start else []
    except Exception:
        logger.warning("haiku_job_match_failed", exc_info=True)
        scores = []

    score_map: dict[int, dict[str, Any]] = {}
    for s in scores:
        if isinstance(s, dict) and "index" in s:
            score_map[s["index"]] = s

    scored: list[dict[str, Any]] = []
    for i, job in enumerate(jobs[:15]):
        match = score_map.get(i, {})
        scored.append(
            {
                **job,
                "match_score": match.get("score", 50),
                "reasoning": match.get("reason", ""),
            }
        )

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored


async def match_jobs_via_cognee(
    jobs: list[dict[str, Any]],
    grades: list[dict[str, Any]],
    lectures: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    identity: dict[str, Any],
    kind: str = "working_student",
) -> list[dict[str, Any]]:
    """Match jobs to student profile using Haiku LLM scoring.

    1. Check memory + disk cache
    2. Build student profile
    3. Ingest jobs into Cognee (for knowledge graph, not scoring)
    4. Score via Haiku LLM
    5. Cache results in memory + disk
    """
    settings = get_settings()
    cache_key = _build_match_cache_key(kind, skills, grades)

    now = time.monotonic()
    mem_cached = _match_cache.get(cache_key)
    if mem_cached and mem_cached[0] > now:
        logger.info("match_cache_hit", kind=kind, layer="memory")
        return mem_cached[1]

    disk_hit = _disk_match_read(
        cache_key, settings.match_cache_dir, settings.match_cache_ttl_seconds
    )
    if disk_hit:
        logger.info("match_cache_hit", kind=kind, layer="disk", count=len(disk_hit))
        _match_cache[cache_key] = (now + MATCH_MEMORY_TTL_SECONDS, disk_hit)
        return disk_hit

    profile_query = _build_profile_query(grades, lectures, skills, identity)

    try:
        await ingest_jobs(jobs)
    except Exception:
        logger.warning("job_ingest_best_effort_failed", exc_info=True)

    logger.info("job_match_scoring_start", kind=kind, job_count=len(jobs))
    matched = await _match_via_haiku(jobs, profile_query)

    _match_cache[cache_key] = (now + MATCH_MEMORY_TTL_SECONDS, matched)
    _disk_match_write(cache_key, settings.match_cache_dir, matched)

    return matched
