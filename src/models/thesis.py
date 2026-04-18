"""Pydantic models for Thesis Opportunity."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ThesisOpportunity(BaseModel):
    """A matched thesis posting from a professor/chair."""

    model_config = ConfigDict(frozen=True)

    id: str
    professor: str
    chair: str
    topic: str
    match_score: float = 0.0
    reasoning: str = ""
    tags: list[str] = []
