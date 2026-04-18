"""ESN TUMi event integration via public GraphQL API.

Fetches real event data from https://tumi.esn.world/graphql.
No authentication required for reading public events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from src.exceptions import TUMSystemUnavailableError
from src.lib.logging import get_logger
from src.lib.retry import retry_external
from src.models.event import EsnEvent

logger = get_logger(__name__)

ESN_GRAPHQL_URL = "https://tumi.esn.world/graphql"
ESN_BASE_URL = "https://tumi.esn.world"

_EVENTS_QUERY = """
query GetEvents($limit: Int, $after: DateTime, $search: String) {
  events(limit: $limit, after: $after, search: $search) {
    id
    title
    description
    start
    end
    location
    isVirtual
    participantLimit
    participantRegistrationCount
    prices
    organizer {
      id
      name
    }
  }
}
"""

_EVENT_DETAIL_QUERY = """
query GetEvent($id: ID!) {
  event(id: $id) {
    id
    title
    description
    start
    end
    location
    isVirtual
    onlineMeetingUrl
    participantLimit
    participantRegistrationCount
    prices
    organizer {
      id
      name
    }
  }
}
"""


def _parse_price(prices: Any) -> tuple[str, bool]:
    """Extract a human-readable price string and free flag from the GraphQL prices field."""
    if not prices:
        return "Free", True
    if isinstance(prices, dict) and prices.get("options"):
        options = prices["options"]
        if isinstance(options, list) and options:
            amounts = [opt.get("amount", 0) for opt in options if isinstance(opt, dict)]
            non_zero = [a for a in amounts if a and a > 0]
            if not non_zero:
                return "Free", True
            min_price = min(non_zero) / 100
            return f"€{min_price:.2f}", False
    return "Free", True


def _parse_event(raw: dict[str, Any]) -> EsnEvent:
    """Convert a raw GraphQL event node into an EsnEvent model."""
    organizer_name = ""
    if raw.get("organizer") and isinstance(raw["organizer"], dict):
        organizer_name = raw["organizer"].get("name", "")

    price_str, is_free = _parse_price(raw.get("prices"))

    return EsnEvent(
        id=raw["id"],
        title=raw.get("title", ""),
        description=raw.get("description", ""),
        start=datetime.fromisoformat(raw["start"]),
        end=datetime.fromisoformat(raw["end"]),
        location=raw.get("location", "") or ("Online" if raw.get("isVirtual") else ""),
        organizer=organizer_name or "ESN TUMi",
        price=price_str,
        is_free=is_free,
        registration_url=f"{ESN_BASE_URL}/events/{raw['id']}",
        participant_limit=raw.get("participantLimit") or 0,
        participant_count=raw.get("participantRegistrationCount") or 0,
    )


async def _graphql_request(
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a GraphQL request against the ESN TUMi API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            ESN_GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            headers={
                "Content-Type": "application/json",
                "Origin": ESN_BASE_URL,
            },
        )
        if response.status_code != 200:
            raise TUMSystemUnavailableError(f"ESN TUMi API returned {response.status_code}")
        data = response.json()
        if "errors" in data:
            logger.warning("esn_tumi_graphql_errors", errors=data["errors"])
        result: dict[str, Any] = data.get("data") or {}
        return result


@retry_external()  # type: ignore[untyped-decorator]
async def fetch_upcoming_events(
    *,
    limit: int = 20,
    search: str | None = None,
) -> list[EsnEvent]:
    """Fetch upcoming events from ESN TUMi.

    Args:
        limit: Maximum number of events to return.
        search: Optional text search against event titles/descriptions.

    Returns:
        List of parsed EsnEvent models sorted by start date.
    """
    logger.info("esn_tumi_fetch_events", limit=limit, search=search)

    variables: dict[str, Any] = {
        "limit": limit,
        "after": datetime.now(tz=UTC).isoformat(),
    }
    if search:
        variables["search"] = search

    data = await _graphql_request(_EVENTS_QUERY, variables)
    raw_events = data.get("events") or []

    events = []
    for raw in raw_events:
        try:
            events.append(_parse_event(raw))
        except (KeyError, ValueError):
            logger.warning("esn_tumi_parse_error", event_id=raw.get("id"), exc_info=True)
            continue

    return sorted(events, key=lambda e: e.start)


@retry_external()  # type: ignore[untyped-decorator]
async def fetch_event_detail(event_id: str) -> EsnEvent | None:
    """Fetch a single event by ID.

    Args:
        event_id: The ESN TUMi event ID.

    Returns:
        EsnEvent if found, None otherwise.
    """
    logger.info("esn_tumi_fetch_event_detail", event_id=event_id)

    data = await _graphql_request(_EVENT_DETAIL_QUERY, {"id": event_id})
    raw = data.get("event")
    if not raw:
        return None

    return _parse_event(raw)


async def search_events(
    *,
    keyword: str | None = None,
    tags: list[str] | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search upcoming ESN TUMi events — main tool interface.

    Args:
        keyword: Text search against event titles/descriptions.
        tags: Not used for GraphQL filtering (kept for API compat), applied client-side.
        available_only: Only return events with open spots.

    Returns:
        List of event dicts formatted for LLM tool consumption.
    """
    events = await fetch_upcoming_events(limit=30, search=keyword)

    if available_only:
        events = [e for e in events if not e.is_full]

    if tags:
        lower_tags = {t.lower() for t in tags}
        filtered = []
        for event in events:
            searchable = f"{event.title} {event.description} {event.location}".lower()
            if any(tag in searchable for tag in lower_tags):
                filtered.append(event)
        events = filtered

    return [e.to_tool_dict() for e in events]
