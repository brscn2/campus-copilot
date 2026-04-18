"""Pydantic models for Deadline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from datetime import datetime


class Deadline(BaseModel):
    """A dated obligation with priority scoring."""

    model_config = ConfigDict(frozen=True)

    id: str
    course: str
    task: str
    due: datetime
    weight: float
    mastery_gap: float = 0.0
    priority: float = 0.0
    source: str = "moodle"
