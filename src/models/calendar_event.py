"""Pydantic models for Calendar Event."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from datetime import datetime


class CalendarEvent(BaseModel):
    """Unified calendar event representation."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    agent: Literal["academic", "career", "social"] | None = None
    location: str = ""
    conflict: bool = False
