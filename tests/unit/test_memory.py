"""Unit tests for the Cognee Cloud memory layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level client between tests."""
    import src.lib.memory as mem

    mem._client = None
    yield
    mem._client = None


@pytest.mark.asyncio
async def test_add_to_memory_calls_cogwit_add() -> None:
    mock_client = MagicMock()
    mock_client.add = AsyncMock(return_value=MagicMock(dataset_id="abc"))
    mock_client.cognify = AsyncMock(return_value=MagicMock())

    with patch("src.lib.memory._get_client", return_value=mock_client):
        from src.lib.memory import add_to_memory

        await add_to_memory(
            user_id="demo-student",
            content="Student is interested in reinforcement learning.",
        )

    mock_client.add.assert_called_once()
    assert mock_client.add.call_args[1]["dataset_name"] == "student_demo-student"
    mock_client.cognify.assert_called_once()


@pytest.mark.asyncio
async def test_query_memory_calls_cogwit_search() -> None:
    mock_result = MagicMock()
    mock_result.search_result = "Student likes ML and robotics."
    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=[mock_result])

    with patch("src.lib.memory._get_client", return_value=mock_client):
        from src.lib.memory import query_memory

        results = await query_memory(
            user_id="demo-student",
            query="What are the student's interests?",
        )

    assert len(results) == 1
    assert "ML" in results[0]["text"]


@pytest.mark.asyncio
async def test_add_to_memory_noop_without_api_key() -> None:
    with patch("src.lib.memory._get_client", return_value=None):
        from src.lib.memory import add_to_memory

        await add_to_memory(user_id="demo", content="test")


@pytest.mark.asyncio
async def test_query_memory_returns_empty_without_api_key() -> None:
    with patch("src.lib.memory._get_client", return_value=None):
        from src.lib.memory import query_memory

        results = await query_memory(user_id="demo", query="test")
        assert results == []
