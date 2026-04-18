"""REST endpoints for quizzes, flashcards, summaries, and progress."""

from __future__ import annotations

# ruff: noqa: B008, TCH001, TCH002
import json
import re
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
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


class ContentItem(BaseModel):
    """A single course content item (lecture, exercise, or other)."""

    title: str
    filename: str
    s3_key: str
    size: int
    number: int | None = None


class CourseContentResponse(BaseModel):
    """Structured course content categorized by type."""

    lectures: list[ContentItem]
    exercises: list[ContentItem]
    other: list[ContentItem]


def _classify_and_parse_file(filename: str, s3_key: str, size: int) -> ContentItem:
    """
    Classify a file as lecture, exercise, or other and extract metadata.

    Args:
        filename: The filename without the leading number prefix.
        s3_key: The full S3 object key.
        size: The file size in bytes.

    Returns:
        A ContentItem with category, title, and number extracted.
    """
    filename_lower = filename.lower()

    # Remove .pdf extension
    title = filename.replace(".pdf", "")

    # Extract number from patterns like "Lecture 10", "Exercise 3", "Sheet 10", "Chapter 0"
    number = None
    number_patterns = [
        r"\blecture\s+(\d+)\b",
        r"\bexercise\s+(\d+)\b",
        r"\bsheet\s+(\d+)\b",
        r"\bchapter\s+(\d+)\b",
        r"\bvorlesung\s+(\d+)\b",
        r"\bübung\s+(\d+)\b",
    ]
    for pattern in number_patterns:
        match = re.search(pattern, filename_lower)
        if match:
            number = int(match.group(1))
            break

    # Clean up title: remove extra whitespace and ___ artifacts
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"_{3,}", "", title)
    title = title.strip()

    return ContentItem(
        title=title,
        filename=filename,
        s3_key=s3_key,
        size=size,
        number=number,
    )


@router.get("/course-content/{course_id}")
async def get_course_content(course_id: str) -> CourseContentResponse:
    """
    List and categorize course content from S3.

    Parses S3 file listings into lectures, exercises, and other materials.
    Files are classified based on filename patterns and sorted by extracted number.

    Args:
        course_id: The course identifier.

    Returns:
        Structured course content with lectures, exercises, and other materials.
    """
    prefix = f"slides/{course_id}/"
    objects = await list_objects(prefix)

    lectures = []
    exercises = []
    other = []

    for obj in objects:
        s3_key = obj["key"]
        size = obj["size"]

        # Extract filename from S3 key
        # Remove prefix (slides/{course_id}/)
        filename = s3_key[len(prefix) :]

        # Remove leading N_ prefix (e.g., "2_..." → "...after underscore")
        match = re.match(r"^\d+_(.+)$", filename)
        if match:
            filename = match.group(1)

        # Parse and classify
        item = _classify_and_parse_file(filename, s3_key, size)

        # Categorize
        filename_lower = filename.lower()
        if any(keyword in filename_lower for keyword in ["exercise", "sheet", "übung"]):
            exercises.append(item)
        elif any(
            keyword in filename_lower for keyword in ["lecture", "slides", "chapter", "vorlesung"]
        ):
            lectures.append(item)
        else:
            other.append(item)

    # Sort lectures and exercises by number (items without numbers go to the end)
    lectures.sort(key=lambda x: (x.number is None, x.number if x.number is not None else 0))
    exercises.sort(key=lambda x: (x.number is None, x.number if x.number is not None else 0))

    return CourseContentResponse(
        lectures=lectures,
        exercises=exercises,
        other=other,
    )
