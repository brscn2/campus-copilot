"""REST endpoints for the Academic tab — courses, uploads, thesis, rooms."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.config import DEMO_STUDENT_ID, get_settings
from src.integrations.library import (
    book_room,
    list_library_branches,
    search_rooms,
    verify_booking,
)
from src.integrations.moodle import get_courses, get_deadlines, get_uploads
from src.integrations.tumonline import (
    get_grades,
    get_identity,
    get_lectures,
    search_thesis_opportunities,
)
from src.lib.logging import get_logger
from src.lib.skill_inference import infer_skills
from src.lib.thesis_matching import match_theses_via_cognee

logger = get_logger(__name__)

router = APIRouter(prefix="/academic", tags=["academic"])


@router.get("/courses")
async def list_courses(semester: str | None = None) -> list[dict[str, Any]]:
    """List enrolled Moodle courses, optionally filtered by semester."""
    return await get_courses(semester=semester)

@router.get("/courses/{course_id}/uploads")
async def list_uploads(course_id: str) -> list[dict[str, Any]]:
    """List resources/uploads for a Moodle course."""
    return await get_uploads(moodle_course_id=course_id)


@router.get("/deadlines")
async def list_deadlines(course_id: str | None = None) -> list[dict[str, Any]]:
    """List upcoming deadlines for the demo student, optionally filtered by course."""
    return await get_deadlines(student_id=DEMO_STUDENT_ID, course_id=course_id)


@router.post("/deadlines/sync-calendar")
async def sync_deadlines_to_calendar() -> dict[str, Any]:
    """Create Google Calendar events for all deadlines, skipping duplicates."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from src.integrations.gcal import create_event, list_events

    deadlines = await get_deadlines(student_id=DEMO_STUDENT_ID)
    if not deadlines:
        return {"synced": 0, "skipped": 0, "total": 0}

    all_dues = [datetime.fromisoformat(d["due_at"]) for d in deadlines]
    time_min = min(all_dues) - timedelta(days=1)
    time_max = max(all_dues) + timedelta(days=1)
    tz = ZoneInfo("Europe/Berlin")
    if time_min.tzinfo is None:
        time_min = time_min.replace(tzinfo=tz)
    if time_max.tzinfo is None:
        time_max = time_max.replace(tzinfo=tz)

    existing = await list_events(
        student_id=DEMO_STUDENT_ID,
        time_min=time_min,
        time_max=time_max,
    )
    existing_titles = {e.title for e in existing}

    synced = 0
    skipped = 0
    for d in deadlines:
        title = f"\U0001f4c5 Deadline: {d['course_id']} \u2014 {d['title']}"
        if title in existing_titles:
            skipped += 1
            continue
        due = datetime.fromisoformat(d["due_at"])
        starts_at = due - timedelta(minutes=30)
        await create_event(
            student_id=DEMO_STUDENT_ID,
            title=title,
            starts_at=starts_at,
            ends_at=due,
            location="",
            description=f"Weight: {d.get('weight', 0):.0%} | Source: {d.get('source', 'moodle')}",
        )
        existing_titles.add(title)
        synced += 1

    logger.info("deadlines_synced_to_calendar", synced=synced, skipped=skipped)
    return {"synced": synced, "skipped": skipped, "total": len(deadlines)}


@router.get("/thesis")
async def list_thesis(
    keywords: str | None = None,
    chair: str | None = None,
    tags: str | None = None,
) -> list[dict[str, Any]]:
    """Search thesis opportunities with Cognee-powered profile matching."""
    kw_list = keywords.split(",") if keywords else None
    tag_list = tags.split(",") if tags else None
    raw = await search_thesis_opportunities(keywords=kw_list, chair=chair, tags=tag_list)

    try:
        identity = await get_identity()
        grades = await get_grades()
        lectures = await get_lectures()
        skills = await infer_skills(grades, lectures)
    except Exception:
        logger.warning("thesis_profile_fetch_failed", exc_info=True)
        identity, grades, lectures, skills = {}, [], [], []

    return await match_theses_via_cognee(raw, grades, lectures, skills, identity)


# --- Library Room Booking (anny.eu) ---


@router.get("/rooms/branches")
async def get_branches() -> list[dict[str, str]]:
    """List TUM library branches available for room booking."""
    return await list_library_branches()


@router.get("/rooms")
async def list_rooms(
    branch: str = "mathematics-informatics",
    target_date: str | None = None,
) -> dict[str, Any]:
    """Search available rooms and time slots at a TUM library branch."""
    settings = get_settings()
    return await search_rooms(
        tum_username=settings.tum_username,
        tum_password=settings.tum_password,
        branch=branch,
        target_date=target_date,
    )


class RoomBookingRequest(BaseModel):
    """Request body for booking a library room."""

    branch: str
    room_name: str
    date_day: str
    start_time: str
    end_time: str
    num_persons: int = 3


@router.post("/rooms/book")
async def book_library_room(body: RoomBookingRequest) -> dict[str, Any]:
    """Book a specific group room at a TUM library branch."""
    settings = get_settings()
    return await book_room(
        tum_username=settings.tum_username,
        tum_password=settings.tum_password,
        branch=body.branch,
        room_name=body.room_name,
        date_day=body.date_day,
        start_time=body.start_time,
        end_time=body.end_time,
        num_persons=body.num_persons,
    )


class VerifyBookingRequest(BaseModel):
    """Request body for verifying a booking."""

    booking_url: str


@router.post("/rooms/verify")
async def verify_library_booking(body: VerifyBookingRequest) -> dict[str, Any]:
    """Verify a booking status and retrieve QR code."""
    settings = get_settings()
    return await verify_booking(
        tum_username=settings.tum_username,
        tum_password=settings.tum_password,
        booking_url=body.booking_url,
    )
