"""Pydantic models for ESN TUMi events."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, ConfigDict


class EsnEvent(BaseModel):
    """An event from the ESN TUMi platform."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    description: str = ""
    start: datetime
    end: datetime
    location: str = ""
    organizer: str = ""
    price: str = "Free"
    registration_url: str = ""
    participant_limit: int = 0
    participant_count: int = 0
    is_free: bool = True

    @property
    def spots_available(self) -> int:
        if self.participant_limit == 0:
            return -1
        return max(0, self.participant_limit - self.participant_count)

    @property
    def is_full(self) -> bool:
        return self.participant_limit > 0 and self.spots_available == 0

    def to_tool_dict(self) -> dict[str, object]:
        """Flat dict for LLM tool consumption."""
        spots = "Unlimited" if self.spots_available == -1 else self.spots_available
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description[:300] if self.description else "",
            "date": self.start.strftime("%Y-%m-%d"),
            "time": self.start.strftime("%H:%M"),
            "end_time": self.end.strftime("%H:%M"),
            "location": self.location,
            "organizer": self.organizer,
            "price": self.price,
            "spots_available": spots,
            "is_full": self.is_full,
            "registration_url": self.registration_url,
        }
