"""Message hygiene helpers for LangGraph -> Bedrock calls.

Bedrock validates the *effective* message sequence after LangChain rewrites
``ToolMessage`` objects into ``HumanMessage`` content blocks and merges
adjacent human turns. This module mirrors that boundary and strips any
dangling ``tool_use`` / ``tool_result`` blocks before we hand messages to the
LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

if TYPE_CHECKING:
    from collections.abc import Sequence


def _merge_human_and_tool_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Return the Bedrock-effective sequence LangChain builds before serialization."""
    merged: list[BaseMessage] = []

    for message in messages:
        current = message.model_copy(deep=True)
        if isinstance(current, ToolMessage):
            if isinstance(current.content, list) and all(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in current.content
            ):
                current = HumanMessage(content=current.content)
            else:
                current = HumanMessage(
                    content=[
                        {
                            "type": "tool_result",
                            "content": current.content,
                            "tool_use_id": current.tool_call_id,
                        }
                    ]
                )

        last = merged[-1] if merged else None
        if last is not None and any(
            all(isinstance(item, klass) for item in (current, last))
            for klass in (SystemMessage, HumanMessage)
        ):
            if isinstance(last.content, str):
                new_content: list[Any] = [{"type": "text", "text": last.content}]
            else:
                new_content = list(last.content)

            if isinstance(current.content, str):
                new_content.append({"type": "text", "text": current.content})
            else:
                new_content.extend(current.content)
            last.content = new_content
        else:
            merged.append(current)

    return merged


def _clean_ai_message(ai: AIMessage, matched_ids: set[str]) -> AIMessage:
    """Return a copy of ``ai`` with unmatched tool_use blocks/tool_calls removed."""
    new_content: str | list[Any]
    if isinstance(ai.content, list):
        filtered: list[Any] = []
        for block in ai.content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                if block.get("id") in matched_ids:
                    filtered.append(block)
                # else: drop dangling tool_use block
            else:
                filtered.append(block)
        new_content = filtered
    else:
        new_content = ai.content

    new_tool_calls = [tc for tc in (ai.tool_calls or []) if tc.get("id") in matched_ids]

    return ai.model_copy(update={"content": new_content, "tool_calls": new_tool_calls})


def _human_tool_result_ids(message: HumanMessage) -> set[str]:
    """Collect tool_result ids from a human message's content blocks."""
    if not isinstance(message.content, list):
        return set()

    ids: set[str] = set()
    for block in message.content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            block_id = block.get("tool_use_id")
            if isinstance(block_id, str):
                ids.add(block_id)
    return ids


def _clean_human_message(message: HumanMessage, allowed_ids: set[str]) -> HumanMessage | None:
    """Return a copy of ``message`` with orphan tool_result blocks removed."""
    if isinstance(message.content, str):
        return message

    filtered: list[Any] = []
    for block in message.content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            if block.get("tool_use_id") in allowed_ids:
                filtered.append(block)
        else:
            filtered.append(block)

    if not filtered:
        return None

    return message.model_copy(update={"content": filtered})


def _ai_tool_use_ids(ai: AIMessage) -> set[str]:
    """Collect every tool_use id declared by an AIMessage (content + tool_calls)."""
    ids: set[str] = set()
    if isinstance(ai.content, list):
        for block in ai.content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                block_id = block.get("id")
                if isinstance(block_id, str):
                    ids.add(block_id)
    for tc in ai.tool_calls or []:
        tc_id = tc.get("id")
        if isinstance(tc_id, str):
            ids.add(tc_id)
    return ids


def _trim_trailing_ai_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Drop trailing assistant messages; Bedrock generation inputs must end with human."""
    trimmed = list(messages)
    while trimmed and isinstance(trimmed[-1], AIMessage):
        trimmed.pop()
    return trimmed


def sanitize_tool_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Return a Bedrock-safe message list with dangling tool blocks removed."""
    merged = _merge_human_and_tool_messages(messages)
    result: list[BaseMessage] = []
    i = 0
    while i < len(merged):
        msg = merged[i]

        if isinstance(msg, AIMessage):
            declared_ids = _ai_tool_use_ids(msg)
            next_msg = (
                merged[i + 1]
                if i + 1 < len(merged) and isinstance(merged[i + 1], HumanMessage)
                else None
            )
            next_ids = (
                _human_tool_result_ids(next_msg) if isinstance(next_msg, HumanMessage) else set()
            )
            matched_ids = declared_ids & next_ids

            result.append(_clean_ai_message(msg, matched_ids) if declared_ids else msg)

            if isinstance(next_msg, HumanMessage):
                cleaned_next = _clean_human_message(next_msg, matched_ids)
                if cleaned_next is not None:
                    result.append(cleaned_next)
                i += 2
                continue

            i += 1
            continue

        if isinstance(msg, HumanMessage):
            cleaned = _clean_human_message(msg, set())
            if cleaned is not None:
                result.append(cleaned)
            i += 1
            continue

        result.append(msg)
        i += 1

    return _trim_trailing_ai_messages(result)
