"""Google Calendar integration — mock + live modes.

Follows the src/lib/s3.py pattern: lazy-init client, all I/O via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from src.config import DEMO_STUDENT_ID, get_settings
from src.models.calendar_event import CalendarEvent

logger = structlog.get_logger(__name__)

DEMO_STUDENT = DEMO_STUDENT_ID

# ---------------------------------------------------------------------------
# Agent-type inference from event titles
# ---------------------------------------------------------------------------

_ACADEMIC_PATTERNS = re.compile(
    r"\b(IN\d{4}|MA\d{4}|CIT\d{4}|PH\d{4}|Study block|Lecture|Tutorial|Lab|Midterm|Exam)\b",
    re.IGNORECASE,
)
_CAREER_PATTERNS = re.compile(
    r"\b(Career|recruiter|interview|BMW|Celonis|Siemens|Personio|Thesis outreach|Resume|CV)\b",
    re.IGNORECASE,
)
_SOCIAL_PATTERNS = re.compile(
    r"\b(ZHS|ESN|TUMi|Mensa|Lunch|Social|Climbing|Badminton|Swimming|Hike|Drinks|Dinner)\b",
    re.IGNORECASE,
)


def _infer_agent(title: str) -> str | None:
    if _ACADEMIC_PATTERNS.search(title):
        return "academic"
    if _CAREER_PATTERNS.search(title):
        return "career"
    if _SOCIAL_PATTERNS.search(title):
        return "social"
    return None


# ---------------------------------------------------------------------------
# Week helpers
# ---------------------------------------------------------------------------


def _week_range(week_offset: int = 0) -> tuple[datetime, datetime]:
    """Return (monday 00:00, sunday 23:59:59) for the given week offset."""
    now = datetime.now(tz=UTC)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    monday += timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


# ---------------------------------------------------------------------------
# Mock data — mirrors frontend/lib/mock-data.ts calendarEvents
# ---------------------------------------------------------------------------

_MOCK_EVENTS_TEMPLATE: list[dict[str, Any]] = [
    {
        "day": 0,
        "start": 9,
        "end": 10.5,
        "title": "IN2064 Lecture",
        "agent": "academic",
        "location": "MI HS 1",
    },
    {
        "day": 0,
        "start": 13,
        "end": 14,
        "title": "Celonis coffee chat",
        "agent": "career",
        "location": "Café Jasmin",
    },
    {
        "day": 0,
        "start": 18,
        "end": 19.5,
        "title": "ZHS Climbing",
        "agent": "social",
        "location": "Garching",
    },
    {
        "day": 1,
        "start": 10,
        "end": 11.5,
        "title": "IN0007 Tutorial",
        "agent": "academic",
        "location": "MI 00.08.038",
    },
    {
        "day": 1,
        "start": 14,
        "end": 16,
        "title": "Study block: IN2086",
        "agent": "academic",
        "location": "MI Library",
        "conflict": True,
    },
    {
        "day": 1,
        "start": 15,
        "end": 16,
        "title": "ESN Welcome Drinks RSVP",
        "agent": "social",
        "location": "Löwenbräukeller",
        "conflict": True,
    },
    {
        "day": 2,
        "start": 9,
        "end": 10.5,
        "title": "IN2086 Lecture",
        "agent": "academic",
        "location": "MI HS 2",
    },
    {
        "day": 2,
        "start": 12,
        "end": 13,
        "title": "Lunch w/ Jonas & Lena",
        "agent": "social",
        "location": "Mensa Garching",
    },
    {
        "day": 2,
        "start": 16,
        "end": 17,
        "title": "BMW recruiter call",
        "agent": "career",
        "location": "Zoom",
    },
    {
        "day": 3,
        "start": 11,
        "end": 12.5,
        "title": "MA0901 Lecture",
        "agent": "academic",
        "location": "MI HS 1",
    },
    {
        "day": 3,
        "start": 14,
        "end": 15.5,
        "title": "Thesis outreach — Prof. Günnemann",
        "agent": "career",
        "location": "Email",
    },
    {
        "day": 4,
        "start": 10,
        "end": 12,
        "title": "IN2339 Lab",
        "agent": "academic",
        "location": "MI 02.05.037",
    },
    {
        "day": 4,
        "start": 17,
        "end": 19,
        "title": "ZHS Badminton",
        "agent": "social",
        "location": "ZHS Hall 2",
    },
    {
        "day": 5,
        "start": 10,
        "end": 12,
        "title": "Study block: Midterm prep",
        "agent": "academic",
        "location": "MI Library",
    },
    {
        "day": 6,
        "start": 14,
        "end": 17,
        "title": "TUMi Alpine Hike",
        "agent": "social",
        "location": "Tegernsee",
    },
]


def _build_mock_events(week_offset: int = 0) -> list[CalendarEvent]:
    """Convert mock template into CalendarEvent objects with real datetimes."""
    monday, _ = _week_range(week_offset)
    events: list[CalendarEvent] = []
    for i, tmpl in enumerate(_MOCK_EVENTS_TEMPLATE):
        day_offset = tmpl["day"]
        start_hour = int(tmpl["start"])
        start_minute = int((tmpl["start"] % 1) * 60)
        end_hour = int(tmpl["end"])
        end_minute = int((tmpl["end"] % 1) * 60)

        starts_at = monday + timedelta(days=day_offset, hours=start_hour, minutes=start_minute)
        ends_at = monday + timedelta(days=day_offset, hours=end_hour, minutes=end_minute)

        events.append(
            CalendarEvent(
                id=f"mock_{i + 1}",
                title=tmpl["title"],
                starts_at=starts_at,
                ends_at=ends_at,
                agent=tmpl.get("agent"),
                location=tmpl.get("location", ""),
                conflict=tmpl.get("conflict", False),
            )
        )
    return events


# ---------------------------------------------------------------------------
# Live Google Calendar helpers
# ---------------------------------------------------------------------------

_gcal_service: Any = None


def _get_gcal_service(credentials: Any) -> Any:
    """Build a Google Calendar API service from credentials."""
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=credentials)


async def get_credentials(student_id: str) -> Any:
    """Load Google OAuth credentials — file first, DB fallback.

    1. Check `.gcal_token.json` on disk (works without Postgres).
    2. If missing, try DB lookup.
    3. If neither has a token, raise CalendarNotConnectedError.
    """
    import json
    from pathlib import Path

    from google.oauth2.credentials import Credentials

    from src.exceptions import CalendarNotConnectedError

    settings = get_settings()
    token_file = Path(".gcal_token.json")
    token_data: dict[str, Any] | None = None

    # 1. File-based check
    if token_file.exists():
        try:
            token_data = json.loads(token_file.read_text())
            logger.info("gcal_credentials_loaded_from_file")
        except (json.JSONDecodeError, OSError):
            logger.warning("gcal_credentials_file_unreadable", exc_info=True)

    # 2. DB fallback
    if token_data is None:
        try:
            from sqlalchemy import select

            from src.storage.db import get_session
            from src.storage.schema import StudentRow

            async for session in get_session():
                result = await session.execute(
                    select(StudentRow).where(StudentRow.id == student_id)
                )
                student = result.scalar_one_or_none()
                if student and student.google_calendar_token:
                    raw = student.google_calendar_token
                    token_data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
                    logger.info("gcal_credentials_loaded_from_db", student_id=student_id)
        except Exception:
            logger.warning("gcal_credentials_db_lookup_failed", exc_info=True)

    if token_data is None:
        raise CalendarNotConnectedError("Google Calendar not connected")

    return Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def list_events(
    student_id: str,
    time_min: datetime,
    time_max: datetime,
) -> list[CalendarEvent]:
    """Fetch calendar events for the given time range."""
    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        now = datetime.now(tz=UTC)
        monday_now = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        monday_req = (time_min - timedelta(days=time_min.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_offset = int((monday_req - monday_now).days / 7)
        logger.info("gcal_list_events_mock", student_id=student_id, week_offset=week_offset)
        return _build_mock_events(week_offset)

    logger.info("gcal_list_events_live", student_id=student_id)
    creds = await get_credentials(student_id)
    service = await asyncio.to_thread(_get_gcal_service, creds)

    # Google Calendar API requires RFC 3339 datetimes with timezone info
    if time_min.tzinfo is None:
        time_min = time_min.replace(tzinfo=UTC)
    if time_max.tzinfo is None:
        time_max = time_max.replace(tzinfo=UTC)

    result = await asyncio.to_thread(
        lambda: (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=100,
            )
            .execute()
        )
    )

    events: list[CalendarEvent] = []
    for item in result.get("items", []):
        start_raw = item.get("start", {})
        end_raw = item.get("end", {})
        starts_at = datetime.fromisoformat(start_raw.get("dateTime", start_raw.get("date", "")))
        ends_at = datetime.fromisoformat(end_raw.get("dateTime", end_raw.get("date", "")))
        title = item.get("summary", "Untitled")

        events.append(
            CalendarEvent(
                id=item["id"],
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                agent=_infer_agent(title),
                location=item.get("location", ""),
            )
        )
    return events


async def create_event(
    student_id: str,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    location: str = "",
    description: str = "",
) -> str:
    """Create a Google Calendar event. Returns the Google event ID."""
    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        import uuid

        mock_id = f"mock_created_{uuid.uuid4().hex[:8]}"
        logger.info("gcal_create_event_mock", student_id=student_id, event_id=mock_id)
        return mock_id

    logger.info("gcal_create_event_live", student_id=student_id, title=title)
    creds = await get_credentials(student_id)
    service = await asyncio.to_thread(_get_gcal_service, creds)

    body = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {"dateTime": starts_at.isoformat(), "timeZone": "Europe/Berlin"},
        "end": {"dateTime": ends_at.isoformat(), "timeZone": "Europe/Berlin"},
    }

    result = await asyncio.to_thread(
        lambda: service.events().insert(calendarId="primary", body=body).execute()
    )
    return result["id"]


async def delete_event(student_id: str, event_id: str) -> None:
    """Delete a Google Calendar event by ID."""
    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        logger.info("gcal_delete_event_mock", student_id=student_id, event_id=event_id)
        return

    logger.info("gcal_delete_event_live", student_id=student_id, event_id=event_id)
    creds = await get_credentials(student_id)
    service = await asyncio.to_thread(_get_gcal_service, creds)

    await asyncio.to_thread(
        lambda: service.events().delete(calendarId="primary", eventId=event_id).execute()
    )


async def update_event(
    student_id: str,
    event_id: str,
    **kwargs: Any,
) -> None:
    """Update fields on an existing Google Calendar event."""
    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        logger.info("gcal_update_event_mock", student_id=student_id, event_id=event_id)
        return

    logger.info("gcal_update_event_live", student_id=student_id, event_id=event_id)
    creds = await get_credentials(student_id)
    service = await asyncio.to_thread(_get_gcal_service, creds)

    body: dict[str, Any] = {}
    if "title" in kwargs:
        body["summary"] = kwargs["title"]
    if "location" in kwargs:
        body["location"] = kwargs["location"]
    if "description" in kwargs:
        body["description"] = kwargs["description"]
    if "starts_at" in kwargs:
        body["start"] = {"dateTime": kwargs["starts_at"].isoformat(), "timeZone": "Europe/Berlin"}
    if "ends_at" in kwargs:
        body["end"] = {"dateTime": kwargs["ends_at"].isoformat(), "timeZone": "Europe/Berlin"}

    await asyncio.to_thread(
        lambda: service.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
    )
