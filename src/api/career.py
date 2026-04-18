"""REST endpoints for the Career tab — jobs, CV audit."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.integrations.jobs import search_jobs

router = APIRouter(prefix="/career", tags=["career"])


@router.get("/jobs")
async def list_jobs(
    kind: str | None = None,
    keywords: str | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Search job listings."""
    kw_list = keywords.split(",") if keywords else None
    return await search_jobs(kind=kind, keywords=kw_list, company=company, location=location)
