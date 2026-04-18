"""Pure-function tools for the Career agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.integrations.jobs import search_jobs as _search_jobs


@tool
async def search_jobs(
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Search for job listings — working student, internship, or new grad roles.

    Args:
        kind: Type filter — 'working_student', 'internship', or 'new_grad'.
        keywords: Keywords to match against title/description (e.g. ['machine learning']).
        company: Company name filter (e.g. 'BMW').
        location: Location filter (e.g. 'Munich').
    """
    return await _search_jobs(
        kind=kind,
        keywords=keywords,
        company=company,
        location=location,
    )
