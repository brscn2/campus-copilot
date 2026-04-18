"""Pydantic models for Calendar Event."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs runtime access
from typing import Literal

from pydantic import BaseModel, ConfigDict


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
