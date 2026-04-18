"""Cognify pipeline — triggers Cognee knowledge graph construction for course content."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Any
from uuid import uuid4

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)

COGNIFY_CUSTOM_PROMPT = """\
Analyze the uploaded lecture and exercise content. Build a hierarchical concept tree:

1. **Domain**: The overarching subject area (e.g., "Software Engineering").
2. **CoreConcepts** (8-15 per course): Major syllabus topics used for progress tracking.
3. **SubConcepts**: Intermediate groupings under each CoreConcept.
4. **LeafConcepts**: Atomic, testable units of knowledge — precise enough for quiz generation.

For exercise content:
- Map each exercise question to the LeafConcepts it tests (TESTS relationship).
- Identify which CoreConcepts an exercise sheet covers.

For prerequisite relationships:
- Identify which CoreConcepts must be understood before others.
- Create PREREQUISITE edges between CoreConcepts.

Focus on precision: LeafConcept definitions should be specific enough that a quiz question \
can be generated from the definition alone.
"""


class CognifyStatus(StrEnum):
    """Pipeline execution status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


_jobs: dict[str, dict[str, Any]] = {}


def _dataset_name(course_id: str) -> str:
    settings = get_settings()
    return f"{settings.cognee_dataset_prefix}{course_id}"


async def trigger_cognify(course_id: str) -> str:
    """Trigger Cognee's cognify pipeline for a course dataset.

    Args:
        course_id: Course identifier.

    Returns:
        Job ID for status polling.
    """
    job_id = f"cognify_{course_id}_{uuid4().hex[:8]}"
    _jobs[job_id] = {
        "course_id": course_id,
        "status": CognifyStatus.PENDING,
        "error": None,
    }

    asyncio.create_task(_run_cognify(job_id, course_id))
    return job_id


async def _run_cognify(job_id: str, course_id: str) -> None:
    """Execute the cognify pipeline in the background."""
    _jobs[job_id]["status"] = CognifyStatus.RUNNING
    settings = get_settings()
    dataset = _dataset_name(course_id)

    logger.info("cognify_start", job_id=job_id, course_id=course_id, dataset=dataset)

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{settings.cognee_api_url}/api/v1/cognify",
                json={
                    "datasets": [dataset],
                    "customPrompt": COGNIFY_CUSTOM_PROMPT,
                },
                headers={"X-Api-Key": settings.cognee_api_key},
            )
            resp.raise_for_status()

        _jobs[job_id]["status"] = CognifyStatus.COMPLETED
        logger.info("cognify_completed", job_id=job_id, course_id=course_id)

        # Auto-generate all learning content (quizzes, flashcards, summaries)
        # after cognify completes. All content is regenerated on every run.
        # Future: use a concept manifest to diff and only regenerate changed concepts.
        try:
            from src.lib.content_generator import generate_all_for_course

            gen_result = await generate_all_for_course(course_id)
            logger.info(
                "content_generation_after_cognify_done",
                course_id=course_id,
                quizzes=gen_result.quizzes_generated,
                flashcards=gen_result.flashcards_generated,
                summaries=gen_result.summaries_generated,
            )
        except Exception:
            logger.warning(
                "content_generation_after_cognify_failed",
                course_id=course_id,
                exc_info=True,
            )

    except httpx.HTTPStatusError as exc:
        _jobs[job_id]["status"] = CognifyStatus.FAILED
        _jobs[job_id]["error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        logger.error("cognify_failed", job_id=job_id, course_id=course_id, exc_info=True)
    except Exception as exc:
        _jobs[job_id]["status"] = CognifyStatus.FAILED
        _jobs[job_id]["error"] = str(exc)[:200]
        logger.error("cognify_failed", job_id=job_id, course_id=course_id, exc_info=True)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    """Get the status of a cognify job.

    Args:
        job_id: The job identifier returned by trigger_cognify.

    Returns:
        Job status dict or None if not found.
    """
    return _jobs.get(job_id)


STUDENT_COGNIFY_PROMPT = """\
Analyze the accumulated facts about this student. Build a lightweight knowledge graph:

- **Interests**: Academic topics, research areas, hobbies.
- **Skills**: Programming languages, tools, frameworks.
- **Goals**: Career aspirations, degree targets, thesis directions.
- **Preferences**: Campus locations, scheduling patterns, communication style.
- **Constraints**: Time limitations, prerequisites not yet met.

Let relationships emerge naturally — connect interests to goals, skills to interests, \
constraints to preferences. Do not force a rigid hierarchy.
"""


async def trigger_student_cognify(student_id: str) -> None:
    """Trigger a lightweight cognify on a student's memory dataset.

    Runs best-effort: failures are logged but do not propagate.

    Args:
        student_id: Student identifier (used to build dataset name).
    """
    settings = get_settings()
    dataset = f"student_{student_id}"

    logger.info("student_cognify_start", student_id=student_id, dataset=dataset)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.cognee_api_url}/api/v1/cognify",
                json={
                    "datasets": [dataset],
                    "customPrompt": STUDENT_COGNIFY_PROMPT,
                },
                headers={"X-Api-Key": settings.cognee_api_key},
            )
            resp.raise_for_status()

        logger.info("student_cognify_completed", student_id=student_id)
    except Exception:
        logger.warning("student_cognify_failed", student_id=student_id, exc_info=True)


async def upload_file_to_cognee(
    course_id: str,
    file_content: bytes,
    filename: str,
) -> dict[str, Any]:
    """Upload a file to Cognee for a course dataset.

    Args:
        course_id: Course identifier.
        file_content: Raw file bytes.
        filename: Original filename.

    Returns:
        Cognee API response.
    """
    settings = get_settings()
    dataset = _dataset_name(course_id)

    logger.info("cognee_upload_file", course_id=course_id, filename=filename, dataset=dataset)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.cognee_api_url}/api/v1/add",
            files=[("data", (filename, file_content, "application/pdf"))],
            data={"datasetName": dataset},
            headers={"X-Api-Key": settings.cognee_api_key},
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result
