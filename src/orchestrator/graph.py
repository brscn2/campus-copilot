"""Top-level orchestrator graph — routes user message to specialist agent."""

from __future__ import annotations

from typing import Any

from src.agents.base import AgentInput, AgentOutput
from src.lib.logging import get_logger
from src.orchestrator.router import classify_intent

logger = get_logger(__name__)

AGENT_RUNNERS: dict[str, Any] = {}


def _get_agent_runner(agent_name: str) -> Any:
    """Lazy-load agent run functions to avoid circular imports."""
    if agent_name not in AGENT_RUNNERS:
        if agent_name == "academic":
            from src.agents.academic.graph import run

            AGENT_RUNNERS["academic"] = run
        else:
            AGENT_RUNNERS[agent_name] = None
    return AGENT_RUNNERS[agent_name]


async def run_orchestrator(
    *,
    query: str,
    session_id: str,
    student_id: str,
) -> AgentOutput:
    """Route a user message through the appropriate specialist agent.

    Args:
        query: The user's message.
        session_id: Conversation session identifier.
        student_id: The student's identifier.

    Returns:
        AgentOutput from the dispatched specialist agent.
    """
    agent_name = await classify_intent(query)
    logger.info("orchestrator_dispatch", agent=agent_name, session_id=session_id)

    runner = _get_agent_runner(agent_name)
    if runner is None:
        return AgentOutput(
            agent=agent_name,
            message=f"The {agent_name} agent is not yet implemented. Coming soon!",
        )

    agent_input = AgentInput(
        query=query,
        session_id=session_id,
        student_id=student_id,
    )
    result: AgentOutput = await runner(agent_input)
    return result
