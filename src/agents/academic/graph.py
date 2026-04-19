"""LangGraph definition for the Academic agent."""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.academic.prompts import ACADEMIC_SYSTEM
from src.agents.academic.state import AcademicState
from src.agents.academic.tools import (
    book_room,
    draft_thesis_email,
    get_deadlines,
    get_lecture_slides,
    get_prerequisites,
    get_professor_contact,
    get_progress,
    list_course_uploads,
    list_library_branches,
    list_moodle_courses,
    search_lectures,
    search_rooms,
    search_thesis_opportunities,
    take_quiz,
    verify_library_booking,
)
from src.agents.base import AgentInput, AgentOutput, extract_actions_from_messages
from src.lib.bedrock import get_chat_model
from src.lib.logging import get_logger
from src.lib.message_hygiene import sanitize_tool_messages

logger = get_logger(__name__)

TOOLS = [
    list_library_branches,
    search_rooms,
    book_room,
    verify_library_booking,
    search_lectures,
    get_progress,
    take_quiz,
    get_prerequisites,
    list_moodle_courses,
    list_course_uploads,
    get_lecture_slides,
    get_deadlines,
    search_thesis_opportunities,
    get_professor_contact,
    draft_thesis_email,
]


def _build_graph() -> StateGraph[AcademicState]:
    """Construct the Academic agent graph."""

    async def agent_node(state: AcademicState) -> dict[str, Any]:
        system_prompt = ACADEMIC_SYSTEM.format(
            today=date.today().isoformat(),
            student_id=state["student_id"],
            memory_section=state.get("memory_section", ""),
        )
        llm = get_chat_model(model="sonnet", temperature=0.3, max_tokens=1024, system=system_prompt)
        llm_with_tools = llm.bind_tools(TOOLS)
        sanitized = sanitize_tool_messages(state["messages"])
        response = await llm_with_tools.ainvoke(sanitized)
        return {"messages": [response]}

    def should_continue(state: AcademicState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "end"

    graph = StateGraph(AcademicState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": "__end__"})
    graph.add_edge("tools", "agent")

    return graph


_compiled_graph = _build_graph().compile()


async def run(agent_input: AgentInput) -> AgentOutput:
    """Public entrypoint — run the Academic agent graph.

    Args:
        agent_input: Standard agent input with query, session_id, student_id.

    Returns:
        AgentOutput with the response message and any proposed actions.
    """
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

    logger.info(
        "academic_agent_run",
        student_id=agent_input.student_id,
        session_id=agent_input.session_id,
        history_len=len(agent_input.history),
    )

    # Limit history to last 10 messages to avoid Bedrock message ordering issues
    recent_history = agent_input.history[-10:]
    history_msgs: list[BaseMessage] = []
    for turn in recent_history:
        if turn["role"] == "user":
            history_msgs.append(HumanMessage(content=turn["content"]))
        else:
            history_msgs.append(AIMessage(content=turn["content"]))

    memory_items: list[str] = agent_input.context.get("memory", [])
    memory_section = ""
    if memory_items:
        memory_section = "\n## What I Remember About You\n" + "\n".join(
            f"- {item}" for item in memory_items
        )

    initial_state = AcademicState(
        messages=[*history_msgs, HumanMessage(content=agent_input.query)],  # type: ignore[list-item]
        student_id=agent_input.student_id,
        session_id=agent_input.session_id,
        memory_section=memory_section,
        pending_action=None,
    )

    result: Any = await _compiled_graph.ainvoke(initial_state)
    last_message = result["messages"][-1]
    response_text: str = last_message.content if isinstance(last_message.content, str) else ""

    actions = extract_actions_from_messages(result["messages"])

    return AgentOutput(
        agent="academic",
        message=response_text,
        actions=actions,
        data={},
    )
