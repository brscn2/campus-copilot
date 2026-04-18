"""Calendar Orchestrator — conflict detection, resolution, and booking.

Every agent that proposes a time-bound action runs it through here first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from src.lib.logging import get_logger

if TYPE_CHECKING:
    from datetime import datetime

    from src.models.calendar_event import CalendarEvent

logger = get_logger(__name__)

DEFAULT_PRIORITIES = [
    "Exam prep",
    "Academic lectures",
    "Career",
    "Sports",
    "Social",
]


async def check_conflicts(
    *,
    student_id: str,
    starts_at: datetime,
    ends_at: datetime,
) -> list[CalendarEvent]:
    """Check Google Calendar + BookingRow table for overlapping events.

    An event conflicts if:
      existing.starts_at < new.ends_at AND existing.ends_at > new.starts_at
    """
    from src.integrations.gcal import list_events

    logger.info(
        "calendar_check_conflicts",
        student_id=student_id,
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
    )

    events = await list_events(
        student_id=student_id,
        time_min=starts_at,
        time_max=ends_at,
    )

    conflicts = [e for e in events if e.starts_at < ends_at and e.ends_at > starts_at]
    return conflicts


async def resolve_conflict(
    events: list[CalendarEvent],
    priorities: list[str] | None = None,
) -> dict[str, Any]:
    """Given conflicting events and student priority list, decide winner.

    Uses Haiku (cheap + fast) to generate a one-sentence rationale.
    """
    if priorities is None:
        priorities = DEFAULT_PRIORITIES

    if len(events) < 2:
        return {"winner": events[0] if events else None, "loser": None, "rationale": "No conflict"}

    def _priority_score(event: CalendarEvent) -> int:
        agent = event.agent or ""
        title_lower = event.title.lower()
        for i, p in enumerate(priorities):
            p_lower = p.lower()
            if p_lower in title_lower or p_lower == agent:
                return i
        return len(priorities)

    sorted_events = sorted(events, key=_priority_score)
    winner = sorted_events[0]
    loser = sorted_events[1]

    rationale = await _generate_rationale(winner, loser, priorities)

    return {
        "winner": winner.model_dump(),
        "loser": loser.model_dump(),
        "rationale": rationale,
    }


async def _generate_rationale(
    winner: CalendarEvent,
    loser: CalendarEvent,
    priorities: list[str],
) -> str:
    """Use Haiku to generate a one-sentence conflict resolution rationale."""
    try:
        from src.lib.bedrock import get_haiku_model_id, invoke_model

        prompt = (
            f"The student's priority list is: {priorities}. "
            f'"{winner.title}" (agent: {winner.agent}) conflicts with '
            f'"{loser.title}" (agent: {loser.agent}). '
            f"Explain in one sentence why we kept the first and suggest rescheduling the second."
        )

        result = await invoke_model(
            model_id=get_haiku_model_id(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3,
        )
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "Priority-based resolution applied.")
        return "Priority-based resolution applied."
    except Exception:
        logger.warning("conflict_rationale_llm_failed", exc_info=True)
        return (
            f'Your priority list places "{winner.title}" above "{loser.title}". '
            f"Kept the higher-priority event."
        )


async def register_booking(
    *,
    student_id: str,
    kind: str,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    location: str = "",
    payload: dict[str, Any] | None = None,
    agent: str | None = None,
) -> dict[str, Any]:
    """Full booking flow: conflict check, gcal creation, DB insert."""
    from src.integrations.gcal import create_event

    logger.info(
        "calendar_register_booking",
        student_id=student_id,
        kind=kind,
        title=title,
    )

    conflicts = await check_conflicts(
        student_id=student_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )

    conflict_info: dict[str, Any] | None = None
    if conflicts:
        conflict_info = await resolve_conflict(conflicts)

    calendar_event_id = await create_event(
        student_id=student_id,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        location=location,
    )

    booking_id = str(uuid4())

    try:
        from sqlalchemy import select

        from src.storage.db import get_session
        from src.storage.schema import BookingRow, StudentRow

        async for session in get_session():
            result = await session.execute(select(StudentRow).where(StudentRow.id == student_id))
            student = result.scalar_one_or_none()

            if student:
                booking = BookingRow(
                    id=booking_id,
                    student_id=student_id,
                    kind=kind,
                    status="confirmed",
                    starts_at=starts_at,
                    ends_at=ends_at,
                    payload=payload or {},
                    calendar_event_id=calendar_event_id,
                )
                session.add(booking)
                await session.commit()
                logger.info("booking_row_created", booking_id=booking_id)
    except Exception:
        logger.warning("booking_db_insert_failed", exc_info=True)

    result_data: dict[str, Any] = {
        "booking_id": booking_id,
        "calendar_event_id": calendar_event_id,
        "status": "confirmed",
        "kind": kind,
        "title": title,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "location": location,
        "agent": agent,
    }

    if conflict_info:
        result_data["conflict"] = conflict_info

    return result_data
