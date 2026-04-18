"""Mock Mensa integration — daily menu fetch.

In live mode this would scrape the Studentenwerk München menu API.
For the hackathon demo, returns curated fake daily menus.
"""

from __future__ import annotations

from typing import Any

from src.lib.logging import get_logger

logger = get_logger(__name__)

MOCK_MENUS: dict[str, list[dict[str, Any]]] = {
    "mensa-garching": [
        {
            "name": "Schweineschnitzel mit Pommes",
            "category": "Hauptgericht",
            "price_student": "3.20 €",
            "allergens": ["gluten", "egg"],
            "vegetarian": False,
            "vegan": False,
        },
        {
            "name": "Gemüse-Curry mit Basmatireis",
            "category": "Hauptgericht",
            "price_student": "2.80 €",
            "allergens": [],
            "vegetarian": True,
            "vegan": True,
        },
        {
            "name": "Käsespätzle mit Röstzwiebeln",
            "category": "Hauptgericht",
            "price_student": "2.90 €",
            "allergens": ["gluten", "milk", "egg"],
            "vegetarian": True,
            "vegan": False,
        },
        {
            "name": "Caesar Salad mit Hähnchen",
            "category": "Beilage",
            "price_student": "1.80 €",
            "allergens": ["gluten", "milk", "egg"],
            "vegetarian": False,
            "vegan": False,
        },
    ],
    "mensa-arcisstrasse": [
        {
            "name": "Currywurst mit Pommes",
            "category": "Hauptgericht",
            "price_student": "2.60 €",
            "allergens": ["gluten"],
            "vegetarian": False,
            "vegan": False,
        },
        {
            "name": "Falafel-Bowl mit Hummus",
            "category": "Hauptgericht",
            "price_student": "3.00 €",
            "allergens": ["sesame"],
            "vegetarian": True,
            "vegan": True,
        },
        {
            "name": "Pasta Bolognese",
            "category": "Hauptgericht",
            "price_student": "2.40 €",
            "allergens": ["gluten"],
            "vegetarian": False,
            "vegan": False,
        },
    ],
}


async def get_menu(
    *,
    mensa: str = "mensa-garching",
    vegetarian_only: bool = False,
    vegan_only: bool = False,
) -> list[dict[str, Any]]:
    """Get today's Mensa menu.

    Args:
        mensa: Mensa identifier ('mensa-garching' or 'mensa-arcisstrasse').
        vegetarian_only: Only return vegetarian options.
        vegan_only: Only return vegan options.

    Returns:
        List of menu item dicts.
    """
    logger.info("mensa_get_menu", mensa=mensa, vegetarian_only=vegetarian_only)

    items = MOCK_MENUS.get(mensa, [])
    if vegan_only:
        items = [i for i in items if i["vegan"]]
    elif vegetarian_only:
        items = [i for i in items if i["vegetarian"]]

    return items
