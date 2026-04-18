"""In-memory session store for conversation history.

Stores message turns per session_id. Can be swapped to Postgres SessionRow later.
"""

from __future__ import annotations

MAX_TURNS = 20


class SessionStore:
    """Thread-safe in-memory conversation history keyed by session_id."""

    def __init__(self, max_turns: int = MAX_TURNS) -> None:
        self._store: dict[str, list[dict[str, str]]] = {}
        self._max_turns = max_turns

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Return prior conversation turns for a session."""
        return list(self._store.get(session_id, []))

    def append(self, session_id: str, messages: list[dict[str, str]]) -> None:
        """Append new messages and trim to max_turns."""
        if session_id not in self._store:
            self._store[session_id] = []
        self._store[session_id].extend(messages)
        if len(self._store[session_id]) > self._max_turns:
            self._store[session_id] = self._store[session_id][-self._max_turns :]

    def clear(self, session_id: str) -> None:
        """Clear history for a session."""
        self._store.pop(session_id, None)


store = SessionStore()
