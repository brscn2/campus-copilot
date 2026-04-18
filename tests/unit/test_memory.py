"""Unit tests for the Cognee Cloud memory layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.lib.memory import add_to_memory, query_memory

_FAKE_REQUEST = httpx.Request("POST", "https://fake.cognee.ai/api/v1/test")


def _ok_response(json_data: object) -> httpx.Response:
    return httpx.Response(200, json=json_data, request=_FAKE_REQUEST)


def _make_mock_client(post_return: httpx.Response | Exception) -> AsyncMock:
    mock_client = AsyncMock()
    if isinstance(post_return, Exception):
        mock_client.post = AsyncMock(side_effect=post_return)
    else:
        mock_client.post = AsyncMock(return_value=post_return)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.asyncio
async def test_add_to_memory_posts_to_cognee_api() -> None:
    mock_client = _make_mock_client(_ok_response({"status": "ok"}))

    with patch("src.lib.memory.httpx.AsyncClient", return_value=mock_client):
        await add_to_memory(
            user_id="demo-student",
            content="Student is interested in reinforcement learning.",
        )

    mock_client.post.assert_called_once()
    payload = mock_client.post.call_args[1]["json"]
    assert payload["dataset_name"] == "student_demo-student"
    assert "reinforcement learning" in payload["data"]


@pytest.mark.asyncio
async def test_query_memory_posts_to_search_with_dataset_scoping() -> None:
    response_data = [{"search_result": "Student likes ML and robotics."}]
    mock_client = _make_mock_client(_ok_response(response_data))

    with patch("src.lib.memory.httpx.AsyncClient", return_value=mock_client):
        results = await query_memory(
            user_id="demo-student",
            query="What are the student's interests?",
        )

    assert len(results) == 1
    assert "ML" in results[0]["content"]

    call_kwargs = mock_client.post.call_args[1]
    assert call_kwargs["json"]["datasets"] == ["student_demo-student"]
    assert call_kwargs["json"]["search_type"] == "GRAPH_COMPLETION"


@pytest.mark.asyncio
async def test_query_memory_returns_empty_on_failure() -> None:
    mock_client = _make_mock_client(httpx.ConnectError("connection refused"))

    with patch("src.lib.memory.httpx.AsyncClient", return_value=mock_client):
        results = await query_memory(user_id="demo", query="test")
        assert results == []


@pytest.mark.asyncio
async def test_query_memory_filters_short_results() -> None:
    response_data = [
        "A long meaningful result about student interests",
        "short",
        "Another good result here for testing",
    ]
    mock_client = _make_mock_client(_ok_response(response_data))

    with patch("src.lib.memory.httpx.AsyncClient", return_value=mock_client):
        results = await query_memory(user_id="demo", query="interests", top_k=5)

    assert len(results) == 2
    assert results[0]["content"] == "A long meaningful result about student interests"
