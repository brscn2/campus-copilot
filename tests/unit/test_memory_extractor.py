"""Unit tests for the background memory extractor."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.lib.memory_extractor import extract_and_remember


@pytest.mark.asyncio
async def test_extract_and_remember_calls_bedrock_and_cognee() -> None:
    turns = [
        {"role": "user", "content": "Find me thesis topics in reinforcement learning"},
        {"role": "assistant", "content": "I found 2 thesis topics about RL..."},
        {"role": "user", "content": "I prefer the robotics one at Prof. Knoll's chair"},
        {"role": "assistant", "content": "Great choice! Prof. Knoll's chair focuses on..."},
    ]

    mock_response = {
        "content": [
            {
                "text": (
                    '["Student is interested in reinforcement learning for robotics", '
                    '"Student prefers Prof. Knoll chair for thesis"]'
                )
            }
        ]
    }

    with (
        patch(
            "src.lib.memory_extractor.invoke_model",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch("src.lib.memory_extractor.add_to_memory", new_callable=AsyncMock) as mock_add,
        patch(
            "src.lib.memory_extractor.trigger_student_cognify",
            new_callable=AsyncMock,
        ) as mock_cognify,
    ):
        await extract_and_remember(student_id="demo-student", turns=turns)

    assert mock_add.call_count == 2
    first_call = mock_add.call_args_list[0]
    assert first_call[1]["user_id"] == "demo-student"
    assert "reinforcement learning" in first_call[1]["content"]
    mock_cognify.assert_called_once_with("demo-student")


@pytest.mark.asyncio
async def test_extract_and_remember_handles_empty_extraction() -> None:
    turns = [
        {"role": "user", "content": "What's for lunch?"},
        {"role": "assistant", "content": "Today's menu at Mensa Garching..."},
    ]

    mock_response = {"content": [{"text": "[]"}]}

    with (
        patch(
            "src.lib.memory_extractor.invoke_model",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch("src.lib.memory_extractor.add_to_memory", new_callable=AsyncMock) as mock_add,
        patch(
            "src.lib.memory_extractor.trigger_student_cognify",
            new_callable=AsyncMock,
        ) as mock_cognify,
    ):
        await extract_and_remember(student_id="demo-student", turns=turns)

    mock_add.assert_not_called()
    mock_cognify.assert_not_called()


@pytest.mark.asyncio
async def test_extract_and_remember_handles_bedrock_failure() -> None:
    with (
        patch(
            "src.lib.memory_extractor.invoke_model",
            new_callable=AsyncMock,
            side_effect=Exception("Bedrock down"),
        ),
        patch(
            "src.lib.memory_extractor.trigger_student_cognify",
            new_callable=AsyncMock,
        ) as mock_cognify,
    ):
        await extract_and_remember(
            student_id="demo-student", turns=[{"role": "user", "content": "hello"}]
        )

    mock_cognify.assert_not_called()
