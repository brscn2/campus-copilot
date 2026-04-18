"""Pydantic models for Booking."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs runtime access
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Booking(BaseModel):
    """A reservation made by the system."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["study_room", "zhs", "event", "lunch"]
    status: Literal["pending", "confirmed", "failed"] = "pending"
    starts_at: datetime
    ends_at: datetime
    payload: dict[str, Any] = {}
    calendar_event_id: str | None = None
