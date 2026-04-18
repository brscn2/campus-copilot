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
    """Get student progress for a course, including all known concepts from S3 cache."""
    from src.lib.content_generator import load_concepts_from_s3

    db_progress = await get_course_progress(session, student_id, course_id)

    cached = await load_concepts_from_s3(course_id)
    if cached:
        valid_names = {cc["name"] for cc in cached if cc.get("name")}

        # Filter DB concepts to only known core concepts
        db_progress["concepts"] = [
            c for c in db_progress["concepts"] if c["core_concept"] in valid_names
        ]

        # Add missing concepts with zero mastery
        existing_names = {c["core_concept"] for c in db_progress["concepts"]}
        for cc in cached:
            name = cc.get("name", "")
            if name and name not in existing_names:
                db_progress["concepts"].append({
                    "core_concept": name,
                    "mastery_score": 0.0,
                    "mastery_sources": {},
                    "manual_mastery": None,
                    "quizzes_taken": 0,
                    "quizzes_passed": 0,
                    "exercises_completed": 0,
                })

        # Recompute overall from filtered concepts only
        scores = [c["mastery_score"] for c in db_progress["concepts"]]
        db_progress["overall_mastery"] = sum(scores) / len(scores) if scores else 0.0

    return db_progress


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


@router.get("/concepts/{course_id}")
async def list_concepts(course_id: str) -> list[str]:
    """List available core concepts for a course (fast, reads from S3 cache)."""
    from src.lib.content_generator import load_concepts_from_s3

    cached = await load_concepts_from_s3(course_id)
    if cached:
        return [c["name"] for c in cached if c.get("name")]

    quiz_objects = await list_objects(f"quizzes/course_{course_id}/")
    return [
        obj["key"].split("/")[-1].replace(".json", "").replace("-", " ") for obj in quiz_objects
    ]


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


@router.get("/exercise-concepts/{course_id}/{exercise_name}")
async def get_exercise_concepts(course_id: str, exercise_name: str) -> dict[str, Any]:
    """Get the core concepts tested by an exercise."""
    from src.lib.memory import get_exercise_concept_map

    return await get_exercise_concept_map(course_id, exercise_name)


class MarkRequest(BaseModel):
    """Request to mark a lecture reviewed or exercise done."""

    student_id: str
    course_id: str
    item_title: str


@router.post("/mark-lecture-reviewed")
async def mark_lecture_reviewed(
    body: MarkRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Mark a lecture as reviewed — bumps mastery for related concepts."""
    from src.lib.memory import query_course_knowledge
    from src.lib.quiz_serving import _update_concept_mastery

    results = await query_course_knowledge(
        body.course_id,
        f"Which core concepts does the lecture '{body.item_title}' cover? "
        f"List just the concept names.",
    )

    updated: dict[str, float] = {}
    concept_names = _extract_concept_names(results)
    for concept in concept_names:
        new_score = await _update_concept_mastery(
            session,
            body.student_id,
            body.course_id,
            concept,
            signal="lecture",
            new_value=1.0,
            coverage=0.3,
        )
        updated[concept] = new_score
    await session.commit()
    return {"concepts_updated": updated}


@router.post("/mark-exercise-done")
async def mark_exercise_done(
    body: MarkRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Mark an exercise as done — bumps mastery for tested concepts."""
    from src.lib.memory import get_exercise_concept_map
    from src.lib.quiz_serving import _update_concept_mastery

    mapping = await get_exercise_concept_map(body.course_id, body.item_title)
    concept_names = _extract_concept_names(mapping.get("concept_mappings", []))

    updated: dict[str, float] = {}
    for concept in concept_names:
        new_score = await _update_concept_mastery(
            session,
            body.student_id,
            body.course_id,
            concept,
            signal="exercise",
            new_value=1.0,
            coverage=0.5,
        )
        updated[concept] = new_score
    await session.commit()
    return {"concepts_updated": updated}


def _extract_concept_names(results: list[str]) -> list[str]:
    """Extract concept names from Cognee search results."""
    from src.lib.memory import _try_parse_concepts_json

    names: list[str] = []
    for r in results:
        parsed = _try_parse_concepts_json(r)
        if parsed:
            names.extend(c["name"] for c in parsed)
        else:
            for part in r.replace(";", ",").split(","):
                clean = part.strip().strip(".-•*")
                if clean and 3 < len(clean) < 100:
                    names.append(clean)
    return list(dict.fromkeys(names))


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
