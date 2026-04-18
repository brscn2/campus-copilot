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
