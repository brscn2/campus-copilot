"""Unit tests for trigger_student_cognify."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.lib.cognify import STUDENT_COGNIFY_PROMPT, trigger_student_cognify


@pytest.mark.asyncio
async def test_trigger_student_cognify_posts_correct_payload() -> None:
    mock_response = httpx.Response(200, json={"status": "ok"})
    mock_post = AsyncMock(return_value=mock_response)

    with patch("src.lib.cognify.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await trigger_student_cognify("stu-42")

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["json"]["datasets"] == ["student_stu-42"]
    assert call_kwargs["json"]["customPrompt"] == STUDENT_COGNIFY_PROMPT
    assert "X-Api-Key" in call_kwargs["headers"]


@pytest.mark.asyncio
async def test_trigger_student_cognify_swallows_http_errors() -> None:
    mock_response = httpx.Response(500, text="Internal Server Error")
    mock_post = AsyncMock(return_value=mock_response)

    with patch("src.lib.cognify.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await trigger_student_cognify("stu-42")


@pytest.mark.asyncio
async def test_trigger_student_cognify_swallows_connection_errors() -> None:
    with patch("src.lib.cognify.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await trigger_student_cognify("stu-42")
