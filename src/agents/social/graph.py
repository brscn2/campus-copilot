"""LangGraph definition for the Social agent."""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.base import AgentInput, AgentOutput
from src.agents.social.prompts import SOCIAL_SYSTEM
from src.agents.social.state import SocialState
from src.agents.social.tools import (
    book_zhs,
    get_event_details,
    get_mensa_menu,
    get_zhs_course_schedule,
    search_events,
    search_zhs_courses,
)
from src.lib.bedrock import get_chat_model
from src.lib.logging import get_logger

logger = get_logger(__name__)

TOOLS = [
    search_zhs_courses,
    get_zhs_course_schedule,
    book_zhs,
    search_events,
    get_event_details,
    get_mensa_menu,
]


def _build_graph() -> StateGraph[SocialState]:
    """Construct the Social agent graph."""

    async def agent_node(state: SocialState) -> dict[str, Any]:
        system_prompt = SOCIAL_SYSTEM.format(
            today=date.today().isoformat(),
            student_id=state["student_id"],
        )
        llm = get_chat_model(model="sonnet", temperature=0.3, max_tokens=1024, system=system_prompt)
        llm_with_tools = llm.bind_tools(TOOLS)
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: SocialState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "end"

    graph = StateGraph(SocialState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": "__end__"})
    graph.add_edge("tools", "agent")

    return graph


_compiled_graph = _build_graph().compile()


async def run(agent_input: AgentInput) -> AgentOutput:
    """Public entrypoint — run the Social agent graph."""
    from langchain_core.messages import HumanMessage

    logger.info(
        "social_agent_run",
        student_id=agent_input.student_id,
        session_id=agent_input.session_id,
    )

    initial_state = SocialState(
        messages=[HumanMessage(content=agent_input.query)],
        student_id=agent_input.student_id,
        session_id=agent_input.session_id,
        pending_action=None,
    )

    result: Any = await _compiled_graph.ainvoke(initial_state)
    last_message = result["messages"][-1]
    response_text: str = last_message.content if isinstance(last_message.content, str) else ""

    return AgentOutput(
        agent="social",
        message=response_text,
        actions=[],
        data={},
    )
