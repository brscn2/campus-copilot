"""Pydantic models for Course, Lecture, and Mastery."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Lecture(BaseModel):
    """A single lecture within a course."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    reviewed: bool = False
    summary: str | None = None


class Course(BaseModel):
    """Public-facing course model."""

    model_config = ConfigDict(frozen=True)

    id: str
    code: str
    name: str
    professor: str = ""
    chair: str = ""
    credits: int = 0
    mastery: float = 0.0
    new_slides: bool = False
    lectures: list[Lecture] = []
