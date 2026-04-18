"""LangGraph definition for the Career agent."""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.base import AgentInput, AgentOutput
from src.agents.career.prompts import CAREER_SYSTEM
from src.agents.career.state import CareerState
from src.agents.career.tools import audit_cv, search_jobs
from src.lib.bedrock import get_chat_model
from src.lib.logging import get_logger

logger = get_logger(__name__)

TOOLS = [search_jobs, audit_cv]


def _build_graph() -> StateGraph[CareerState]:
    """Construct the Career agent graph."""

    async def agent_node(state: CareerState) -> dict[str, Any]:
        system_prompt = CAREER_SYSTEM.format(
            today=date.today().isoformat(),
            student_id=state["student_id"],
            memory_section=state.get("memory_section", ""),
        )
        llm = get_chat_model(model="sonnet", temperature=0.3, max_tokens=1024, system=system_prompt)
        llm_with_tools = llm.bind_tools(TOOLS)
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: CareerState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "end"

    graph = StateGraph(CareerState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": "__end__"})
    graph.add_edge("tools", "agent")

    return graph


_compiled_graph = _build_graph().compile()


async def run(agent_input: AgentInput) -> AgentOutput:
    """Public entrypoint — run the Career agent graph."""
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

    logger.info(
        "career_agent_run",
        student_id=agent_input.student_id,
        session_id=agent_input.session_id,
        history_len=len(agent_input.history),
    )

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

    initial_state = CareerState(
        messages=[*history_msgs, HumanMessage(content=agent_input.query)],  # type: ignore[list-item]
        student_id=agent_input.student_id,
        session_id=agent_input.session_id,
        memory_section=memory_section,
        pending_action=None,
    )

    result: Any = await _compiled_graph.ainvoke(initial_state)
    last_message = result["messages"][-1]
    response_text: str = last_message.content if isinstance(last_message.content, str) else ""

    return AgentOutput(
        agent="career",
        message=response_text,
        actions=[],
        data={},
    )
