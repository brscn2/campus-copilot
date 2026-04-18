"""Intent classifier — routes to specialist agents."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage

from src.lib.bedrock import get_chat_model
from src.lib.logging import get_logger
from src.orchestrator.prompts import ROUTER_SYSTEM

logger = get_logger(__name__)

VALID_AGENTS = {"academic", "career", "social"}


async def classify_intent(query: str) -> Literal["academic", "career", "social"]:
    """Classify a user query to the correct specialist agent.

    Uses Sonnet for classification.

    Args:
        query: The user's message.

    Returns:
        One of 'academic', 'career', 'social'.
    """
    llm = get_chat_model(model="sonnet", temperature=0.0, max_tokens=10)

    messages = [
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=query),
    ]

    response = await llm.ainvoke(messages)
    raw = response.content.strip().lower() if isinstance(response.content, str) else "academic"

    if raw not in VALID_AGENTS:
        logger.warning("router_fallback", raw_response=raw, fallback="academic")
        return "academic"

    logger.info("router_classified", query_preview=query[:80], agent=raw)
    return raw  # type: ignore[return-value]
