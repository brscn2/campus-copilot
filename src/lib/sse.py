"""Server-Sent Event helpers for streaming agent responses."""

from __future__ import annotations

import json
from typing import Any


def format_sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string.

    Args:
        event_type: One of 'thinking', 'tool_call', 'draft_ready', 'action_complete', 'final'.
        data: JSON-serializable payload.

    Returns:
        Formatted SSE event string.
    """
    payload = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"
