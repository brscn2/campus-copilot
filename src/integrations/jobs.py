"""Mock job board integration — working student, internship, new grad listings.

In live mode this would scrape TUM job board, LinkedIn, etc.
For the hackathon demo, returns curated fake data.
"""

from __future__ import annotations

from typing import Any

from src.lib.logging import get_logger

logger = get_logger(__name__)

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


async def search_jobs(
    *,
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Search for job listings.

    Args:
        kind: Filter by type — 'working_student', 'internship', 'new_grad'.
        keywords: Keywords to match against title/description.
        company: Company name filter substring.
        location: Location filter substring.

    Returns:
        List of matching job dicts.
    """
    logger.info(
        "jobs_search",
        kind=kind,
        keywords=keywords,
        company=company,
        location=location,
    )

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
