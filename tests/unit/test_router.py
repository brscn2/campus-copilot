"""Unit tests for the orchestrator router — mocks Bedrock to test classification logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_classify_intent_academic() -> None:
    with patch("src.orchestrator.router.get_chat_model") as mock_get:
        mock_llm = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = "academic"
        mock_llm.ainvoke.return_value = mock_response
        mock_get.return_value = mock_llm

        from src.orchestrator.router import classify_intent

        result = await classify_intent("I need a study room for tomorrow")
        assert result == "academic"


@pytest.mark.asyncio
async def test_classify_intent_career() -> None:
    with patch("src.orchestrator.router.get_chat_model") as mock_get:
        mock_llm = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = "career"
        mock_llm.ainvoke.return_value = mock_response
        mock_get.return_value = mock_llm

        from src.orchestrator.router import classify_intent

        result = await classify_intent("Find me working student positions")
        assert result == "career"


@pytest.mark.asyncio
async def test_classify_intent_fallback_on_invalid() -> None:
    with patch("src.orchestrator.router.get_chat_model") as mock_get:
        mock_llm = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = "I think this is about academics"
        mock_llm.ainvoke.return_value = mock_response
        mock_get.return_value = mock_llm

        from src.orchestrator.router import classify_intent

        result = await classify_intent("What's for lunch?")
        assert result == "academic"
