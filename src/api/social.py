"""REST endpoints for the Social tab — ZHS, events, mensa."""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.integrations.esn_tumi import fetch_event_detail, search_events
from src.integrations.mensa import get_canteens, get_menu
from src.integrations.zhs import get_categories as get_zhs_categories
from src.integrations.zhs import search_courses
from src.integrations.zhs_booking import book_zhs_course, get_course_details

if TYPE_CHECKING:
    from src.models.event import EsnEvent

router = APIRouter(prefix="/social", tags=["social"])

TUM_USERNAME = "go79sax"
TUM_PASSWORD = "Polyu03@@@"


# --- ZHS Courses (public MeiliSearch) ---


@router.get("/zhs")
async def list_zhs_courses(
    keyword: str | None = None,
    category: str | None = None,
    location: str | None = None,
    level: str | None = None,
) -> list[dict[str, Any]]:
    """Search ZHS sport courses with optional filters."""
    result: list[dict[str, Any]] = await search_courses(
        keyword=keyword,
        category=category,
        location=location,
        level=level,
    )
    return result


@router.get("/zhs/categories")
async def list_zhs_categories() -> list[dict[str, Any]]:
    """Get all ZHS sport categories with counts."""
    result: list[dict[str, Any]] = await get_zhs_categories()
    return result


# --- ZHS Booking (Playwright automation) ---


@router.get("/zhs/schedule")
async def get_zhs_schedule(course_name: str) -> dict[str, Any]:
    """Get real timetable for a ZHS course (timeslots or weekly classes)."""
    result: dict[str, Any] = await get_course_details(
        tum_username=TUM_USERNAME, tum_password=TUM_PASSWORD, course_name=course_name
    )
    return result


class BookingRequest(BaseModel):
    """Request body for booking a ZHS course."""

    course_name: str
    course_index: int = 0
    slot_id: str = ""


@router.post("/zhs/book")
async def book_zhs(body: BookingRequest) -> dict[str, Any]:
    """Book a ZHS course/slot with full checkout automation."""
    result: dict[str, Any] = await book_zhs_course(
        tum_username=TUM_USERNAME,
        tum_password=TUM_PASSWORD,
        course_name=body.course_name,
        course_index=body.course_index,
        slot_id=body.slot_id or None,
    )
    return result


# --- ESN Events ---


@router.get("/events")
async def list_events(
    keyword: str | None = None,
    tags: str | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search upcoming ESN TUMi events."""
    tag_list = tags.split(",") if tags else None
    return await search_events(keyword=keyword, tags=tag_list, available_only=available_only)


@router.get("/events/{event_id}")
async def get_event(event_id: str) -> dict[str, Any]:
    """Get details for a specific ESN TUMi event."""
    event: EsnEvent | None = await fetch_event_detail(event_id)
    if event is None:
        return {"error": "Event not found"}
    return event.to_tool_dict()


# --- Mensa ---


@router.get("/mensa/canteens")
async def list_canteens() -> list[dict[str, Any]]:
    """List available TUM canteens with metadata."""
    result: list[dict[str, Any]] = await get_canteens()
    return result


@router.get("/mensa")
async def mensa_menu(
    mensa: str = "mensa-garching",
    target_date: date | None = None,
    vegetarian_only: bool = False,
    vegan_only: bool = False,
) -> list[dict[str, Any]]:
    """Get mensa menu for a given day (defaults to today)."""
    return await get_menu(
        mensa=mensa,
        target_date=target_date,
        vegetarian_only=vegetarian_only,
        vegan_only=vegan_only,
    )
