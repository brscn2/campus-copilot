"""Unit tests for the mock TUMonline integration."""

from __future__ import annotations

import pytest

from src.integrations.tumonline import get_professor_info, search_thesis_opportunities


@pytest.mark.asyncio
async def test_search_thesis_returns_results() -> None:
    results = await search_thesis_opportunities()
    assert len(results) > 0
    for opp in results:
        assert "id" in opp
        assert "topic" in opp
        assert "professor_name" in opp


@pytest.mark.asyncio
async def test_search_thesis_filters_by_keywords() -> None:
    results = await search_thesis_opportunities(keywords=["reinforcement learning"])
    assert len(results) >= 1
    assert all(
        "reinforcement" in r["topic"].lower() or "reinforcement" in r["description"].lower()
        for r in results
    )


@pytest.mark.asyncio
async def test_search_thesis_filters_by_chair() -> None:
    results = await search_thesis_opportunities(chair="Robotics")
    assert all("Robotics" in r["chair"] for r in results)


@pytest.mark.asyncio
async def test_search_thesis_filters_by_tags() -> None:
    results = await search_thesis_opportunities(tags=["privacy"])
    assert len(results) >= 1
    assert any("privacy" in r["tags"] for r in results)


@pytest.mark.asyncio
async def test_search_thesis_no_results() -> None:
    results = await search_thesis_opportunities(keywords=["quantum underwater basket weaving"])
    assert results == []


@pytest.mark.asyncio
async def test_get_professor_info_found() -> None:
    result = await get_professor_info("knoll@in.tum.de")
    assert result is not None
    assert result["name"] == "Prof. Dr.-Ing. Alois Knoll"
    assert "office_hours" in result


@pytest.mark.asyncio
async def test_get_professor_info_not_found() -> None:
    result = await get_professor_info("nonexistent@tum.de")
    assert result is None
