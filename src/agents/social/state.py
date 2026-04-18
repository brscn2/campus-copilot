"""Social agent LangGraph state definition."""

from __future__ import annotations

from typing import Any

from langgraph.graph import MessagesState


class SocialState(MessagesState):
    """State passed between Social agent graph nodes."""

    student_id: str
    session_id: str
    memory_section: str
    pending_action: dict[str, Any] | None
