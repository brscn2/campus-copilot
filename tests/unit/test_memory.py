"""Unit tests for the Cognee Cloud memory layer."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.lib.memory import add_to_memory, query_memory


def _mock_search_results(texts: list[str]) -> list[SimpleNamespace]:
    """Build fake SearchResult objects with a search_result attribute."""
    return [SimpleNamespace(search_result=t) for t in texts]


@pytest.fixture(autouse=True)
def _skip_cognee_init() -> None:  # type: ignore[misc]
    """Prevent real Cognee Cloud connection in tests."""
    with patch("src.lib.memory.ensure_cognee", new_callable=AsyncMock):
        yield


@pytest.mark.asyncio
async def test_add_to_memory_calls_cognee_remember() -> None:
    with patch("cognee.remember", new_callable=AsyncMock) as mock_remember:
        await add_to_memory(
            user_id="demo-student",
            content="Student is interested in reinforcement learning.",
        )

    mock_remember.assert_called_once()
    call_kwargs = mock_remember.call_args[1]
    assert call_kwargs["dataset_name"] == "student_demo-student"
    assert "reinforcement learning" in call_kwargs["data"]


@pytest.mark.asyncio
async def test_query_memory_searches_with_dataset_scoping() -> None:
    results = _mock_search_results(["Student likes ML and robotics."])

    with patch("cognee.recall", new_callable=AsyncMock, return_value=results):
        memories = await query_memory(
            user_id="demo-student",
            query="What are the student's interests?",
        )

    assert len(memories) == 1
    assert "ML" in memories[0]["content"]


@pytest.mark.asyncio
async def test_query_memory_returns_empty_on_failure() -> None:
    with patch(
        "cognee.recall", new_callable=AsyncMock, side_effect=Exception("connection refused")
    ):
        results = await query_memory(user_id="demo", query="test")
        assert results == []


@pytest.mark.asyncio
async def test_query_memory_filters_short_results() -> None:
    results = _mock_search_results(
        [
            "A long meaningful result about student interests",
            "short",
            "Another good result here for testing",
        ]
    )

    with patch("cognee.recall", new_callable=AsyncMock, return_value=results):
        memories = await query_memory(user_id="demo", query="interests", top_k=5)

    assert len(memories) == 2
    assert memories[0]["content"] == "A long meaningful result about student interests"
