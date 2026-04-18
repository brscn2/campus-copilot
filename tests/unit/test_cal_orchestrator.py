"""Unit tests for the calendar orchestrator stub."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.cal.orchestrator import check_conflicts, register_booking


@pytest.mark.asyncio
async def test_check_conflicts_returns_empty() -> None:
    result = await check_conflicts(
        student_id="demo-student",
        starts_at=datetime(2026, 4, 18, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 18, 12, 0, tzinfo=UTC),
    )
    assert result == []


@pytest.mark.asyncio
async def test_register_booking_returns_metadata() -> None:
    result = await register_booking(
        student_id="demo-student",
        kind="study_room",
        starts_at=datetime(2026, 4, 18, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 18, 12, 0, tzinfo=UTC),
        payload={"room_id": "lib-sr-202"},
    )
    assert result["status"] == "registered"
    assert result["kind"] == "study_room"
