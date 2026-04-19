"""REST endpoints for the user profile — fetch from TUMonline, save to DB."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import select

from src.config import DEMO_STUDENT_ID
from src.exceptions import TUMAuthenticationError, TUMSystemUnavailableError
from src.integrations.tumonline import fetch_nat_student
from src.lib.logging import get_logger
from src.storage.db import get_db_session
from src.storage.schema import StudentRow

logger = get_logger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])

_TUM_USERNAME_RE = re.compile(r"^[a-z]{2}[0-9]{2}[a-z]{3}$")


class TumStudentResponse(BaseModel):
    """Data returned from the NAT Student API lookup."""

    firstname: str
    lastname: str
    email: str
    matriculation_number: str
    program: str


class ProfileData(BaseModel):
    """Editable profile fields."""

    first_name: str = ""
    last_name: str = ""
    email: str = ""
    program: str = ""
    semester: int = 1
    matriculation_number: str = ""


@router.get("/tum/{username}", response_model=TumStudentResponse)
async def fetch_tum_profile(
    username: str = Path(..., min_length=7, max_length=7),
) -> TumStudentResponse:
    """Fetch student data from the NAT Student API."""
    if not _TUM_USERNAME_RE.match(username):
        raise HTTPException(status_code=422, detail="Invalid TUM username format")

    try:
        data = await fetch_nat_student(username)
    except TUMAuthenticationError as exc:
        logger.error("nat_auth_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TUMSystemUnavailableError as exc:
        logger.error("nat_fetch_failed", username=username, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return TumStudentResponse(**data)


@router.get("", response_model=ProfileData)
async def get_profile() -> ProfileData:
    """Load the saved profile from the database."""
    async with get_db_session() as db:
        stmt = select(StudentRow).where(StudentRow.id == DEMO_STUDENT_ID)
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()

    if not row:
        return ProfileData()

    return ProfileData(
        first_name=row.first_name or "",
        last_name=row.last_name or "",
        email=row.tum_email or "",
        program=row.program or "",
        semester=row.semester or 1,
        matriculation_number=row.matriculation_number or "",
    )


@router.put("", response_model=ProfileData)
async def save_profile(body: ProfileData) -> ProfileData:
    """Save profile fields to the database."""
    async with get_db_session() as db:
        stmt = select(StudentRow).where(StudentRow.id == DEMO_STUDENT_ID)
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()

        if not row:
            raise HTTPException(status_code=404, detail="Student not found")

        row.first_name = body.first_name
        row.last_name = body.last_name
        row.tum_email = body.email
        row.program = body.program
        row.semester = body.semester
        row.matriculation_number = body.matriculation_number
        row.display_name = f"{body.first_name} {body.last_name}".strip()

        db.add(row)
        await db.commit()

    logger.info("profile_saved", student_id=DEMO_STUDENT_ID)
    return body
