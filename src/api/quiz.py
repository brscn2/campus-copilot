"""REST endpoints for quizzes, flashcards, summaries, and progress."""

from __future__ import annotations

# ruff: noqa: B008, TCH001, TCH002
import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.lib.quiz_serving import (
    get_course_progress,
    score_flashcards,
    score_quiz,
    serve_flashcards,
    serve_quiz,
    set_manual_mastery,
)
from src.lib.s3 import download_file, list_objects
from src.models.learning import (
    FlashcardRequest,
    FlashcardSubmission,
    QuizRequest,
    QuizSubmission,
    SetMasteryRequest,
)
from src.storage.db import get_session

router = APIRouter(prefix="/learning", tags=["learning"])


@router.post("/quiz")
async def request_quiz(
    body: QuizRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Request a personalized quiz session."""
    result = await serve_quiz(
        session,
        student_id=body.student_id,
        course_id=body.course_id,
        num_questions=body.num_questions,
        core_concepts=body.core_concepts,
    )
    return result.model_dump()


@router.post("/quiz/submit")
async def submit_quiz(
    body: QuizSubmission,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit quiz answers and get scores + mastery updates."""
    result = await score_quiz(session, body)
    return result.model_dump()


@router.post("/flashcards")
async def request_flashcards(
    body: FlashcardRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Request a personalized flashcard session."""
    result = await serve_flashcards(
        session,
        student_id=body.student_id,
        course_id=body.course_id,
        num_cards=body.num_cards,
        core_concepts=body.core_concepts,
    )
    return result.model_dump()


@router.post("/flashcards/submit")
async def submit_flashcards(
    body: FlashcardSubmission,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit flashcard ratings and get mastery updates."""
    result = await score_flashcards(session, body)
    return result.model_dump()


@router.get("/progress/{student_id}/{course_id}")
async def get_progress(
    student_id: str,
    course_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get student progress for a course."""
    return await get_course_progress(session, student_id, course_id)


@router.post("/mastery")
async def set_mastery(
    body: SetMasteryRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Manually set mastery for a core concept."""
    new_score = await set_manual_mastery(
        session,
        student_id=body.student_id,
        course_id=body.course_id,
        core_concept=body.core_concept,
        mastery=body.mastery,
    )
    return {"core_concept": body.core_concept, "mastery_score": new_score}


@router.get("/summaries/{course_id}")
async def list_summaries(course_id: str) -> list[dict[str, Any]]:
    """List available lecture summaries for a course."""
    prefix = f"summaries/course_{course_id}/"
    objects = await list_objects(prefix)
    summaries = []
    for obj in objects:
        try:
            data = await download_file(obj["key"])
            summaries.append(json.loads(data))
        except Exception:
            continue
    return summaries
