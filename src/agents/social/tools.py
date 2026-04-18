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

if TYPE_CHECKING:
    from src.models.event import EsnEvent

TUM_USERNAME = "go79sax"
TUM_PASSWORD = "Polyu03@@@"


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
    result: dict[str, Any] = await _get_details(
        tum_username=TUM_USERNAME, tum_password=TUM_PASSWORD, course_name=course_name
    )
    return result


@tool
async def book_zhs(
    course_name: str,
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
        course_index: For weekly courses, which option (0 = first, 1 = second, etc.).
        slot_id: For free play, the slot ID from the schedule results.
    """
    result: dict[str, Any] = await _book_course(
        tum_username=TUM_USERNAME,
        tum_password=TUM_PASSWORD,
        course_name=course_name,
        course_index=course_index,
        slot_id=slot_id or None,
    )
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
async def get_mensa_menu(
    mensa: str = "mensa-garching",
    vegetarian_only: bool = False,
    vegan_only: bool = False,
) -> list[dict[str, Any]]:
    """Get today's Mensa menu from the TUM eat-api.

    Real data from TUM Studentenwerk canteens. Only available on weekdays.

    Args:
        mensa: Canteen slug — popular: 'mensa-garching', 'mensa-arcisstr',
               'mensa-leopoldstr', 'mensa-lothstr', 'fmi-bistro'.
        vegetarian_only: Only vegetarian options.
        vegan_only: Only vegan options.
    """
    return await _get_menu(mensa=mensa, vegetarian_only=vegetarian_only, vegan_only=vegan_only)
