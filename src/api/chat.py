"""POST /chat — main conversational entrypoint with SSE streaming."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.lib.logging import get_logger
from src.lib.sse import format_sse_event

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    """User message to the orchestrator."""

    message: str
    session_id: str = "default"
    student_id: str = "demo-student"


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Route user message through the orchestrator and stream response."""

    async def event_stream() -> AsyncIterator[str]:
        logger.info(
            "chat_request",
            session_id=request.session_id,
            student_id=request.student_id,
        )

        yield format_sse_event("thinking", {"message": "Routing your request..."})

        # TODO(brscn): Wire to orchestrator graph
        yield format_sse_event(
            "final",
            {
                "message": "Campus Co-Pilot backend is running. Orchestrator not yet wired.",
                "agent": None,
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
