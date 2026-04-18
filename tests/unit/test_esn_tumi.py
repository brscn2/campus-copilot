"""Unit tests for the mock ESN TUMi event integration."""

from __future__ import annotations

import pytest

from src.integrations.esn_tumi import search_events


@pytest.mark.asyncio
async def test_search_events_returns_results() -> None:
    results = await search_events()
    assert len(results) > 0
    for event in results:
        assert "id" in event
        assert "title" in event
        assert "date" in event


@pytest.mark.asyncio
async def test_search_events_filters_by_keyword() -> None:
    results = await search_events(keyword="hiking")
    assert len(results) >= 1
    assert any(
        "hiking" in e["title"].lower() or "hiking" in e["description"].lower() for e in results
    )


@pytest.mark.asyncio
async def test_search_events_filters_by_tags() -> None:
    results = await search_events(tags=["tech"])
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_events_available_only() -> None:
    results = await search_events(available_only=True)
    assert all(e["spots_available"] > 0 for e in results)


@pytest.mark.asyncio
async def test_search_events_no_results() -> None:
    results = await search_events(keyword="quantum underwater")
    assert results == []
