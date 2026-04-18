"""Unit tests for the mock Mensa integration."""

from __future__ import annotations

import pytest

from src.integrations.mensa import get_menu


@pytest.mark.asyncio
async def test_get_menu_garching() -> None:
    items = await get_menu(mensa="mensa-garching")
    assert len(items) > 0
    for item in items:
        assert "name" in item
        assert "price_student" in item


@pytest.mark.asyncio
async def test_get_menu_arcisstrasse() -> None:
    items = await get_menu(mensa="mensa-arcisstrasse")
    assert len(items) > 0


@pytest.mark.asyncio
async def test_get_menu_vegetarian_filter() -> None:
    items = await get_menu(vegetarian_only=True)
    assert all(i["vegetarian"] for i in items)


@pytest.mark.asyncio
async def test_get_menu_vegan_filter() -> None:
    items = await get_menu(vegan_only=True)
    assert all(i["vegan"] for i in items)


@pytest.mark.asyncio
async def test_get_menu_unknown_mensa() -> None:
    items = await get_menu(mensa="mensa-nonexistent")
    assert items == []
