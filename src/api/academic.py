"""REST endpoints for the Academic tab — courses, uploads, thesis, rooms."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.integrations.library import search_rooms
from src.integrations.moodle import get_courses, get_uploads
from src.integrations.tumonline import search_thesis_opportunities

router = APIRouter(prefix="/academic", tags=["academic"])


@router.get("/courses")
async def list_courses(semester: str | None = None) -> list[dict[str, Any]]:
    """List enrolled Moodle courses, optionally filtered by semester."""
    return await get_courses(semester=semester)


@router.get("/courses/{course_id}/uploads")
async def list_uploads(course_id: str) -> list[dict[str, Any]]:
    """List resources/uploads for a Moodle course."""
    return await get_uploads(moodle_course_id=course_id)


@router.get("/thesis")
async def list_thesis(
    keywords: str | None = None,
    chair: str | None = None,
    tags: str | None = None,
) -> list[dict[str, Any]]:
    """Search thesis opportunities."""
    kw_list = keywords.split(",") if keywords else None
    tag_list = tags.split(",") if tags else None
    return await search_thesis_opportunities(keywords=kw_list, chair=chair, tags=tag_list)


@router.get("/rooms")
async def list_rooms(
    date: str = "2026-04-18",
    duration_hours: int = 2,
    capacity: int = 1,
    building: str | None = None,
) -> list[dict[str, Any]]:
    """Search available library study rooms."""
    return await search_rooms(
        date=date, duration_hours=duration_hours, capacity=capacity, building=building
    )
