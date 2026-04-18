"""Unit tests for the message hygiene helper."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.lib.message_hygiene import sanitize_tool_messages


def _ai_with_tool_use_block(
    *, text: str, tool_use_id: str, name: str, input_: dict, in_tool_calls: bool = True
) -> AIMessage:
    """Build an AIMessage with a list content containing text + tool_use block."""
    content = [
        {"type": "text", "text": text},
        {"type": "tool_use", "id": tool_use_id, "name": name, "input": input_},
    ]
    tool_calls = (
        [{"name": name, "args": input_, "id": tool_use_id, "type": "tool_call"}]
        if in_tool_calls
        else []
    )
    return AIMessage(content=content, tool_calls=tool_calls)


def _assert_bedrock_tool_invariant(messages: list) -> None:
    """Assert every assistant tool_use is matched by the next human tool_result."""
    for index, message in enumerate(messages[:-1]):
        if not isinstance(message, AIMessage) or not isinstance(message.content, list):
            continue

        tool_use_ids = {
            block["id"]
            for block in message.content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        }
        if not tool_use_ids:
            continue

        next_message = messages[index + 1]
        tool_result_ids = (
            {
                block.get("tool_use_id")
                for block in next_message.content
                if isinstance(block, dict) and block.get("type") == "tool_result"
            }
            if isinstance(next_message, HumanMessage) and isinstance(next_message.content, list)
            else set()
        )
        assert tool_use_ids <= tool_result_ids


def test_plain_text_messages_pass_through_unchanged() -> None:
    messages = [
        HumanMessage(content="hello"),
        AIMessage(content="hi, how can I help?"),
        HumanMessage(content="find me a study room"),
    ]
    assert sanitize_tool_messages(messages) == messages


def test_matched_tool_use_and_tool_result_preserved() -> None:
    ai = _ai_with_tool_use_block(
        text="Let me search.",
        tool_use_id="toolu_1",
        name="search_rooms",
        input_={"query": "library"},
    )
    tool_msg = ToolMessage(content="found 3 rooms", tool_call_id="toolu_1")

    result = sanitize_tool_messages([HumanMessage(content="q"), ai, tool_msg])

    assert len(result) == 3
    assert isinstance(result[1], AIMessage)
    assert result[1].tool_calls == ai.tool_calls
    assert isinstance(result[2], HumanMessage)
    _assert_bedrock_tool_invariant(result)


def test_dangling_tool_use_block_in_content_is_stripped() -> None:
    ai = _ai_with_tool_use_block(
        text="Let me search.",
        tool_use_id="toolu_dangling",
        name="search_rooms",
        input_={"query": "library"},
        in_tool_calls=False,
    )

    result = sanitize_tool_messages([HumanMessage(content="q"), ai])

    assert result == [HumanMessage(content="q")]
    _assert_bedrock_tool_invariant(result)


def test_dangling_tool_call_without_matching_tool_message_stripped() -> None:
    ai = _ai_with_tool_use_block(
        text="Looking up.",
        tool_use_id="toolu_orphan",
        name="search_rooms",
        input_={"query": "library"},
    )

    result = sanitize_tool_messages([HumanMessage(content="q"), ai])

    assert result == [HumanMessage(content="q")]
    _assert_bedrock_tool_invariant(result)


def test_orphan_tool_message_at_start_is_dropped() -> None:
    orphan = ToolMessage(content="stale", tool_call_id="toolu_ghost")
    user = HumanMessage(content="what's up")

    result = sanitize_tool_messages([orphan, user])

    assert len(result) == 1
    assert isinstance(result[0], HumanMessage)
    assert result[0].content == [{"type": "text", "text": "what's up"}]
    _assert_bedrock_tool_invariant(result)


def test_tool_message_without_matching_preceding_tool_use_is_dropped() -> None:
    ai = AIMessage(content="sure")
    orphan = ToolMessage(content="stale", tool_call_id="toolu_ghost")
    user = HumanMessage(content="thanks")

    result = sanitize_tool_messages([user, ai, orphan, user])

    assert len(result) == 3
    assert all(not isinstance(message, ToolMessage) for message in result)
    _assert_bedrock_tool_invariant(result)


def test_multiple_pairs_interleaved_partial_match() -> None:
    """AIMessage has two tool_use blocks, but only one has a matching result."""
    content = [
        {"type": "text", "text": "doing both"},
        {
            "type": "tool_use",
            "id": "toolu_a",
            "name": "tool_a",
            "input": {"x": 1},
        },
        {
            "type": "tool_use",
            "id": "toolu_b",
            "name": "tool_b",
            "input": {"y": 2},
        },
    ]
    ai = AIMessage(
        content=content,
        tool_calls=[
            {"name": "tool_a", "args": {"x": 1}, "id": "toolu_a", "type": "tool_call"},
            {"name": "tool_b", "args": {"y": 2}, "id": "toolu_b", "type": "tool_call"},
        ],
    )
    only_a_result = ToolMessage(content="ok a", tool_call_id="toolu_a")

    result = sanitize_tool_messages([HumanMessage(content="go"), ai, only_a_result])

    assert len(result) == 3
    cleaned = result[1]
    assert isinstance(cleaned, AIMessage)
    assert {tc["id"] for tc in cleaned.tool_calls} == {"toolu_a"}
    assert isinstance(cleaned.content, list)
    tool_use_ids = [
        b["id"] for b in cleaned.content if isinstance(b, dict) and b.get("type") == "tool_use"
    ]
    assert tool_use_ids == ["toolu_a"]
    assert isinstance(result[2], HumanMessage)
    _assert_bedrock_tool_invariant(result)


def test_ai_message_with_only_text_after_stripping_keeps_content_list() -> None:
    """When the assistant tail becomes invalid, sanitizer trims it away."""
    ai = _ai_with_tool_use_block(
        text="I will look it up.",
        tool_use_id="toolu_none",
        name="search_rooms",
        input_={"q": "x"},
        in_tool_calls=False,
    )

    result = sanitize_tool_messages([ai])

    assert result == []
    _assert_bedrock_tool_invariant(result)


def test_human_tool_result_content_is_preserved_when_already_merged() -> None:
    ai = _ai_with_tool_use_block(
        text="Let me search.",
        tool_use_id="toolu_1",
        name="search_rooms",
        input_={"query": "library"},
    )
    merged_human = HumanMessage(
        content=[
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": "found 3 rooms"},
            {"type": "text", "text": "next question"},
        ]
    )

    result = sanitize_tool_messages([HumanMessage(content="q"), ai, merged_human])

    assert len(result) == 3
    assert isinstance(result[1], AIMessage)
    assert isinstance(result[2], HumanMessage)
    assert isinstance(result[2].content, list)
    assert result[2].content[0]["type"] == "tool_result"
    _assert_bedrock_tool_invariant(result)


def test_tool_message_then_followup_user_text_stays_in_same_next_human_turn() -> None:
    ai = _ai_with_tool_use_block(
        text="Let me search.",
        tool_use_id="toolu_1",
        name="search_rooms",
        input_={"query": "library"},
    )
    tool_msg = ToolMessage(content="found 3 rooms", tool_call_id="toolu_1")

    result = sanitize_tool_messages(
        [HumanMessage(content="q"), ai, tool_msg, HumanMessage(content="thanks")]
    )

    assert len(result) == 3
    assert isinstance(result[2], HumanMessage)
    assert isinstance(result[2].content, list)
    assert [block["type"] for block in result[2].content if isinstance(block, dict)] == [
        "tool_result",
        "text",
    ]
    _assert_bedrock_tool_invariant(result)


def test_mismatched_tool_result_drops_trailing_assistant_prefill() -> None:
    ai = _ai_with_tool_use_block(
        text="checking",
        tool_use_id="toolu_bad",
        name="search_rooms",
        input_={"query": "library"},
    )
    mismatched_result = HumanMessage(
        content=[{"type": "tool_result", "tool_use_id": "toolu_other", "content": "oops"}]
    )

    result = sanitize_tool_messages([HumanMessage(content="q"), ai, mismatched_result])

    assert len(result) == 1
    assert isinstance(result[0], HumanMessage)
    assert result[0].content == "q"
