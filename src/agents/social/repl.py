"""Interactive REPL for debugging the Social agent.

Usage: python -m src.agents.social.repl
"""

from __future__ import annotations

import asyncio

from src.agents.base import AgentInput
from src.agents.social.graph import run


async def main() -> None:
    """Run an interactive loop for the Social agent."""
    print("Social Agent REPL — type 'quit' to exit")
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
        print(f"\n[social] {output.message}")
        if output.actions:
            for action in output.actions:
                print(f"  -> Action: {action.action_type}: {action.description}")


if __name__ == "__main__":
    asyncio.run(main())
