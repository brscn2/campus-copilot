"""Job board integration — TheirStack Job Search (live) or mock data (dev/fallback).

In live mode, queries TheirStack's POST /v1/jobs/search endpoint for structured
listings filtered by country, employment status, seniority, and (optionally)
keywords/company. In mock mode (or on TheirStack failure / empty result), falls
back to curated sample data so the demo always has something to show.

TheirStack returns first-class structured fields (employment_statuses, seniority,
salary_string, technology_slugs) — far cleaner than the previous SerpAPI Google
Jobs scrape. See https://api.theirstack.com/en/docs/api-reference/jobs/search_jobs_v1
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

from src.config import get_settings
from src.exceptions import JobSearchError
from src.lib.logging import get_logger
from src.lib.retry import retry_external

logger = get_logger(__name__)

THEIRSTACK_BASE_URL = "https://api.theirstack.com/v1/jobs/search"
THEIRSTACK_TIMEOUT = 20.0
THEIRSTACK_DEFAULT_LIMIT = 10
THEIRSTACK_MAX_AGE_DAYS = 30

EUROPE_COUNTRY_CODES = [
    "DE",
    "AT",
    "CH",
    "NL",
    "GB",
    "IE",
    "FR",
    "SE",
    "DK",
    "NO",
    "FI",
    "BE",
    "LU",
    "ES",
    "IT",
    "PT",
    "PL",
    "CZ",
]
IN_MEMORY_CACHE_TTL_SECONDS = 600

WERKSTUDENT_PATTERN = re.compile(r"werkstudent|working student", re.IGNORECASE)
MUNICH_PATTERN = re.compile(r"munich|münchen", re.IGNORECASE)

# (kind, keywords_tuple, company, location) -> (expires_at_epoch, results)
_search_cache: dict[tuple[str, tuple[str, ...], str, str], tuple[float, list[dict[str, Any]]]] = {}


MOCK_JOBS: list[dict[str, Any]] = [
    {
        "id": "job-001",
        "company": "BMW Group",
        "title": "Working Student — Autonomous Driving Simulation",
        "kind": "working_student",
        "location": "Munich",
        "salary": "15-18 €/hr",
        "description": (
            "Support the AD simulation team in developing and validating "
            "scenarios for autonomous driving using CARLA and internal tools. "
            "Python, C++ experience required."
        ),
        "source_url": "https://jobs.bmw.com/ws-ad-sim",
        "posted_at": "2026-04-10",
    },
    {
        "id": "job-002",
        "company": "Celonis",
        "title": "Working Student — Machine Learning Platform",
        "kind": "working_student",
        "location": "Munich",
        "salary": "16-20 €/hr",
        "description": (
            "Join the ML platform team building scalable training and inference "
            "pipelines. Work with Kubernetes, Ray, and MLflow. Python and "
            "cloud experience preferred."
        ),
        "source_url": "https://celonis.com/careers/ws-ml-platform",
        "posted_at": "2026-04-12",
    },
    {
        "id": "job-003",
        "company": "Siemens",
        "title": "Internship — Digital Twin Research",
        "kind": "internship",
        "location": "Munich",
        "salary": "1800 €/month",
        "description": (
            "6-month internship in the Digital Twin research group. Build "
            "simulation models for industrial IoT systems. Background in "
            "control systems or physics-based modeling preferred."
        ),
        "source_url": "https://siemens.com/intern-digital-twin",
        "posted_at": "2026-04-08",
    },
    {
        "id": "job-004",
        "company": "Google Munich",
        "title": "Working Student — Cloud Infrastructure SRE",
        "kind": "working_student",
        "location": "Munich",
        "salary": "20-25 €/hr",
        "description": (
            "Support the SRE team maintaining Google Cloud infrastructure. "
            "Monitoring, incident response, and automation with Go and Python. "
            "Strong Linux and networking fundamentals required."
        ),
        "source_url": "https://careers.google.com/ws-sre-munich",
        "posted_at": "2026-04-15",
    },
    {
        "id": "job-005",
        "company": "Reply",
        "title": "New Grad — AI Consultant",
        "kind": "new_grad",
        "location": "Munich",
        "salary": "55-65k €/year",
        "description": (
            "Join Reply's AI practice as a consultant. Work on enterprise "
            "AI projects across industries — NLP, computer vision, and "
            "generative AI. TUM graduates preferred."
        ),
        "source_url": "https://reply.com/careers/ai-consultant",
        "posted_at": "2026-04-14",
    },
]


def _build_theirstack_payload(
    *,
    kind: str | None,
    keywords: list[str] | None,
    company: str | None,
    location: str | None,
    limit: int = THEIRSTACK_DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Build the JSON body for POST /v1/jobs/search.

    Maps our three job kinds to TheirStack's structured filters:
      - internship   -> employment_statuses_or=['internship']
      - working_student -> employment_statuses_or=['part_time']
                            + job_title_pattern_or=Werkstudent regex
      - new_grad     -> employment_statuses_or=['full_time']
                            + job_seniority_or=['junior']

    Always restricts to DE and the last 30 days (the API requires at least one
    date or company filter). ``limit`` is the page size; on the free TheirStack
    plan each returned job costs 1 credit, so keep it low for demo iteration.
    """
    payload: dict[str, Any] = {
        "page": 0,
        "limit": limit,
        "include_total_results": False,
        "posted_at_max_age_days": THEIRSTACK_MAX_AGE_DAYS,
        "job_country_code_or": EUROPE_COUNTRY_CODES,
    }

    if kind == "internship":
        payload["employment_statuses_or"] = ["internship"]
    elif kind == "working_student":
        payload["employment_statuses_or"] = ["part_time"]
        payload["job_title_pattern_or"] = [
            "(?i)werkstudent",
            "(?i)working student",
        ]
    elif kind == "new_grad":
        payload["employment_statuses_or"] = ["full_time"]
        payload["job_seniority_or"] = ["junior"]

    description_terms: list[str] = []
    if keywords:
        description_terms.extend(k for k in keywords if k.strip())

    if description_terms:
        payload["job_description_contains_or"] = description_terms

    if company:
        payload["company_name_case_insensitive_or"] = [company]

    return payload


def _format_salary(item: dict[str, Any]) -> str:
    """Build a fallback salary string from min/max/currency when salary_string is empty."""
    lo = item.get("min_annual_salary")
    hi = item.get("max_annual_salary")
    cur = item.get("salary_currency") or ""
    if lo and hi:
        return f"{lo:.0f}-{hi:.0f} {cur}".strip()
    if lo:
        return f"from {lo:.0f} {cur}".strip()
    if hi:
        return f"up to {hi:.0f} {cur}".strip()
    return ""


def _resolve_kind(item: dict[str, Any], requested_kind: str | None) -> str:
    """Derive our kind from TheirStack's structured fields, with sensible fallbacks."""
    statuses = [s for s in (item.get("employment_statuses") or []) if isinstance(s, str)]
    seniority = item.get("seniority") or ""
    title = item.get("job_title") or ""

    if "internship" in statuses or "apprenticeship" in statuses:
        return "internship"
    if WERKSTUDENT_PATTERN.search(title) or (
        "part_time" in statuses and "werkstudent" in title.lower()
    ):
        return "working_student"
    if "part_time" in statuses and requested_kind == "working_student":
        return "working_student"
    if seniority == "junior" and "full_time" in statuses:
        return "new_grad"

    if requested_kind in ("working_student", "internship", "new_grad"):
        return requested_kind
    return "new_grad"


def _map_theirstack_result(item: dict[str, Any], requested_kind: str | None) -> dict[str, Any]:
    """Map a single TheirStack response item into our internal job dict shape."""
    company_obj = item.get("company_object") or {}
    company_name = (
        (company_obj.get("name") if isinstance(company_obj, dict) else None)
        or item.get("company")
        or ""
    )

    description = item.get("description") or ""
    salary = item.get("salary_string") or _format_salary(item)

    return {
        "id": str(item.get("id", "")),
        "company": company_name,
        "title": item.get("job_title", ""),
        "kind": _resolve_kind(item, requested_kind),
        "location": item.get("long_location") or item.get("location") or "",
        "salary": salary,
        "description": description[:4000],
        "source_url": item.get("final_url") or item.get("url", ""),
        "posted_at": item.get("date_posted", ""),
    }


@retry_external()  # type: ignore[untyped-decorator]
async def _search_theirstack(
    *,
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Query TheirStack Job Search and return mapped results."""
    settings = get_settings()
    payload = _build_theirstack_payload(
        kind=kind,
        keywords=keywords,
        company=company,
        location=location,
        limit=settings.theirstack_results_per_call,
    )
    headers = {
        "Authorization": f"Bearer {settings.theirstack_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    logger.info(
        "theirstack_request",
        kind=kind,
        keywords=keywords,
        company=company,
        location=location,
    )

    try:
        async with httpx.AsyncClient(timeout=THEIRSTACK_TIMEOUT) as client:
            resp = await client.post(THEIRSTACK_BASE_URL, json=payload, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("theirstack_http_error", status_code=exc.response.status_code)
        raise JobSearchError(f"TheirStack returned {exc.response.status_code}") from exc
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("theirstack_connection_error", exc_info=True)
        raise JobSearchError("TheirStack unreachable") from exc

    body = resp.json()
    raw_jobs: list[dict[str, Any]] = body.get("data") or []

    logger.info("theirstack_response", result_count=len(raw_jobs))

    mapped = [_map_theirstack_result(item, requested_kind=kind) for item in raw_jobs]
    return mapped


async def _search_mock(
    *,
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Filter mock job data — used in dev mode and as live-mode fallback."""
    results: list[dict[str, Any]] = []
    for job in MOCK_JOBS:
        if kind and job["kind"] != kind:
            continue
        if company and company.lower() not in job["company"].lower():
            continue
        if location and location.lower() not in job["location"].lower():
            continue
        if keywords:
            text = f"{job['title']} {job['description']}".lower()
            if not any(kw.lower() in text for kw in keywords):
                continue
        results.append(job)
    return results


def _cache_key(
    kind: str | None,
    keywords: list[str] | None,
    company: str | None,
    location: str | None,
) -> tuple[str, tuple[str, ...], str, str]:
    return (
        kind or "",
        tuple(sorted(keywords)) if keywords else (),
        company or "",
        location or "",
    )


def _disk_cache_path(key: tuple[str, tuple[str, ...], str, str], cache_dir: str) -> Path:
    """Resolve the on-disk JSON path for a given cache key."""
    payload = json.dumps(list(key), sort_keys=True)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return Path(cache_dir) / f"{digest}.json"


def _disk_cache_read(
    key: tuple[str, tuple[str, ...], str, str],
    cache_dir: str,
    ttl_seconds: int,
) -> list[dict[str, Any]] | None:
    """Return cached results if fresh, else None. Best-effort: any I/O error -> miss."""
    try:
        path = _disk_cache_path(key, cache_dir)
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


def _disk_cache_write(
    key: tuple[str, tuple[str, ...], str, str],
    cache_dir: str,
    value: list[dict[str, Any]],
) -> None:
    """Persist results to disk. Best-effort: silently swallow I/O errors."""
    try:
        path = _disk_cache_path(key, cache_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError, TypeError):
        return


def _keyword_batches(
    keywords: list[str] | None,
    batch_size: int = 3,
) -> list[list[str] | None]:
    """Split a keyword list into batches for multiple TheirStack calls.

    Each batch becomes one API call. With batch_size=3 and 8 keywords,
    we get 3 calls: [kw0..2], [kw3..5], [kw6..7]. This diversity in
    search terms produces a broader, more varied candidate pool (~30 jobs)
    while each individual call stays within the per-call limit.
    """
    if not keywords:
        return [None]
    batches: list[list[str] | None] = []
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i : i + batch_size]
        if batch:
            batches.append(batch)
    return batches or [None]


def _deduplicate_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate jobs by ID, keeping first occurrence."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for job in jobs:
        jid = job.get("id", "")
        if jid and jid in seen:
            continue
        if jid:
            seen.add(jid)
        unique.append(job)
    return unique


async def search_jobs(
    *,
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Search for job listings — working student, internship, or new grad roles.

    Makes multiple TheirStack calls with keyword batches to build a pool
    of ~30 candidates, deduplicates by job ID, and caches the merged result.

    Live results are cached in two layers to conserve TheirStack credits
    (1 credit per job returned on the free tier):

    1. **In-process cache** (10 min) — hot path for back-to-back UI clicks.
    2. **Disk cache** (default 24 h) — survives uvicorn restarts.

    Args:
        kind: Filter by type — 'working_student', 'internship', 'new_grad'.
        keywords: Keywords to match against job descriptions.
        company: Company name filter (case-insensitive).
        location: Location filter substring.

    Returns:
        List of matching job dicts.
    """
    settings = get_settings()

    logger.info(
        "jobs_search",
        mode=settings.jobs_mode,
        kind=kind,
        keywords=keywords,
        company=company,
        location=location,
    )

    if settings.jobs_mode != "live":
        return await _search_mock(kind=kind, keywords=keywords, company=company, location=location)

    if not settings.theirstack_api_key:
        logger.warning("theirstack_key_missing", fallback="mock")
        return await _search_mock(kind=kind, keywords=keywords, company=company, location=location)

    key = _cache_key(kind, keywords, company, location)
    now = time.monotonic()
    cached = _search_cache.get(key)
    if cached and cached[0] > now:
        logger.info("theirstack_cache_hit", kind=kind, layer="memory")
        return cached[1]

    disk_hit = _disk_cache_read(
        key, settings.theirstack_cache_dir, settings.theirstack_cache_ttl_seconds
    )
    if disk_hit:
        logger.info("theirstack_cache_hit", kind=kind, layer="disk", count=len(disk_hit))
        _search_cache[key] = (now + IN_MEMORY_CACHE_TTL_SECONDS, disk_hit)
        return disk_hit

    batches = _keyword_batches(keywords)
    all_results: list[dict[str, Any]] = []

    for i, batch in enumerate(batches):
        if i > 0:
            await asyncio.sleep(1.0)
        try:
            batch_results = await _search_theirstack(
                kind=kind, keywords=batch, company=company, location=location
            )
            if kind:
                filtered = [r for r in batch_results if r.get("kind") == kind]
                if filtered:
                    batch_results = filtered
            all_results.extend(batch_results)
        except JobSearchError:
            logger.warning(
                "theirstack_batch_failed",
                batch=batch,
                exc_info=True,
            )

    results = _deduplicate_jobs(all_results)
    logger.info(
        "theirstack_multi_batch_complete",
        batches=len(batches),
        total_raw=len(all_results),
        deduplicated=len(results),
    )

    if results:
        _search_cache[key] = (now + IN_MEMORY_CACHE_TTL_SECONDS, results)
        _disk_cache_write(key, settings.theirstack_cache_dir, results)
        return results

    logger.warning("theirstack_empty_results_fallback_to_mock", kind=kind)
    return await _search_mock(kind=kind, keywords=keywords, company=company, location=location)
