"""Mock ESN TUMi + Luma event integration.

In live mode this would scrape TUMi and Luma event pages.
For the hackathon demo, returns curated fake event data.
"""

from __future__ import annotations

from typing import Any

from src.lib.logging import get_logger

logger = get_logger(__name__)

MOCK_EVENTS: list[dict[str, Any]] = [
    {
        "id": "evt-001",
        "title": "International Beer Garden Night",
        "organizer": "ESN TUMi",
        "date": "2026-04-22",
        "time": "18:00",
        "location": "Augustiner Keller, Munich",
        "price": "Free (pay your own drinks)",
        "spots_available": 40,
        "description": "Meet fellow international students over Bavarian beer and pretzels.",
        "tags": ["social", "international", "outdoor"],
    },
    {
        "id": "evt-002",
        "title": "Hiking Trip — Zugspitze Day Tour",
        "organizer": "ESN TUMi",
        "date": "2026-04-26",
        "time": "07:00",
        "location": "Meeting point: Hauptbahnhof",
        "price": "25 € (includes Bayern-Ticket share)",
        "spots_available": 3,
        "description": "Day hike to Germany's highest peak. Moderate difficulty, bring layers.",
        "tags": ["sports", "hiking", "outdoor", "nature"],
    },
    {
        "id": "evt-003",
        "title": "AI/ML Hackathon — Reply Challenge",
        "organizer": "Reply x TUM",
        "date": "2026-04-25",
        "time": "09:00",
        "location": "TUM Garching, MW Building",
        "price": "Free",
        "spots_available": 0,
        "description": "24h hackathon building AI agents. Food and drinks provided.",
        "tags": ["tech", "hackathon", "AI", "coding"],
    },
    {
        "id": "evt-004",
        "title": "Movie Night — Oppenheimer (OV)",
        "organizer": "ESN TUMi",
        "date": "2026-04-23",
        "time": "19:30",
        "location": "TUM Audimax",
        "price": "3 €",
        "spots_available": 100,
        "description": "Screening of Oppenheimer in original version with subtitles.",
        "tags": ["culture", "movie", "indoor"],
    },
    {
        "id": "evt-005",
        "title": "Startup Networking Mixer",
        "organizer": "UnternehmerTUM",
        "date": "2026-04-24",
        "time": "18:30",
        "location": "UnternehmerTUM, Garching",
        "price": "Free",
        "spots_available": 20,
        "description": "Network with Munich startup founders and fellow entrepreneurial students.",
        "tags": ["networking", "startup", "career"],
    },
]


async def search_events(
    *,
    keyword: str | None = None,
    tags: list[str] | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search for upcoming social events.

    Args:
        keyword: Keyword to match against title/description.
        tags: Tags to filter by (matches if any overlap).
        available_only: Only return events with open spots.

    Returns:
        List of matching event dicts.
    """
    logger.info("esn_tumi_search_events", keyword=keyword, tags=tags)

    results: list[dict[str, Any]] = []
    for event in MOCK_EVENTS:
        if available_only and event["spots_available"] == 0:
            continue
        if keyword and keyword.lower() not in f"{event['title']} {event['description']}".lower():
            continue
        if tags:
            event_tags: list[str] = event["tags"]
            if not any(t.lower() in [et.lower() for et in event_tags] for t in tags):
                continue
        results.append(event)

    return results
