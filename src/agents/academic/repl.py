"""Interactive REPL for debugging the Academic agent.

Usage: python -m src.agents.academic.repl
"""

from __future__ import annotations

import asyncio

from src.agents.academic.graph import run
from src.agents.base import AgentInput


async def main() -> None:
    """Run an interactive loop for the Academic agent."""
    print("Academic Agent REPL — type 'quit' to exit")
    while True:
        query = input("\n> ")
        if query.strip().lower() in ("quit", "exit"):
            break
        agent_input = AgentInput(
            query=query,
            session_id="repl",
            student_id="demo-student",
        )
        output = await run(agent_input)
        print(f"\n[academic] {output.message}")
        if output.actions:
            for action in output.actions:
                print(f"  -> Action: {action.action_type}: {action.description}")


if __name__ == "__main__":
    asyncio.run(main())
