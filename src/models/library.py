"""Pydantic models for TUM Library room booking via anny.eu."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class LibraryBranch(BaseModel):
    """A TUM library branch on anny.eu."""

    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    address: str
    resource_types: list[str] = []
    booking_url: str = ""

    def to_tool_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "name": self.name,
            "address": self.address,
            "resource_types": self.resource_types,
        }


class LibraryRoom(BaseModel):
    """A bookable room inside a branch library."""

    model_config = ConfigDict(frozen=True)

    room_id: str
    name: str
    branch: str
    capacity: int = 0
    equipment: list[str] = []

    def to_tool_dict(self) -> dict[str, object]:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "branch": self.branch,
            "capacity": self.capacity,
            "equipment": self.equipment,
        }


class LibraryTimeSlot(BaseModel):
    """An available time slot for booking."""

    model_config = ConfigDict(frozen=True)

    start: str
    end: str
    available: bool = True


class LibrarySchedule(BaseModel):
    """Schedule info for a branch library's rooms."""

    model_config = ConfigDict(frozen=True)

    branch: str
    branch_slug: str
    date: str
    rooms: list[LibraryRoom] = []
    slots: list[LibraryTimeSlot] = []
    booking_url: str = ""
    constraints: dict[str, Any] = {}

    def to_tool_dict(self) -> dict[str, object]:
        return {
            "branch": self.branch,
            "date": self.date,
            "rooms": [r.to_tool_dict() for r in self.rooms],
            "slots": [
                {"start": s.start, "end": s.end, "available": s.available} for s in self.slots
            ],
            "constraints": self.constraints,
        }


class LibraryBookingResult(BaseModel):
    """Result of a room booking attempt."""

    model_config = ConfigDict(frozen=True)

    status: str
    message: str
    booking_id: str | None = None
    branch: str = ""
    room: str = ""
    date: str = ""
    start: str = ""
    end: str = ""
    num_persons: int = 3
    qr_code_base64: str | None = None
    calendar_link: str | None = None
    ics_data: str | None = None
    manage_url: str | None = None
    checkout_url: str | None = None
