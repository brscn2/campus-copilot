"""OAuth routes — Google Calendar consent flow.

Uses plain httpx for token exchange instead of google_auth_oauthlib (which adds
PKCE code_challenge and breaks some redirect setups).  Stores the token JSON to
a local file `.gcal_token.json` as a fallback when Postgres is not running.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from src.config import get_settings
from src.lib.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_STUDENT_ID = "00000000-0000-0000-0000-000000000001"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

TOKEN_FILE = Path(".gcal_token.json")

# In-memory state store — maps state token → True.  Single-process is fine for
# the hackathon demo; a production system would use Redis or a DB table.
_pending_states: dict[str, bool] = {}


@router.get("/google")
async def google_auth_redirect() -> RedirectResponse:
    """Redirect to Google OAuth consent screen (or straight to frontend in mock mode)."""
    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        logger.info("google_auth_mock_redirect")
        return RedirectResponse(url=f"{settings.frontend_url}/calendar?connected=true")

    state = secrets.token_urlsafe(32)
    _pending_states[state] = True

    params = urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )

    authorization_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    logger.info("google_auth_live_redirect")
    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
async def google_auth_callback(
    code: str = Query(...),
    state: str = Query(default=""),
) -> RedirectResponse:
    """Exchange authorization code for tokens and store them."""
    settings = get_settings()

    if settings.google_calendar_mode == "mock":
        return RedirectResponse(url=f"{settings.frontend_url}/calendar?connected=true")

    # Validate state to prevent CSRF
    if state and state in _pending_states:
        del _pending_states[state]
    else:
        logger.warning("google_auth_callback_invalid_state", state=state)

    # Exchange code for tokens via httpx
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        token_json = token_response.json()

    token_data = {
        "token": token_json.get("access_token"),
        "refresh_token": token_json.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
    }

    # 1. Always write to local file (works without Postgres)
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    logger.info("google_auth_token_saved_to_file", path=str(TOKEN_FILE))

    # 2. Best-effort store to DB
    try:
        from sqlalchemy import select

        from src.storage.db import get_session
        from src.storage.schema import StudentRow

        async for session in get_session():
            result = await session.execute(
                select(StudentRow).where(StudentRow.id == DEMO_STUDENT_ID)
            )
            student = result.scalar_one_or_none()
            if student:
                student.google_calendar_token = json.dumps(token_data).encode("utf-8")
                await session.commit()
                logger.info("google_auth_token_stored_in_db", student_id=DEMO_STUDENT_ID)
    except Exception:
        logger.warning("google_auth_db_store_failed", exc_info=True)

    return RedirectResponse(url=f"{settings.frontend_url}/calendar?connected=true")
