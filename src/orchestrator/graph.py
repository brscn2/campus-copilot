"""Top-level orchestrator graph — routes user message to specialist agent."""

from __future__ import annotations

import asyncio
from typing import Any

from src.agents.base import AgentInput, AgentOutput
from src.lib.activity import log_activity
from src.lib.logging import get_logger
from src.lib.memory import query_memory
from src.lib.memory_extractor import BATCH_SIZE, extract_and_remember
from src.lib.session_store import store as session_store
from src.orchestrator.router import classify_intent

logger = get_logger(__name__)

AGENT_RUNNERS: dict[str, Any] = {}


def _get_agent_runner(agent_name: str) -> Any:
    """Lazy-load agent run functions to avoid circular imports."""
    if agent_name not in AGENT_RUNNERS:
        if agent_name == "academic":
            from src.agents.academic.graph import run as academic_run

            AGENT_RUNNERS["academic"] = academic_run
        elif agent_name == "career":
            from src.agents.career.graph import run as career_run

            AGENT_RUNNERS["career"] = career_run
        elif agent_name == "social":
            from src.agents.social.graph import run as social_run

            AGENT_RUNNERS["social"] = social_run
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
    history = await session_store.get_history(session_id)
    agent_name = await classify_intent(query)

    memories = await query_memory(user_id=student_id, query=query, top_k=3)
    memory_context: dict[str, Any] = {
        "memory": [m["content"] for m in memories] if memories else [],
    }

    logger.info(
        "orchestrator_dispatch",
        agent=agent_name,
        session_id=session_id,
        history_len=len(history),
        memory_count=len(memory_context["memory"]),
    )

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
        history=history,
        context=memory_context,
    )
    result: AgentOutput = await runner(agent_input)

    for action in result.actions:
        try:
            await log_activity(
                student_id=student_id,
                agent=agent_name,
                text=action.description[:120],
                metadata={"session_id": session_id, "action_type": action.action_type},
            )
        except Exception:
            logger.warning("activity_log_failed", exc_info=True)

    await session_store.append(
        session_id,
        student_id,
        [
            {"role": "user", "content": query},
            {"role": "assistant", "content": result.message},
        ],
    )

    history_after = await session_store.get_history(session_id)
    if len(history_after) >= BATCH_SIZE and len(history_after) % BATCH_SIZE == 0:
        recent_turns = history_after[-BATCH_SIZE:]
        asyncio.create_task(extract_and_remember(student_id=student_id, turns=recent_turns))

    return result
