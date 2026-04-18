"""Academic agent LangGraph state definition."""

from __future__ import annotations

from typing import Any

from langgraph.graph import MessagesState


class AcademicState(MessagesState):
    """State passed between Academic agent graph nodes."""

    student_id: str
    session_id: str
    pending_action: dict[str, Any] | None
