"""Pydantic models for Job listings."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Job(BaseModel):
    """A working-student, internship, or new-grad listing."""

    model_config = ConfigDict(frozen=True)

    id: str
    company: str
    title: str
    location: str = ""
    kind: Literal["working_student", "internship", "new_grad"] = "working_student"
    match_score: float = 0.0
    reasoning: str = ""
    salary: str = ""
    posted: str = ""
