"""Unit tests for the Cognee memory layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.lib.memory import add_to_memory, query_memory


@pytest.mark.asyncio
async def test_add_to_memory_calls_cognee_remember() -> None:
    with patch("src.lib.memory.cognee") as mock_cognee:
        mock_result = AsyncMock()
        mock_result.status = "completed"
        mock_cognee.remember = AsyncMock(return_value=mock_result)

        await add_to_memory(
            user_id="demo-student",
            content="Lecture 1 covers neural network basics.",
            metadata={"course": "IN2346"},
        )

        mock_cognee.remember.assert_called_once()
        call_args = mock_cognee.remember.call_args
        assert "neural network" in call_args[0][0]
        assert call_args[1]["dataset_name"] == "student_demo-student"


@pytest.mark.asyncio
async def test_query_memory_calls_cognee_recall() -> None:
    with patch("src.lib.memory.cognee") as mock_cognee:
        mock_cognee.recall = AsyncMock(
            return_value=[{"text": "Neural networks use backpropagation.", "score": 0.9}]
        )

        results = await query_memory(
            user_id="demo-student",
            query="How does backpropagation work?",
        )

        mock_cognee.recall.assert_called_once()
        assert len(results) == 1
        assert "backpropagation" in results[0]["text"]


@pytest.mark.asyncio
async def test_add_to_memory_handles_cognee_failure_gracefully() -> None:
    with patch("src.lib.memory.cognee") as mock_cognee:
        mock_cognee.remember = AsyncMock(side_effect=Exception("Cognee down"))

        await add_to_memory(
            user_id="demo-student",
            content="Some content",
        )
        # Should not raise — logs warning and returns
