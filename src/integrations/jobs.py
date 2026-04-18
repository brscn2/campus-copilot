"""Job board integration — SerpAPI Google Jobs (live) or mock data (dev/fallback).

In live mode, queries SerpAPI's Google Jobs engine for real listings.
In mock mode (or on SerpAPI failure), returns curated sample data.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.config import get_settings
from src.exceptions import JobSearchError
from src.lib.logging import get_logger
from src.lib.retry import retry_external

logger = get_logger(__name__)

SERPAPI_BASE_URL = "https://serpapi.com/search.json"
SERPAPI_TIMEOUT = 15.0

KIND_QUERY_MAP: dict[str, str] = {
    "working_student": "(Werkstudent OR working student)",
    "internship": "(Praktikum OR internship)",
    "new_grad": "junior developer",
}

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


def _build_query(
    *,
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> str:
    """Build the SerpAPI ``q`` parameter from search filters."""
    parts: list[str] = []

    if kind and kind in KIND_QUERY_MAP:
        parts.append(KIND_QUERY_MAP[kind])

    if keywords:
        parts.extend(keywords)

    if company:
        parts.append(company)

    if not parts:
        parts.append("student jobs")

    city = (location or "Munich").split(",")[0].strip()
    parts.append(city)

    return " ".join(parts)


def _infer_kind(title: str, extensions: list[str] | None) -> str:
    """Classify a SerpAPI result into working_student / internship / new_grad."""
    searchable = title.lower()
    if extensions:
        searchable += " " + " ".join(e.lower() for e in extensions)

    if any(term in searchable for term in ("werkstudent", "working student")):
        return "working_student"
    if any(term in searchable for term in ("praktikum", "internship", "intern ")):
        return "internship"

    return "new_grad"


def _map_serpapi_result(item: dict[str, Any], fallback_kind: str | None) -> dict[str, Any]:
    """Map a single SerpAPI ``jobs_results`` entry to the project's job schema."""
    detected = item.get("detected_extensions") or {}
    extensions = item.get("extensions") or []

    apply_options = item.get("apply_options") or []
    source_url = apply_options[0]["link"] if apply_options else ""

    inferred_kind = _infer_kind(item.get("title", ""), extensions)
    kind = fallback_kind if fallback_kind and inferred_kind == "new_grad" else inferred_kind

    return {
        "id": item.get("job_id", ""),
        "company": item.get("company_name", ""),
        "title": item.get("title", ""),
        "kind": kind,
        "location": item.get("location", ""),
        "salary": detected.get("salary", ""),
        "description": item.get("description", ""),
        "source_url": source_url,
        "posted_at": detected.get("posted_at", ""),
    }


@retry_external()  # type: ignore[untyped-decorator]
async def _search_serpapi(
    *,
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Query SerpAPI Google Jobs and return mapped results."""
    settings = get_settings()
    loc = location or "Munich, Bavaria, Germany"
    query = _build_query(kind=kind, keywords=keywords, company=company, location=loc)

    params: dict[str, str] = {
        "engine": "google_jobs",
        "q": query,
        "location": loc,
        "gl": "de",
        "hl": "en",
        "api_key": settings.serpapi_api_key,
    }

    logger.info("serpapi_request", query=query, location=loc, kind=kind)

    try:
        async with httpx.AsyncClient(timeout=SERPAPI_TIMEOUT) as client:
            resp = await client.get(SERPAPI_BASE_URL, params=params)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("serpapi_http_error", status_code=exc.response.status_code)
        raise JobSearchError(f"SerpAPI returned {exc.response.status_code}") from exc
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("serpapi_connection_error", exc_info=True)
        raise JobSearchError("SerpAPI unreachable") from exc

    data = resp.json()
    raw_jobs: list[dict[str, Any]] = data.get("jobs_results") or []

    logger.info("serpapi_response", result_count=len(raw_jobs))

    return [_map_serpapi_result(item, fallback_kind=kind) for item in raw_jobs]


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


async def search_jobs(
    *,
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Search for job listings — working student, internship, or new grad roles.

    Routes to SerpAPI in live mode, falls back to mock data on failure.

    Args:
        kind: Filter by type — 'working_student', 'internship', 'new_grad'.
        keywords: Keywords to match against title/description.
        company: Company name filter substring.
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

    if settings.jobs_mode == "live":
        if not settings.serpapi_api_key:
            logger.warning("serpapi_key_missing", fallback="mock")
            return await _search_mock(
                kind=kind, keywords=keywords, company=company, location=location
            )

        try:
            results: list[dict[str, Any]] = await _search_serpapi(
                kind=kind, keywords=keywords, company=company, location=location
            )
            if kind:
                filtered = [r for r in results if r.get("kind") == kind]
                if filtered:
                    results = filtered
            if results:
                return results
            logger.warning("serpapi_empty_results_fallback_to_mock", kind=kind)
            return await _search_mock(
                kind=kind, keywords=keywords, company=company, location=location
            )
        except JobSearchError:
            logger.warning("serpapi_failed_fallback_to_mock", exc_info=True)
            return await _search_mock(
                kind=kind, keywords=keywords, company=company, location=location
            )

    return await _search_mock(kind=kind, keywords=keywords, company=company, location=location)
