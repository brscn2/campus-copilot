"""Pydantic models for the Student entity."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Student(BaseModel):
    """Public-facing student model."""

    model_config = ConfigDict(frozen=True)

    id: str
    tum_email: str
    display_name: str
    program: str
    semester: int
    priorities: dict[str, int] = {}


class StudentCreate(BaseModel):
    """Input model for creating a student."""

    tum_email: str
    display_name: str
    program: str
    semester: int
