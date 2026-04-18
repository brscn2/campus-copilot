"""ZHS booking integration via Playwright browser automation.

Provides agentic course/free-play booking by automating the ZHS website.
Scrapes real timetable data (schedules, timeslots, prices, availability).
"""

from __future__ import annotations

from typing import Any

from src.lib.logging import get_logger
from src.lib.retry import retry_external
from src.lib.zhs_browser import book_course, get_course_info

logger = get_logger(__name__)


@retry_external()  # type: ignore[untyped-decorator]
async def get_course_details(
    *,
    tum_username: str,
    tum_password: str,
    course_name: str,
) -> dict[str, Any]:
    """Search for a course and return full schedule details.

    For weekly courses: date range, weekday, time, location, price, leader.
    For free play: available timeslots by date with booking status.

    Args:
        tum_username: TUM account username.
        tum_password: TUM account password.
        course_name: Course to search for (e.g. 'basketball', 'yoga hatha').

    Returns:
        Dict with type ('weekly_course' or 'free_play'), title,
        courses/slots list, and booking URL.
    """
    logger.info("zhs_get_course_details", course_name=course_name)
    result: dict[str, Any] = await get_course_info(
        username=tum_username, password=tum_password, course_name=course_name
    )
    return result


@retry_external()  # type: ignore[untyped-decorator]
async def book_zhs_course(
    *,
    tum_username: str,
    tum_password: str,
    course_name: str,
    course_index: int = 0,
    slot_id: str | None = None,
) -> dict[str, Any]:
    """Book a ZHS course or free play slot.

    Free play slots are fully automated (free, no forms).
    Weekly courses are added to cart and a visible browser opens for the
    user to complete checkout (may require certificates, language docs, etc.).

    Args:
        tum_username: TUM account username.
        tum_password: TUM account password.
        course_name: Course to search and book.
        course_index: For weekly courses, which option to book (0-based).
        slot_id: For free play, specific slot button ID to book.

    Returns:
        Booking result with status, message, and checkout_url (for weekly).
    """
    logger.info(
        "zhs_book_course",
        course_name=course_name,
        course_index=course_index,
        slot_id=slot_id,
    )
    result: dict[str, Any] = await book_course(
        username=tum_username,
        password=tum_password,
        course_name=course_name,
        course_index=course_index,
        slot_id=slot_id,
    )
    return result
