"""Base types for all specialist agents."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict


class AgentInput(BaseModel):
    """Standard input to every specialist agent."""

    model_config = ConfigDict(frozen=True)

    query: str
    session_id: str
    student_id: str
    context: dict[str, Any] = {}
    history: list[dict[str, str]] = []


class AgentAction(BaseModel):
    """A proposed action that may require human approval."""

    model_config = ConfigDict(frozen=True)

    action_type: str
    description: str
    payload: dict[str, Any] = {}
    requires_approval: bool = True


class AgentOutput(BaseModel):
    """Standard output from every specialist agent."""

    model_config = ConfigDict(frozen=True)

    agent: Literal["academic", "career", "social", "orchestrator"]
    message: str
    actions: list[AgentAction] = []
    data: dict[str, Any] = {}


class AgentProtocol(Protocol):
    """Protocol every specialist agent must satisfy."""

    async def run(self, agent_input: AgentInput) -> AgentOutput: ...


TOOL_DESCRIPTIONS: dict[str, str] = {
    # Academic
    "search_rooms": "Searched for available study rooms",
    "book_room": "Booked study room {room_id}",
    "search_lectures": "Searched lecture content for {course_id}",
    "get_progress": "Fetched concept progress for {course_id}",
    "take_quiz": "Generated quiz on {core_concept}",
    "get_lecture_slides": "Retrieved lecture slides for course {course_id}",
    "search_thesis_opportunities": "Searched thesis opportunities",
    "get_professor_contact": "Looked up professor contact details",
    "draft_thesis_email": "Drafted thesis inquiry email to {professor_name}",
    "get_prerequisites": "Fetched prerequisites for {topic}",
    "list_moodle_courses": "Listed enrolled Moodle courses",
    "list_course_uploads": "Listed uploads for course {moodle_course_id}",
    "get_deadlines": "Fetched upcoming deadlines",
    # Career
    "get_student_profile": "Fetched academic profile from TUMonline",
    "search_jobs": "Searched job listings",
    "audit_cv": "Audited CV for {target_role} roles",
    # Social
    "search_zhs_courses": "Searched ZHS sport courses",
    "get_zhs_course_schedule": "Fetched schedule for {course_name}",
    "book_zhs": "Booked ZHS course {course_name}",
    "search_events": "Searched ESN TUMi events",
    "get_event_details": "Fetched event details",
    "get_mensa_menu": "Fetched Mensa menu for {mensa}",
}


def extract_actions_from_messages(messages: list[Any]) -> list[AgentAction]:
    """Extract tool calls from LangGraph message history as AgentAction entries."""
    from langchain_core.messages import AIMessage

    actions: list[AgentAction] = []
    seen: set[str] = set()
    for msg in messages:
        if not isinstance(msg, AIMessage) or not msg.tool_calls:
            continue
        for tc in msg.tool_calls:
            name: str = tc["name"]
            if name in seen:
                continue
            seen.add(name)
            args: dict[str, Any] = tc.get("args", {})
            template = TOOL_DESCRIPTIONS.get(name, name.replace("_", " ").title())
            try:
                description = template.format(**args)
            except (KeyError, IndexError):
                description = template.split("{")[0].rstrip()
            actions.append(
                AgentAction(
                    action_type=name,
                    description=description,
                    payload=args,
                    requires_approval=name in {"book_room", "book_zhs", "draft_thesis_email"},
                )
            )
    return actions
