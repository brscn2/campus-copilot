"""OAuth routes — Google Calendar consent flow."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from src.config import get_settings
from src.lib.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_STUDENT_ID = "demo_student"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


@router.get("/google")
async def google_auth_redirect() -> RedirectResponse:
    """Redirect to Google OAuth consent screen (or straight to frontend in mock mode)."""
    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        logger.info("google_auth_mock_redirect")
        return RedirectResponse(url=f"{settings.frontend_url}/calendar?connected=true")

    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
    )

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=DEMO_STUDENT_ID,
    )

    logger.info("google_auth_live_redirect")
    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
async def google_auth_callback(
    code: str = Query(...),
    state: str = Query(default=DEMO_STUDENT_ID),
) -> RedirectResponse:
    """Exchange authorization code for tokens and store them."""
    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        return RedirectResponse(url=f"{settings.frontend_url}/calendar?connected=true")

    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials

    token_data = json.dumps(
        {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
        }
    ).encode("utf-8")

    from sqlalchemy import select

    from src.storage.db import get_session
    from src.storage.schema import StudentRow

    async for session in get_session():
        result = await session.execute(select(StudentRow).where(StudentRow.id == state))
        student = result.scalar_one_or_none()
        if student:
            student.google_calendar_token = token_data
            await session.commit()
            logger.info("google_auth_token_stored", student_id=state)

    return RedirectResponse(url=f"{settings.frontend_url}/calendar?connected=true")
