"""TUM library room booking integration via anny.eu.

Wraps the Playwright-based anny_browser module with retry logic.
Provides search_rooms, get_room_schedule, and book_room for the academic agent.
"""

from __future__ import annotations

from typing import Any

from src.lib.anny_browser import (
    book_room as _browser_book_room,
)
from src.lib.anny_browser import (
    list_branches as _list_branches,
)
from src.lib.anny_browser import (
    scrape_rooms_and_slots as _scrape_rooms_and_slots,
)
from src.lib.anny_browser import (
    verify_booking as _browser_verify_booking,
)
from src.lib.logging import get_logger
from src.lib.retry import retry_external

logger = get_logger(__name__)


@retry_external()
async def list_library_branches() -> list[dict[str, str]]:
    """List all TUM library branches available for room booking."""
    return await _list_branches()


@retry_external()
async def search_rooms(
    *,
    tum_username: str,
    tum_password: str,
    branch: str,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Search available rooms and time slots at a branch library.

    Args:
        tum_username: TUM username for SSO.
        tum_password: TUM password for SSO.
        branch: Branch slug (e.g. 'mathematics-informatics', 'main-campus').
        target_date: Day number to select (e.g. '21'). Defaults to today.

    Returns:
        Dict with rooms, available start/end times, dates, and branch info.
    """
    logger.info("library_search_rooms", branch=branch, target_date=target_date)

    result: dict[str, Any] = await _scrape_rooms_and_slots(
        username=tum_username,
        password=tum_password,
        branch_slug=branch,
        target_date=target_date,
    )
    return result


@retry_external()
async def book_room(
    *,
    tum_username: str,
    tum_password: str,
    branch: str,
    room_name: str,
    date_day: str,
    start_time: str,
    end_time: str,
    num_persons: int = 3,
) -> dict[str, Any]:
    """Book a specific room at a TUM library branch (full checkout).

    Args:
        tum_username: TUM username for SSO.
        tum_password: TUM password for SSO.
        branch: Branch slug (e.g. 'mathematics-informatics').
        room_name: Room name (e.g. 'Group Room 1').
        date_day: Day number in calendar (e.g. '21').
        start_time: Start time (e.g. '10:00').
        end_time: End time (e.g. '12:00').
        num_persons: Number of persons (3-8, default 3).

    Returns:
        Dict with status, message, booking details, and qr_code_base64 if available.
    """
    logger.info(
        "library_book_room",
        branch=branch,
        room_name=room_name,
        date_day=date_day,
        start_time=start_time,
        end_time=end_time,
        num_persons=num_persons,
    )

    result: dict[str, Any] = await _browser_book_room(
        username=tum_username,
        password=tum_password,
        branch_slug=branch,
        room_name=room_name,
        date_day=date_day,
        start_time=start_time,
        end_time=end_time,
        num_persons=num_persons,
    )
    return result


@retry_external()
async def verify_booking(
    *,
    tum_username: str,
    tum_password: str,
    booking_url: str,
) -> dict[str, Any]:
    """Verify a booking and retrieve its QR code.

    Args:
        tum_username: TUM username for SSO.
        tum_password: TUM password for SSO.
        booking_url: Full manage booking URL from the booking result.

    Returns:
        Dict with booking status and qr_code_base64 if available.
    """
    logger.info("library_verify_booking", url=booking_url)

    result: dict[str, Any] = await _browser_verify_booking(
        username=tum_username,
        password=tum_password,
        booking_url=booking_url,
    )
    return result
