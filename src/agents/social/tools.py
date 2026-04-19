"""Pure-function tools for the Social agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools import tool

from src.integrations.esn_tumi import fetch_event_detail as _fetch_event_detail
from src.integrations.esn_tumi import search_events as _search_events
from src.integrations.mensa import get_menu as _get_menu
from src.integrations.zhs import search_courses as _search_zhs
from src.integrations.zhs_booking import book_zhs_course as _book_course
from src.integrations.zhs_booking import get_course_details as _get_details

from src.config import get_settings

if TYPE_CHECKING:
    from src.models.event import EsnEvent


@tool
async def search_zhs_courses(
    keyword: str | None = None,
    category: str | None = None,
    level: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Search ZHS university sport courses from kurse.zhs-muenchen.de.

    Returns courses with names, descriptions, categories, levels, and direct links.

    Args:
        keyword: Text search (e.g. 'yoga', 'basketball', 'climbing').
        category: Filter by category (e.g. 'Yoga & Mindfulness', 'Football').
        level: Filter by level ('Beginner', 'Intermediate', 'Advanced', 'All Levels').
        location: Filter by campus ('Munich', 'Garching', 'Freising').
    """
    result: list[dict[str, Any]] = await _search_zhs(
        keyword=keyword, category=category, level=level, location=location
    )
    return result


@tool
async def get_zhs_course_schedule(
    course_name: str,
) -> dict[str, Any]:
    """Get full timetable and booking details for a ZHS course.

    Returns schedule with timeslots (for free play) or weekly class options
    (for paid courses), including dates, times, prices, locations, and
    availability status.

    ALWAYS call this before booking to show the student what's available.

    Args:
        course_name: Course to look up (e.g. 'basketball free play', 'yoga hatha').
    """
    settings = get_settings()
    result: dict[str, Any] = await _get_details(
        tum_username=settings.tum_username, tum_password=settings.tum_password, course_name=course_name
    )
    return result


@tool
async def book_zhs(
    course_name: str,
    student_id: str,
    course_index: int = 0,
    slot_id: str = "",
) -> dict[str, Any]:
    """Book a ZHS course or free play slot. Completes the full checkout.

    For weekly courses: use course_index to pick which class option.
    For free play: use slot_id (from get_zhs_course_schedule) to pick the timeslot.

    IMPORTANT: Always call get_zhs_course_schedule first to show available
    options, then confirm with the student before calling this.

    Args:
        course_name: Course to book (e.g. 'basketball free play').
        student_id: The student making the booking.
        course_index: For weekly courses, which option (0 = first, 1 = second, etc.).
        slot_id: For free play, the slot ID from the schedule results.
    """
    settings = get_settings()
    result: dict[str, Any] = await _book_course(
        tum_username=settings.tum_username,
        tum_password=settings.tum_password,
        course_name=course_name,
        course_index=course_index,
        slot_id=slot_id or None,
    )

    if result.get("status") in ("confirmed", "pending", "booked"):
        from datetime import datetime

        from src.cal.orchestrator import register_booking

        start_str = result.get("start_time") or result.get("time", "")
        end_str = result.get("end_time", "")
        date_str = result.get("date", "")
        if start_str and date_str:
            try:
                start_dt = datetime.fromisoformat(f"{date_str}T{start_str}")
                end_dt = (
                    datetime.fromisoformat(f"{date_str}T{end_str}")
                    if end_str
                    else start_dt.replace(hour=start_dt.hour + 2)
                )
                booking = await register_booking(
                    student_id=student_id,
                    kind="sport",
                    title=f"ZHS: {course_name}",
                    starts_at=start_dt,
                    ends_at=end_dt,
                    location=result.get("location", "ZHS München"),
                    agent="social",
                )
                result["calendar"] = booking
            except Exception:
                pass

    return result


@tool
async def search_events(
    keyword: str | None = None,
    tags: list[str] | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search for upcoming ESN TUMi events for international students in Munich.

    Returns real events from tumi.esn.world with registration links.

    Args:
        keyword: Text search against event titles and descriptions.
        tags: Topic filters (e.g. 'party', 'hiking', 'culture').
        available_only: Only show events with open spots.
    """
    return await _search_events(keyword=keyword, tags=tags, available_only=available_only)


@tool
async def get_event_details(event_id: str) -> dict[str, Any]:
    """Get full details for a specific ESN TUMi event by its ID.

    Args:
        event_id: The event ID from search results.
    """
    event: EsnEvent | None = await _fetch_event_detail(event_id)
    if event is None:
        return {"error": "Event not found", "recoverable": False}
    result: dict[str, Any] = dict(event.to_tool_dict())
    return result


@tool
async def open_event_registration(event_id: str) -> dict[str, str]:
    """Open the ESN TUMi event registration page in the student's browser.

    Use this when the student wants to register for an event. It opens the
    tumi.esn.world page directly so they can log in and sign up.

    Args:
        event_id: The event ID from search results or get_event_details.
    """
    import asyncio
    import subprocess

    url = f"https://tumi.esn.world/events/{event_id}"
    await asyncio.to_thread(
        subprocess.run,
        ["open", "-na", "Google Chrome", "--args", "--new-window", url],
        check=False,
    )
    return {"status": "opened", "url": url}


@tool
async def get_mensa_menu(
    mensa: str = "mensa-garching",
    vegetarian_only: bool = False,
    vegan_only: bool = False,
) -> list[dict[str, Any]] | dict[str, str]:
    """Get today's Mensa menu from the TUM eat-api.

    Real data from TUM Studentenwerk canteens. Only available on weekdays
    (Mon-Fri). Returns an error dict on weekends — do NOT retry.

    Args:
        mensa: Canteen slug — popular: 'mensa-garching', 'mensa-arcisstr',
               'mensa-leopoldstr', 'mensa-lothstr', 'fmi-bistro'.
        vegetarian_only: Only vegetarian options.
        vegan_only: Only vegan options.
    """
    from datetime import date

    today = date.today()
    if today.weekday() >= 5:
        return {"error": "Mensa is closed on weekends. Try again on a weekday.", "recoverable": False}

    result = await _get_menu(mensa=mensa, vegetarian_only=vegetarian_only, vegan_only=vegan_only)
    if not result:
        return {"error": f"No menu available for {mensa} today ({today.isoformat()}).", "recoverable": False}
    return result
