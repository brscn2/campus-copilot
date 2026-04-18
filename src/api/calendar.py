"""Calendar API routes — unified event list, create, delete, status."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import get_settings
from src.lib.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])

DEMO_STUDENT_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateEventRequest(BaseModel):
    """Body for POST /api/calendar/events."""

    title: str
    starts_at: str
    ends_at: str
    location: str = ""
    agent: str | None = None
    description: str = ""


class CalendarEventResponse(BaseModel):
    """Single event in the response list."""

    id: str | int
    title: str
    day: int
    start: float
    end: float
    agent: str | None = None
    location: str = ""
    conflict: bool = False
    google_event_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _week_range(week_offset: int = 0) -> tuple[datetime, datetime]:
    """Monday 00:00 to Sunday 23:59:59 for the given week offset."""
    now = datetime.now(tz=UTC)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    monday += timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def _to_response(event: Any, monday: datetime) -> CalendarEventResponse:
    """Convert a CalendarEvent model to the frontend-expected shape."""
    starts = event.starts_at
    ends = event.ends_at

    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=UTC)
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=UTC)

    day = (starts - monday).days
    start_hour = starts.hour + starts.minute / 60.0
    end_hour = ends.hour + ends.minute / 60.0

    return CalendarEventResponse(
        id=event.id,
        title=event.title,
        day=day,
        start=start_hour,
        end=end_hour,
        agent=event.agent,
        location=event.location,
        conflict=event.conflict,
        google_event_id=event.id if not str(event.id).startswith("mock_") else None,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/events")
async def list_events(
    week_offset: int = Query(default=0),
) -> dict[str, list[dict[str, Any]]]:
    """Return unified event list for the given week."""
    from src.integrations.gcal import list_events as gcal_list_events

    monday, sunday = _week_range(week_offset)

    logger.info("calendar_list_events", week_offset=week_offset)
    events = await gcal_list_events(
        student_id=DEMO_STUDENT_ID,
        time_min=monday,
        time_max=sunday,
    )

    response_events = [_to_response(e, monday) for e in events]
    return {"events": [e.model_dump() for e in response_events]}


@router.post("/events")
async def create_event(request: CreateEventRequest) -> dict[str, Any]:
    """Create a calendar event via the orchestrator."""
    from src.cal.orchestrator import register_booking

    starts_at = datetime.fromisoformat(request.starts_at)
    ends_at = datetime.fromisoformat(request.ends_at)

    # Naive datetimes from the frontend are local time (Europe/Berlin)
    local_tz = ZoneInfo("Europe/Berlin")
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=local_tz)
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=local_tz)

    logger.info("calendar_create_event", title=request.title)
    result = await register_booking(
        student_id=DEMO_STUDENT_ID,
        kind="event",
        title=request.title,
        starts_at=starts_at,
        ends_at=ends_at,
        location=request.location,
        agent=request.agent,
    )
    return result


@router.delete("/events/{event_id}")
async def delete_event(event_id: str) -> JSONResponse:
    """Delete a calendar event."""
    from src.integrations.gcal import delete_event as gcal_delete_event

    logger.info("calendar_delete_event", event_id=event_id)
    await gcal_delete_event(student_id=DEMO_STUDENT_ID, event_id=event_id)
    return JSONResponse(status_code=204, content=None)


@router.get("/status")
async def calendar_status() -> dict[str, bool]:
    """Return Google Calendar connection status."""
    from pathlib import Path

    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        return {"connected": True}

    # 1. Check local token file
    if Path(".gcal_token.json").exists():
        return {"connected": True}

    # 2. Best-effort DB check
    try:
        from sqlalchemy import select

        from src.storage.db import get_session
        from src.storage.schema import StudentRow

        async for session in get_session():
            result = await session.execute(
                select(StudentRow.google_calendar_token).where(StudentRow.id == DEMO_STUDENT_ID)
            )
            token = result.scalar_one_or_none()
            return {"connected": token is not None}
    except Exception:
        logger.warning("calendar_status_db_check_failed", exc_info=True)

    return {"connected": False}
