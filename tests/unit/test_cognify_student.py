"""Unit tests for trigger_student_cognify."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.lib.cognify import trigger_student_cognify


@pytest.fixture(autouse=True)
def _skip_cognee_init() -> None:  # type: ignore[misc]
    """Prevent real Cognee Cloud connection in tests."""
    with patch("src.lib.cognify.ensure_cognee", new_callable=AsyncMock):
        yield


@pytest.mark.asyncio
async def test_trigger_student_cognify_sends_correct_params() -> None:
    with patch("cognee.improve", new_callable=AsyncMock) as mock_improve:
        await trigger_student_cognify("stu-42")

    mock_improve.assert_called_once()
    call_kwargs = mock_improve.call_args[1]
    assert call_kwargs["dataset"] == "student_stu-42"


@pytest.mark.asyncio
async def test_trigger_student_cognify_swallows_sdk_errors() -> None:
    with patch("cognee.improve", new_callable=AsyncMock, side_effect=Exception("Cognee down")):
        await trigger_student_cognify("stu-42")


@pytest.mark.asyncio
async def test_trigger_student_cognify_swallows_connection_errors() -> None:
    with patch(
        "cognee.improve",
        new_callable=AsyncMock,
        side_effect=ConnectionError("connection refused"),
    ):
        await trigger_student_cognify("stu-42")
