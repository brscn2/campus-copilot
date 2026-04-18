"""Mock TUM library study-room integration.

In live mode this would hit the library booking system.
For the hackathon demo, returns realistic fake data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.lib.logging import get_logger

logger = get_logger(__name__)

MOCK_ROOMS: list[dict[str, Any]] = [
    {
        "room_id": "lib-sr-101",
        "name": "Silent Study Room 101",
        "building": "Teilbibliothek Stammgelände",
        "capacity": 1,
        "has_monitor": False,
        "has_whiteboard": False,
    },
    {
        "room_id": "lib-sr-202",
        "name": "Group Study Room 202",
        "building": "Teilbibliothek Stammgelände",
        "capacity": 6,
        "has_monitor": True,
        "has_whiteboard": True,
    },
    {
        "room_id": "lib-sr-303",
        "name": "Group Study Room 303",
        "building": "Teilbibliothek Garching",
        "capacity": 4,
        "has_monitor": True,
        "has_whiteboard": False,
    },
    {
        "room_id": "lib-sr-404",
        "name": "Silent Study Room 404",
        "building": "Teilbibliothek Garching",
        "capacity": 1,
        "has_monitor": False,
        "has_whiteboard": False,
    },
    {
        "room_id": "lib-sr-505",
        "name": "Presentation Room 505",
        "building": "Teilbibliothek Stammgelände",
        "capacity": 10,
        "has_monitor": True,
        "has_whiteboard": True,
    },
]


def _generate_slots(date: datetime) -> list[dict[str, str]]:
    """Generate hourly availability slots for a given date."""
    base = date.replace(hour=8, minute=0, second=0, microsecond=0)
    slots: list[dict[str, str]] = []
    for hour_offset in range(12):
        start = base + timedelta(hours=hour_offset)
        end = start + timedelta(hours=1)
        slots.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
        )
    return slots


async def search_rooms(
    *,
    date: str,
    duration_hours: int = 2,
    capacity: int = 1,
    building: str | None = None,
) -> list[dict[str, Any]]:
    """Search for available library study rooms.

    Args:
        date: ISO-format date string (e.g. "2026-04-18").
        duration_hours: Desired booking duration in hours.
        capacity: Minimum room capacity.
        building: Optional building filter substring.

    Returns:
        List of available rooms with their slots.
    """
    logger.info(
        "library_search_rooms",
        date=date,
        duration_hours=duration_hours,
        capacity=capacity,
        building=building,
    )

    parsed_date = datetime.fromisoformat(date).replace(tzinfo=UTC)

    results: list[dict[str, Any]] = []
    for room in MOCK_ROOMS:
        if room["capacity"] < capacity:
            continue
        if building and building.lower() not in room["building"].lower():
            continue

        slots = _generate_slots(parsed_date)
        contiguous: list[dict[str, str]] = []
        for i in range(len(slots) - duration_hours + 1):
            contiguous.append(
                {
                    "start": slots[i]["start"],
                    "end": slots[i + duration_hours - 1]["end"],
                }
            )

        results.append({**room, "available_slots": contiguous})

    return results


async def book_room(
    *,
    room_id: str,
    start: str,
    end: str,
    student_id: str,
) -> dict[str, Any]:
    """Book a library study room.

    Args:
        room_id: The room identifier.
        start: ISO-format start datetime.
        end: ISO-format end datetime.
        student_id: The student making the booking.

    Returns:
        Booking confirmation with external reference.
    """
    logger.info(
        "library_book_room",
        room_id=room_id,
        start=start,
        end=end,
        student_id=student_id,
    )

    matching = [r for r in MOCK_ROOMS if r["room_id"] == room_id]
    if not matching:
        return {"error": f"Room {room_id} not found", "recoverable": False}

    return {
        "booking_id": f"lib-booking-{uuid4().hex[:8]}",
        "room_id": room_id,
        "room_name": matching[0]["name"],
        "building": matching[0]["building"],
        "start": start,
        "end": end,
        "status": "confirmed",
        "student_id": student_id,
    }
