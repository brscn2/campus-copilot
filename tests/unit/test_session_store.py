"""Unit tests for the Postgres-backed session store."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.lib.session_store import SessionStore


@pytest.fixture()
def _mock_repo() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Return mocked repository functions (get_history, append, clear)."""
    return AsyncMock(return_value=[]), AsyncMock(), AsyncMock()


@pytest.mark.asyncio
async def test_empty_session_returns_empty_list() -> None:
    store = SessionStore()
    with patch(
        "src.lib.session_store.session_repo.get_history",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await store.get_history("nonexistent")
    assert result == []


@pytest.mark.asyncio
async def test_append_and_retrieve() -> None:
    stored_turns: list[dict[str, str]] = []

    async def fake_append(
        _db: object,
        _sid: str,
        _student: str,
        messages: list[dict[str, str]],
        _max: int,
    ) -> None:
        stored_turns.extend(messages)

    async def fake_get(_db: object, _sid: str) -> list[dict[str, str]]:
        return list(stored_turns)

    store = SessionStore()
    with (
        patch("src.lib.session_store.session_repo.append", side_effect=fake_append),
        patch("src.lib.session_store.session_repo.get_history", side_effect=fake_get),
    ):
        await store.append("s1", "stu1", [{"role": "user", "content": "hello"}])
        await store.append("s1", "stu1", [{"role": "assistant", "content": "hi there"}])
        history = await store.get_history("s1")

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["content"] == "hi there"


@pytest.mark.asyncio
async def test_sessions_are_isolated() -> None:
    data: dict[str, list[dict[str, str]]] = {}

    async def fake_append(
        _db: object,
        sid: str,
        _student: str,
        messages: list[dict[str, str]],
        _max: int,
    ) -> None:
        data.setdefault(sid, []).extend(messages)

    async def fake_get(_db: object, sid: str) -> list[dict[str, str]]:
        return list(data.get(sid, []))

    store = SessionStore()
    with (
        patch("src.lib.session_store.session_repo.append", side_effect=fake_append),
        patch("src.lib.session_store.session_repo.get_history", side_effect=fake_get),
    ):
        await store.append("s1", "stu1", [{"role": "user", "content": "msg1"}])
        await store.append("s2", "stu1", [{"role": "user", "content": "msg2"}])

        assert len(await store.get_history("s1")) == 1
        assert len(await store.get_history("s2")) == 1
        assert (await store.get_history("s1"))[0]["content"] == "msg1"


@pytest.mark.asyncio
async def test_clear_delegates_to_repo() -> None:
    mock_clear = AsyncMock()
    store = SessionStore()
    with patch("src.lib.session_store.session_repo.clear", mock_clear):
        await store.clear("s1")

    mock_clear.assert_called_once()


@pytest.mark.asyncio
async def test_append_passes_student_id_and_max_turns() -> None:
    mock_append = AsyncMock()
    store = SessionStore(max_turns=10)
    with patch("src.lib.session_store.session_repo.append", mock_append):
        await store.append("s1", "stu-42", [{"role": "user", "content": "hi"}])

    _, kwargs = mock_append.call_args
    # positional args: db, session_id, student_id, messages, max_turns
    args = mock_append.call_args[0]
    assert args[1] == "s1"
    assert args[2] == "stu-42"
    assert args[4] == 10
