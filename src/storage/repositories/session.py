"""Postgres-backed session repository for conversation history."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid5

import structlog
from sqlalchemy import select

from src.storage.schema import SessionRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

MAX_TURNS = 20

_NAMESPACE = UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def _normalize_id(session_id: str) -> str:
    """Return a valid UUID string, deriving one deterministically if needed."""
    try:
        UUID(session_id)
        return session_id
    except ValueError:
        return str(uuid5(_NAMESPACE, session_id))


async def get_history(
    db: AsyncSession,
    session_id: str,
) -> list[dict[str, str]]:
    """Return prior conversation turns for a session.

    Args:
        db: SQLAlchemy async session.
        session_id: Session identifier (UUID or arbitrary string).

    Returns:
        List of turn dicts, or empty list if session not found.
    """
    row_id = _normalize_id(session_id)
    result = await db.execute(select(SessionRow).where(SessionRow.id == row_id))
    row = result.scalar_one_or_none()
    if row is None:
        return []
    return list(row.turns)


async def append(
    db: AsyncSession,
    session_id: str,
    student_id: str,
    messages: list[dict[str, str]],
    max_turns: int = MAX_TURNS,
) -> None:
    """Append new messages to a session and trim to max_turns.

    Creates the session row if it does not exist.

    Args:
        db: SQLAlchemy async session.
        session_id: Session identifier (UUID or arbitrary string).
        student_id: Student FK, needed for row creation.
        messages: New turn dicts to append.
        max_turns: Maximum turns to retain.
    """
    row_id = _normalize_id(session_id)
    result = await db.execute(select(SessionRow).where(SessionRow.id == row_id))
    row = result.scalar_one_or_none()

    if row is None:
        turns = messages[-max_turns:]
        row = SessionRow(id=row_id, student_id=student_id, turns=turns)
        db.add(row)
    else:
        updated = list(row.turns) + messages
        row.turns = updated[-max_turns:]

    await db.commit()
    logger.debug("session_append", session_id=session_id, turn_count=len(row.turns))


async def clear(
    db: AsyncSession,
    session_id: str,
) -> None:
    """Clear all turns for a session.

    Args:
        db: SQLAlchemy async session.
        session_id: Session identifier (UUID or arbitrary string).
    """
    row_id = _normalize_id(session_id)
    result = await db.execute(select(SessionRow).where(SessionRow.id == row_id))
    row = result.scalar_one_or_none()
    if row is not None:
        row.turns = []
        await db.commit()
        logger.debug("session_clear", session_id=session_id)
