"""Pydantic models for TUM Mensa menus."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MensaDish(BaseModel):
    """A single dish from a TUM mensa menu."""

    model_config = ConfigDict(frozen=True)

    name: str
    dish_type: str = ""
    labels: list[str] = []
    price_student: str = ""
    price_base: float = 0.0
    price_per_unit: float = 0.0
    price_unit: str = ""
    is_vegetarian: bool = False
    is_vegan: bool = False

    def to_tool_dict(self) -> dict[str, object]:
        """Flat dict for LLM tool consumption."""
        return {
            "name": self.name,
            "dish_type": self.dish_type,
            "price": self.price_student,
            "is_vegetarian": self.is_vegetarian,
            "is_vegan": self.is_vegan,
            "labels": self.labels,
        }


class MensaInfo(BaseModel):
    """Metadata about a mensa location."""

    model_config = ConfigDict(frozen=True)

    canteen_id: str
    name: str
    address: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    open_hours: dict[str, dict[str, str]] = {}
