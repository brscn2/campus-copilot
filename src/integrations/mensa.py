"""TUM Mensa integration via the eat-api.

Fetches real daily menus from https://tum-dev.github.io/eat-api.
Static JSON files served by GitHub Pages — no authentication required.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx

from src.exceptions import TUMSystemUnavailableError
from src.lib.logging import get_logger
from src.lib.retry import retry_external
from src.models.mensa import MensaDish, MensaInfo

logger = get_logger(__name__)

EAT_API_BASE = "https://tum-dev.github.io/eat-api"

POPULAR_CANTEENS = [
    "mensa-garching",
    "mensa-arcisstr",
    "mensa-leopoldstr",
    "mensa-lothstr",
    "mensa-martinsried",
    "mensa-pasing",
    "mensa-weihenstephan",
    "stucafe-boltzmannstr",
    "stucafe-garching",
    "fmi-bistro",
]

DIETARY_LABELS = {
    "VEGAN": "vegan",
    "VEGETARIAN": "vegetarian",
    "FISH": "fish",
    "MEAT": "meat",
    "BEEF": "beef",
    "PORK": "pork",
}


def _format_price(prices: dict[str, Any]) -> str:
    """Build a human-readable student price string."""
    student = prices.get("students", {})
    base = student.get("base_price", 0) or 0
    per_unit = student.get("price_per_unit", 0) or 0
    unit = student.get("unit", "")

    if per_unit and unit:
        parts = []
        if base:
            parts.append(f"€{base:.2f}")
        parts.append(f"€{per_unit:.2f}/{unit}")
        return " + ".join(parts)
    if base:
        return f"€{base:.2f}"
    return "N/A"


def _parse_dish(raw: dict[str, Any]) -> MensaDish:
    """Convert eat-api dish JSON into a MensaDish model."""
    labels = raw.get("labels", [])
    prices = raw.get("prices", {})
    student_prices = prices.get("students", {})

    return MensaDish(
        name=raw.get("name", ""),
        dish_type=raw.get("dish_type", ""),
        labels=[DIETARY_LABELS.get(lbl, lbl.lower()) for lbl in labels],
        price_student=_format_price(prices),
        price_base=student_prices.get("base_price", 0) or 0,
        price_per_unit=student_prices.get("price_per_unit", 0) or 0,
        price_unit=student_prices.get("unit", ""),
        is_vegetarian="VEGETARIAN" in labels,
        is_vegan="VEGAN" in labels,
    )


@retry_external()  # type: ignore[untyped-decorator]
async def _fetch_week_menu(canteen_id: str, target_date: date) -> list[dict[str, Any]]:
    """Fetch the weekly menu JSON for a canteen."""
    year, week, _ = target_date.isocalendar()
    url = f"{EAT_API_BASE}/{canteen_id}/{year}/{week}.json"

    logger.info("mensa_fetch_week", canteen_id=canteen_id, url=url)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise TUMSystemUnavailableError(f"eat-api returned {response.status_code}")
        data = response.json()

    days: list[dict[str, Any]] = data.get("days", [])
    return days


async def get_menu(
    *,
    mensa: str = "mensa-garching",
    target_date: date | None = None,
    vegetarian_only: bool = False,
    vegan_only: bool = False,
) -> list[dict[str, Any]]:
    """Get the mensa menu for a specific day.

    Args:
        mensa: Canteen slug from eat-api (e.g. 'mensa-garching', 'mensa-arcisstr').
        target_date: Date to fetch. Defaults to today.
        vegetarian_only: Only return vegetarian options.
        vegan_only: Only return vegan options.

    Returns:
        List of dish dicts formatted for tool/API consumption.
    """
    if target_date is None:
        target_date = datetime.now(tz=UTC).date()

    logger.info(
        "mensa_get_menu",
        mensa=mensa,
        date=target_date.isoformat(),
        vegetarian_only=vegetarian_only,
        vegan_only=vegan_only,
    )

    days = await _fetch_week_menu(mensa, target_date)

    target_str = target_date.isoformat()
    raw_dishes: list[dict[str, Any]] = []
    for day in days:
        if day.get("date") == target_str:
            raw_dishes = day.get("dishes", [])
            break

    dishes: list[MensaDish] = []
    for raw in raw_dishes:
        try:
            dishes.append(_parse_dish(raw))
        except (KeyError, ValueError):
            logger.warning("mensa_parse_error", dish_name=raw.get("name"), exc_info=True)
            continue

    if vegan_only:
        dishes = [d for d in dishes if d.is_vegan]
    elif vegetarian_only:
        dishes = [d for d in dishes if d.is_vegetarian]

    return [d.to_tool_dict() for d in dishes]


@retry_external()  # type: ignore[untyped-decorator]
async def get_canteens() -> list[dict[str, Any]]:
    """Fetch the list of available TUM canteens with metadata.

    Returns:
        List of canteen info dicts (id, name, address, hours).
    """
    url = f"{EAT_API_BASE}/enums/canteens.json"
    logger.info("mensa_fetch_canteens")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise TUMSystemUnavailableError(f"eat-api canteens returned {response.status_code}")
        raw_list: list[dict[str, Any]] = response.json()

    canteens: list[dict[str, Any]] = []
    for raw in raw_list:
        loc = raw.get("location", {})
        hours = raw.get("open_hours", {})
        info = MensaInfo(
            canteen_id=raw.get("canteen_id", ""),
            name=raw.get("name", ""),
            address=loc.get("address", ""),
            latitude=loc.get("latitude", 0),
            longitude=loc.get("longitude", 0),
            open_hours=hours,
        )
        canteens.append(
            {
                "canteen_id": info.canteen_id,
                "name": info.name,
                "address": info.address,
                "latitude": info.latitude,
                "longitude": info.longitude,
                "open_hours": info.open_hours,
            }
        )

    return canteens
