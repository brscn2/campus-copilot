"""Unit tests for the mock library integration."""

from __future__ import annotations

import pytest

from src.integrations.library import book_room, search_rooms


@pytest.mark.asyncio
async def test_search_rooms_returns_results() -> None:
    results = await search_rooms(date="2026-04-18")
    assert len(results) > 0
    for room in results:
        assert "room_id" in room
        assert "available_slots" in room
        assert len(room["available_slots"]) > 0


@pytest.mark.asyncio
async def test_search_rooms_filters_by_capacity() -> None:
    results = await search_rooms(date="2026-04-18", capacity=6)
    assert all(r["capacity"] >= 6 for r in results)


@pytest.mark.asyncio
async def test_search_rooms_filters_by_building() -> None:
    results = await search_rooms(date="2026-04-18", building="Garching")
    assert all("Garching" in r["building"] for r in results)


@pytest.mark.asyncio
async def test_search_rooms_respects_duration() -> None:
    results = await search_rooms(date="2026-04-18", duration_hours=3)
    for room in results:
        for slot in room["available_slots"]:
            assert "start" in slot
            assert "end" in slot


@pytest.mark.asyncio
async def test_book_room_success() -> None:
    result = await book_room(
        room_id="lib-sr-202",
        start="2026-04-18T10:00:00+00:00",
        end="2026-04-18T12:00:00+00:00",
        student_id="demo-student",
    )
    assert result["status"] == "confirmed"
    assert result["room_id"] == "lib-sr-202"
    assert "booking_id" in result


@pytest.mark.asyncio
async def test_book_room_invalid_room() -> None:
    result = await book_room(
        room_id="nonexistent",
        start="2026-04-18T10:00:00+00:00",
        end="2026-04-18T12:00:00+00:00",
        student_id="demo-student",
    )
    assert "error" in result
