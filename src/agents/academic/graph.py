"""LangGraph definition for the Academic agent."""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.academic.prompts import ACADEMIC_SYSTEM
from src.agents.academic.state import AcademicState
from src.agents.academic.tools import (
    book_room,
    draft_thesis_email,
    get_deadlines,
    get_lecture_slides,
    get_my_courses,
    get_professor_contact,
    search_rooms,
    search_thesis_opportunities,
)
from src.agents.base import AgentInput, AgentOutput
from src.lib.bedrock import get_chat_model
from src.lib.logging import get_logger

logger = get_logger(__name__)

TOOLS = [
    search_rooms,
    book_room,
    search_thesis_opportunities,
    get_professor_contact,
    draft_thesis_email,
    get_my_courses,
    get_lecture_slides,
    get_deadlines,
]


def _build_graph() -> StateGraph[AcademicState]:
    """Construct the Academic agent graph."""
    llm = get_chat_model(model="sonnet", temperature=0.3, max_tokens=1024)
    llm_with_tools = llm.bind_tools(TOOLS)

    async def agent_node(state: AcademicState) -> dict[str, Any]:
        system = SystemMessage(
            content=ACADEMIC_SYSTEM.format(
                today=date.today().isoformat(),
                student_id=state["student_id"],
            )
        )
        messages = [system, *state["messages"]]
        response = await llm_with_tools.ainvoke(messages)
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
    from langchain_core.messages import HumanMessage

    logger.info(
        "academic_agent_run",
        student_id=agent_input.student_id,
        session_id=agent_input.session_id,
    )

    initial_state = AcademicState(
        messages=[HumanMessage(content=agent_input.query)],
        student_id=agent_input.student_id,
        session_id=agent_input.session_id,
        pending_action=None,
    )

    result: Any = await _compiled_graph.ainvoke(initial_state)
    last_message = result["messages"][-1]
    response_text: str = last_message.content if isinstance(last_message.content, str) else ""

    return AgentOutput(
        agent="academic",
        message=response_text,
        actions=[],
        data={},
    )
