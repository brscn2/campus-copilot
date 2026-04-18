"""Pure-function tools for the Academic agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.integrations.library import book_room as _book_room
from src.integrations.library import search_rooms as _search_rooms


@tool
async def search_rooms(
    date: str,
    duration_hours: int = 2,
    capacity: int = 1,
    building: str | None = None,
) -> list[dict[str, Any]]:
    """Search for available TUM library study rooms.

    Args:
        date: ISO date string, e.g. '2026-04-18'.
        duration_hours: How many hours you need the room.
        capacity: Minimum number of seats needed.
        building: Optional building filter (e.g. 'Garching', 'Stammgelände').
    """
    return await _search_rooms(
        date=date,
        duration_hours=duration_hours,
        capacity=capacity,
        building=building,
    )


@tool
async def book_room(
    room_id: str,
    start: str,
    end: str,
    student_id: str,
) -> dict[str, Any]:
    """Book a specific library study room.

    Args:
        room_id: The room identifier from search results.
        start: ISO datetime for booking start.
        end: ISO datetime for booking end.
        student_id: The student making the booking.
    """
    return await _book_room(
        room_id=room_id,
        start=start,
        end=end,
        student_id=student_id,
    )
