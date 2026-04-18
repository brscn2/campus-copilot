"""Agent activity logging — persists autonomous actions to the database."""

from __future__ import annotations

from src.lib.logging import get_logger
from src.storage.db import get_db_session
from src.storage.schema import AgentActivityRow

logger = get_logger(__name__)

AGENT_ICONS: dict[str, str] = {
    "academic": "\U0001f4da",
    "career": "\U0001f4bc",
    "social": "\U0001f389",
}

DEFAULT_ICON = "\U0001f916"


async def log_activity(
    *,
    student_id: str,
    agent: str,
    text: str,
    icon: str | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    """Persist an agent activity entry and return its id.

    Args:
        student_id: The student this activity belongs to.
        agent: Agent name (academic, career, social).
        text: Human-readable description of the action.
        icon: Optional emoji override; defaults to per-agent icon.
        metadata: Optional key-value payload for structured data.

    Returns:
        The id of the created AgentActivityRow.
    """
    resolved_icon = icon or AGENT_ICONS.get(agent, DEFAULT_ICON)
    row = AgentActivityRow(
        student_id=student_id,
        agent=agent,
        icon=resolved_icon,
        text=text,
        metadata_=metadata or {},
    )
    async with get_db_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    logger.info(
        "agent_activity_logged",
        activity_id=row.id,
        agent=agent,
        text=text,
    )
    return str(row.id)
