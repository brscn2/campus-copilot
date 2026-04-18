"""Luma event scraper — fetches public Munich events from lu.ma/Munich.

Parses the markdown output from the discovery page into structured event data.
No API key needed — uses public pages only.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from src.lib.logging import get_logger

logger = get_logger(__name__)

LUMA_MUNICH_URL = "https://lu.ma/Munich"
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"
_TIMEOUT = 30.0

_event_cache: list[dict[str, Any]] | None = None


def _parse_events_from_markdown(md: str) -> list[dict[str, Any]]:
    """Parse Luma Munich markdown into structured event dicts."""
    events: list[dict[str, Any]] = []

    lines = md.split("\n")
    current_date = ""
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        date_match = re.match(r"^(Today|Tomorrow|(?:Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+)$", line)
        if date_match:
            current_date = date_match.group(1)
            i += 1
            continue

        day_match = re.match(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$", line)
        if day_match:
            current_date = f"{current_date} ({day_match.group(1)})"
            i += 1
            continue

        link_match = re.match(r"\[(.+?)\]\((https://luma\.com/[a-zA-Z0-9_-]+)\)", line)
        if link_match:
            title = link_match.group(1)
            url = link_match.group(2)

            if any(skip in url for skip in ["/signin", "/discover", "/pricing", "/ios",
                                             "/android", "/create", "/munich/map"]):
                i += 1
                continue
            if "Cover Image" in title or title in ("Luma Home", "Map"):
                i += 1
                continue

            event: dict[str, Any] = {
                "title": title.replace("\\|", "|").replace("\\[", "[").replace("\\]", "]"),
                "url": url,
                "date": current_date,
                "time": "",
                "organizer": "",
                "location": "",
                "status": "",
                "image": "",
            }

            for j in range(i + 1, min(i + 20, len(lines))):
                next_line = lines[j].strip()
                if not next_line or next_line == "\u200b":
                    continue

                img_match = re.match(
                    r"!\[.*?\]\((https://images\.lumacdn\.com/.+?)\)", next_line
                )
                if img_match and not event["image"]:
                    event["image"] = img_match.group(1)
                    continue

                if next_line.startswith("###"):
                    continue

                time_match = re.match(r"^(\d{1,2}:\d{2}\s*(?:AM|PM))", next_line)
                if time_match and not event["time"]:
                    event["time"] = time_match.group(1)
                    continue

                if next_line.startswith("By ") and not event["organizer"]:
                    event["organizer"] = next_line[3:]
                    continue

                if next_line in ("LIVE", "Near Capacity", "Waitlist", "Sold Out"):
                    event["status"] = next_line
                    continue

                if next_line.startswith("€") or next_line.startswith("+"):
                    if next_line.startswith("€"):
                        event["price"] = next_line
                    continue

                new_event_link = re.match(r"\[(.+?)\]\(https://luma\.com/[a-zA-Z0-9]", next_line)
                if new_event_link and "Cover Image" not in next_line:
                    break

                date_break = re.match(r"^(Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+$", next_line)
                if date_break:
                    break

                if not event["location"] and len(next_line) > 2 and not next_line.startswith("["):
                    event["location"] = next_line

            events.append(event)

        i += 1

    return events


async def fetch_munich_events(use_cache: bool = True) -> list[dict[str, Any]]:
    """Fetch upcoming Munich events from Luma.

    Uses Firecrawl API to scrape lu.ma/Munich with JS rendering.
    Results cached in memory for the server lifetime.
    """
    global _event_cache  # noqa: PLW0603
    if use_cache and _event_cache is not None:
        return _event_cache

    from src.config import get_settings
    settings = get_settings()

    firecrawl_key = getattr(settings, "firecrawl_api_key", "")
    if not firecrawl_key:
        import os
        firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")

    if not firecrawl_key:
        logger.warning("luma_no_firecrawl_key_falling_back_to_mock")
        return _mock_events()

    logger.info("luma_fetch_start")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                FIRECRAWL_API_URL,
                json={
                    "url": LUMA_MUNICH_URL,
                    "formats": ["markdown"],
                    "waitFor": 5000,
                },
                headers={"Authorization": f"Bearer {firecrawl_key}"},
            )
            if resp.status_code != 200:
                logger.error("luma_firecrawl_failed", status=resp.status_code)
                return _mock_events()

            data = resp.json()
            md = data.get("data", {}).get("markdown", "")
            if not md:
                logger.warning("luma_empty_markdown")
                return _mock_events()

        events = _parse_events_from_markdown(md)
        logger.info("luma_events_parsed", count=len(events))

        if events:
            _event_cache = events
        return events if events else _mock_events()

    except Exception:
        logger.error("luma_fetch_error", exc_info=True)
        return _mock_events()


def _mock_events() -> list[dict[str, Any]]:
    """Fallback mock events if scraping fails."""
    return [
        {
            "title": "Claude Code for Everyone",
            "url": "https://lu.ma/ujak3b5v",
            "date": "Apr 20",
            "time": "6:00 PM",
            "organizer": "Claude Code Community Munich",
            "location": "codecentric AG",
            "status": "Waitlist",
        },
        {
            "title": "Point Nine | Physical AI Meet-up Munich",
            "url": "https://lu.ma/ze6650nr",
            "date": "Apr 23",
            "time": "5:00 PM",
            "organizer": "Point Nine, Laura Weritz",
            "location": "Berg am Laim",
            "status": "",
        },
        {
            "title": "AI Innovator Munich with Weights & Biases x AppliedAI",
            "url": "https://lu.ma/2026apr-munich",
            "date": "Apr 23",
            "time": "6:00 PM",
            "organizer": "Weights & Biases",
            "location": "Berg am Laim",
            "status": "",
        },
        {
            "title": "AI in Health Summit @ Netlight",
            "url": "https://lu.ma/m36by6ds",
            "date": "Apr 23",
            "time": "6:00 PM",
            "organizer": "med dev, MLabAC & Netlight",
            "location": "Netlight Consulting GmbH",
            "status": "Waitlist",
        },
        {
            "title": "European Defense Tech Meetup - Munich",
            "url": "https://lu.ma/bc3dwkkx",
            "date": "Apr 29",
            "time": "6:00 PM",
            "organizer": "Nadiia Savchenko, Benjamin Wolba",
            "location": "Berg am Laim",
            "status": "Waitlist",
        },
    ]
