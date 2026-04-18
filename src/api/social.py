"""REST endpoints for the Social tab — ZHS, events, mensa."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.integrations.esn_tumi import search_events
from src.integrations.mensa import get_menu
from src.integrations.zhs import search_courses

router = APIRouter(prefix="/social", tags=["social"])


@router.get("/zhs")
async def list_zhs_courses(
    category: str | None = None,
    day: str | None = None,
    keyword: str | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search ZHS sport courses."""
    return await search_courses(
        category=category, day=day, keyword=keyword, available_only=available_only
    )


@router.get("/events")
async def list_events(
    keyword: str | None = None,
    tags: str | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search social events."""
    tag_list = tags.split(",") if tags else None
    return await search_events(keyword=keyword, tags=tag_list, available_only=available_only)


@router.get("/mensa")
async def mensa_menu(
    mensa: str = "mensa-garching",
    vegetarian_only: bool = False,
    vegan_only: bool = False,
) -> list[dict[str, Any]]:
    """Get today's mensa menu."""
    return await get_menu(mensa=mensa, vegetarian_only=vegetarian_only, vegan_only=vegan_only)
