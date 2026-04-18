"""Unit tests for the in-memory session store."""

from __future__ import annotations

from src.lib.session_store import SessionStore


def test_empty_session_returns_empty_list() -> None:
    store = SessionStore()
    assert store.get_history("nonexistent") == []


def test_append_and_retrieve() -> None:
    store = SessionStore()
    store.append("s1", [{"role": "user", "content": "hello"}])
    store.append("s1", [{"role": "assistant", "content": "hi there"}])

    history = store.get_history("s1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["content"] == "hi there"


def test_sessions_are_isolated() -> None:
    store = SessionStore()
    store.append("s1", [{"role": "user", "content": "msg1"}])
    store.append("s2", [{"role": "user", "content": "msg2"}])

    assert len(store.get_history("s1")) == 1
    assert len(store.get_history("s2")) == 1
    assert store.get_history("s1")[0]["content"] == "msg1"


def test_trim_to_max_turns() -> None:
    store = SessionStore(max_turns=4)
    for i in range(6):
        store.append("s1", [{"role": "user", "content": f"msg-{i}"}])

    history = store.get_history("s1")
    assert len(history) == 4
    assert history[0]["content"] == "msg-2"
    assert history[-1]["content"] == "msg-5"


def test_clear_removes_session() -> None:
    store = SessionStore()
    store.append("s1", [{"role": "user", "content": "hello"}])
    store.clear("s1")
    assert store.get_history("s1") == []


def test_get_history_returns_copy() -> None:
    store = SessionStore()
    store.append("s1", [{"role": "user", "content": "hello"}])
    history = store.get_history("s1")
    history.append({"role": "user", "content": "injected"})
    assert len(store.get_history("s1")) == 1
