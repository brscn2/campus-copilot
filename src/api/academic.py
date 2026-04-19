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
