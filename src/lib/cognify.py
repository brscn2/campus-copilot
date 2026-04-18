"""Cognify pipeline — triggers Cognee knowledge graph construction for course content."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Any

import httpx
import structlog

from src.config import get_settings
from src.exceptions import CogneeIngestionError

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
    job_id = f"cognify_{course_id}_{asyncio.get_event_loop().time():.0f}"
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

        # Auto-generate quizzes after cognify completes
        try:
            from src.lib.quiz import generate_quizzes_for_course

            await generate_quizzes_for_course(course_id)
            logger.info("quiz_generation_after_cognify_done", course_id=course_id)
        except Exception:
            logger.warning(
                "quiz_generation_after_cognify_failed",
                course_id=course_id,
                exc_info=True,
            )

    except httpx.HTTPStatusError as exc:
        _jobs[job_id]["status"] = CognifyStatus.FAILED
        _jobs[job_id]["error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        logger.error("cognify_failed", job_id=job_id, course_id=course_id, exc_info=True)
        raise CogneeIngestionError(f"Cognify failed for {course_id}") from exc
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
