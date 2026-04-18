"""Postgres-backed session store for conversation history."""

from __future__ import annotations

from src.lib.logging import get_logger
from src.storage.db import get_db_session
from src.storage.repositories import session as session_repo

logger = get_logger(__name__)

MAX_TURNS = 20


class SessionStore:
    """Async conversation history store backed by Postgres SessionRow."""

    def __init__(self, max_turns: int = MAX_TURNS) -> None:
        self._max_turns = max_turns

    async def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Return prior conversation turns for a session."""
        async with get_db_session() as db:
            return await session_repo.get_history(db, session_id)

    async def append(
        self,
        session_id: str,
        student_id: str,
        messages: list[dict[str, str]],
    ) -> None:
        """Append new messages and trim to max_turns."""
        async with get_db_session() as db:
            await session_repo.append(db, session_id, student_id, messages, self._max_turns)

    async def clear(self, session_id: str) -> None:
        """Clear history for a session."""
        async with get_db_session() as db:
            await session_repo.clear(db, session_id)


store = SessionStore()
