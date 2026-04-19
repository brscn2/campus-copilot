"""GET /activity — recent agent activity feed."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from src.config import DEMO_STUDENT_ID
from src.storage.db import get_db_session
from src.storage.schema import AgentActivityRow

router = APIRouter(tags=["activity"])


class ActivityItem(BaseModel):
    """Single agent activity entry returned to the frontend."""

    id: str
    agent: str
    icon: str
    text: str
    created_at: datetime


class ActivityResponse(BaseModel):
    """Paginated activity feed."""

    activities: list[ActivityItem]


@router.get("/activity", response_model=ActivityResponse)
async def list_activity(
    student_id: str = Query(default=DEMO_STUDENT_ID),
    limit: int = Query(default=20, ge=1, le=100),
) -> ActivityResponse:
    """Return the most recent agent activities for a student."""
    async with get_db_session() as db:
        stmt = (
            select(AgentActivityRow)
            .where(AgentActivityRow.student_id == student_id)
            .order_by(AgentActivityRow.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return ActivityResponse(
        activities=[
            ActivityItem(
                id=row.id,
                agent=row.agent,
                icon=row.icon,
                text=row.text,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )
