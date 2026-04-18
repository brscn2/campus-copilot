"""Pure-function tools for the Social agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.integrations.esn_tumi import search_events as _search_events
from src.integrations.mensa import get_menu as _get_menu
from src.integrations.zhs import register_for_course as _register_zhs
from src.integrations.zhs import search_courses as _search_zhs
from src.integrations.zhs import set_snipe_alert as _set_snipe


@tool
async def search_zhs_courses(
    category: str | None = None,
    day: str | None = None,
    keyword: str | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search for ZHS university sport courses.

    Args:
        category: Sport category filter (e.g. 'climbing', 'yoga', 'swimming', 'martial_arts').
        day: Day of week filter (e.g. 'Monday', 'Wednesday').
        keyword: Keyword to match course name (e.g. 'bouldering').
        available_only: Only show courses with open spots.
    """
    return await _search_zhs(
        category=category,
        day=day,
        keyword=keyword,
        available_only=available_only,
    )


@tool
async def register_zhs_course(
    course_id: str,
    student_id: str,
) -> dict[str, Any]:
    """Register for a ZHS sport course.

    Args:
        course_id: The ZHS course identifier from search results.
        student_id: The student registering.
    """
    return await _register_zhs(course_id=course_id, student_id=student_id)


@tool
async def set_zhs_snipe_alert(
    course_id: str,
    student_id: str,
) -> dict[str, Any]:
    """Set a snipe alert for a full ZHS course.

    When a spot opens or registration begins, the student will be notified.

    Args:
        course_id: The ZHS course to watch.
        student_id: The student to notify.
    """
    return await _set_snipe(course_id=course_id, student_id=student_id)


@tool
async def search_events(
    keyword: str | None = None,
    tags: list[str] | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search for upcoming social events (ESN TUMi, Luma, UnternehmerTUM).

    Args:
        keyword: Keyword to match event title/description.
        tags: Tags to filter by (e.g. 'social', 'hiking', 'tech', 'networking').
        available_only: Only show events with open spots.
    """
    return await _search_events(keyword=keyword, tags=tags, available_only=available_only)


@tool
async def get_mensa_menu(
    mensa: str = "mensa-garching",
    vegetarian_only: bool = False,
    vegan_only: bool = False,
) -> list[dict[str, Any]]:
    """Get today's Mensa menu.

    Args:
        mensa: Which mensa ('mensa-garching' or 'mensa-arcisstrasse').
        vegetarian_only: Only vegetarian options.
        vegan_only: Only vegan options.
    """
    return await _get_menu(mensa=mensa, vegetarian_only=vegetarian_only, vegan_only=vegan_only)
