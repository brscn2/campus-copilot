"""Calendar Orchestrator — conflict detection and resolution.

Every agent that proposes a time-bound action runs it through here first.
For now this is a passthrough stub; conflict detection comes in Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.lib.logging import get_logger

if TYPE_CHECKING:
    from datetime import datetime

logger = get_logger(__name__)


async def check_conflicts(
    *,
    student_id: str,
    starts_at: datetime,
    ends_at: datetime,
) -> list[dict[str, Any]]:
    """Check for scheduling conflicts.

    Returns:
        Empty list if no conflicts, otherwise list of conflicting events.
    """
    logger.info(
        "calendar_check_conflicts",
        student_id=student_id,
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
    )
    return []


async def register_booking(
    *,
    student_id: str,
    kind: str,
    starts_at: datetime,
    ends_at: datetime,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Register a confirmed booking on the calendar.

    Returns:
        Calendar event metadata.
    """
    logger.info(
        "calendar_register_booking",
        student_id=student_id,
        kind=kind,
    )
    return {
        "calendar_event_id": None,
        "status": "registered",
        "kind": kind,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    }
