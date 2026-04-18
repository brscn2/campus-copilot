"""Per-student overrides for synced-course metadata (semester, etc.).

The Moodle scraper derives ``semester`` / ``display_name`` / ``course_code`` from
the download folder name via regex (see ``src/api/pipeline.py``).  When the
regex misclassifies a course, the user can drag the card into the correct
semester in the UI; that correction is persisted here as a JSONB blob on
``StudentRow``.

Crucially, the override is **keyed by Cognee ``dataset_name``**, which is the
stable identifier shared with S3 (``slides/<dataset_name>/...``), Cognee
datasets, and ``quiz_attempts.course_id`` / ``flashcard_attempts.course_id`` /
``student_concept_progress.course_id``.  Nothing about the underlying course
data ever moves — only the *display* semester changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from src.storage.schema import StudentRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Single-tenant demo student.  Mirrors src/api/auth.py and src/api/calendar.py.
DEMO_STUDENT_ID = "00000000-0000-0000-0000-000000000001"


def resolve_student_id(student_id: str | None) -> str:
    """Map the frontend's ``"demo"`` placeholder to the seeded UUID."""
    if not student_id or student_id == "demo":
        return DEMO_STUDENT_ID
    return student_id


async def _get_or_create_student(db: AsyncSession, student_id: str) -> StudentRow:
    """Fetch the student row, creating a minimal placeholder if missing.

    Auto-creating keeps the override endpoints usable on a fresh DB without
    requiring ``scripts/seed_demo_student.py`` to have run first.
    """
    result = await db.execute(select(StudentRow).where(StudentRow.id == student_id))
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    row = StudentRow(
        id=student_id,
        tum_email=f"{student_id}@placeholder.local",
        display_name="Demo Student",
        program="",
        semester=0,
        priorities={},
        course_overrides={},
    )
    db.add(row)
    await db.flush()
    logger.info("student_row_created", student_id=student_id)
    return row


async def get_overrides(
    db: AsyncSession,
    student_id: str,
) -> dict[str, dict[str, str]]:
    """Return ``{dataset_name: {semester: ...}}`` for the given student."""
    sid = resolve_student_id(student_id)
    result = await db.execute(select(StudentRow).where(StudentRow.id == sid))
    row = result.scalar_one_or_none()
    if row is None:
        return {}
    return dict(row.course_overrides or {})


async def set_override(
    db: AsyncSession,
    student_id: str,
    dataset_name: str,
    semester: str,
) -> dict[str, dict[str, str]]:
    """Upsert ``semester`` for ``dataset_name`` and return the full override map."""
    sid = resolve_student_id(student_id)
    row = await _get_or_create_student(db, sid)
    overrides = dict(row.course_overrides or {})
    overrides[dataset_name] = {"semester": semester}
    row.course_overrides = overrides
    # JSONB mutation isn't auto-tracked unless we reassign or flag dirty.
    flag_modified(row, "course_overrides")
    await db.commit()
    logger.info(
        "course_override_set",
        student_id=sid,
        dataset_name=dataset_name,
        semester=semester,
    )
    return overrides


async def delete_override(
    db: AsyncSession,
    student_id: str,
    dataset_name: str,
) -> dict[str, dict[str, str]]:
    """Remove a single dataset's override and return the remaining map."""
    sid = resolve_student_id(student_id)
    result = await db.execute(select(StudentRow).where(StudentRow.id == sid))
    row = result.scalar_one_or_none()
    if row is None:
        return {}
    overrides = dict(row.course_overrides or {})
    if dataset_name in overrides:
        overrides.pop(dataset_name)
        row.course_overrides = overrides
        flag_modified(row, "course_overrides")
        await db.commit()
        logger.info("course_override_deleted", student_id=sid, dataset_name=dataset_name)
    return overrides


async def clear_overrides(
    db: AsyncSession,
    student_id: str,
) -> None:
    """Drop all overrides for the student."""
    sid = resolve_student_id(student_id)
    result = await db.execute(select(StudentRow).where(StudentRow.id == sid))
    row = result.scalar_one_or_none()
    if row is None:
        return
    row.course_overrides = {}
    flag_modified(row, "course_overrides")
    await db.commit()
    logger.info("course_overrides_cleared", student_id=sid)
