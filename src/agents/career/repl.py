"""Interactive REPL for debugging the Career agent.

Usage: python -m src.agents.career.repl
"""

from __future__ import annotations

import asyncio

from src.agents.base import AgentInput
from src.agents.career.graph import run
from src.config import DEMO_STUDENT_ID


async def main() -> None:
    """Run an interactive loop for the Career agent."""
    print("Career Agent REPL — type 'quit' to exit")
    while True:
        query = input("\n> ")
        if query.strip().lower() in ("quit", "exit"):
            break
        agent_input = AgentInput(
            query=query,
            session_id="repl",
            student_id=DEMO_STUDENT_ID,
        )
        output = await run(agent_input)
        print(f"\n[career] {output.message}")
        if output.actions:
            for action in output.actions:
                print(f"  -> Action: {action.action_type}: {action.description}")


if __name__ == "__main__":
    asyncio.run(main())
