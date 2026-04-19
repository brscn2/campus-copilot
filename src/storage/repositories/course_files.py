"""S3-backed course file sync, per-student progress tracking, and concept mastery.

Keeps ``CourseFileRow`` in sync with the S3 ``slides/`` prefix and provides
per-student completion toggles plus weighted mastery computation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.storage.repositories.course_overrides import DEMO_STUDENT_ID, resolve_student_id
from src.storage.schema import (
    CourseFileRow,
    FlashcardAttemptRow,
    StudentConceptProgressRow,
    StudentFileProgressRow,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants for mastery computation (Task 5)
# ---------------------------------------------------------------------------
FLASHCARD_RATING_MAP: dict[str, float] = {
    "again": 0.0,
    "hard": 0.33,
    "good": 0.66,
    "easy": 1.0,
}

WEIGHT_LECTURE: float = 0.20
WEIGHT_EXERCISE: float = 0.30
WEIGHT_QUIZ: float = 0.35
WEIGHT_FLASHCARD: float = 0.15

# ---------------------------------------------------------------------------
# Regex for detecting exercise-type files
# ---------------------------------------------------------------------------
_EXERCISE_RE = re.compile(
    r"exercise|übung|uebung|homework|assignment|aufgabe|blatt",
    re.IGNORECASE,
)

# Leading digits (possibly followed by a separator) at the start of a stem
_LEADING_NUM_RE = re.compile(r"^(\d+)")
_LEADING_NUM_SEP_RE = re.compile(r"^\d+[\s_.\-]*")

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    """Outcome of a single ``sync_course_files_from_s3`` run."""

    inserted: int
    deleted: int
    enriched: int


@dataclass
class ConceptMastery:
    """Per-concept mastery breakdown for one student + course."""

    concept: str
    mastery: float
    lecture_pct: float
    exercise_pct: float
    quiz_pct: float
    flashcard_pct: float
    manual_boost: float


# ---------------------------------------------------------------------------
# Filename parsing (pure functions)
# ---------------------------------------------------------------------------


def parse_category(filename: str) -> str:
    """Return ``"exercise"`` if filename matches exercise patterns, else ``"lecture"``."""
    if _EXERCISE_RE.search(filename):
        return "exercise"
    return "lecture"


def parse_sort_order(filename: str) -> int:
    """Extract the leading integer from the filename stem, default ``0``."""
    stem = PurePosixPath(filename).stem
    m = _LEADING_NUM_RE.match(stem)
    if m:
        return int(m.group(1))
    return 0


def parse_display_name(filename: str) -> str:
    """Human-friendly display name derived from a raw filename.

    Steps: strip extension, strip leading numbers + separators, replace
    underscores/dashes with spaces, collapse whitespace, title-case if the
    result is all lowercase.
    """
    stem = PurePosixPath(filename).stem
    name = _LEADING_NUM_SEP_RE.sub("", stem)
    if not name:
        name = stem
    name = name.replace("_", " ").replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    if name == name.lower():
        name = name.title()
    return name


# ---------------------------------------------------------------------------
# S3 list proxy (monkeypatched in tests)
# ---------------------------------------------------------------------------


async def list_objects(prefix: str) -> list[dict[str, Any]]:
    """Proxy for ``src.lib.s3.list_objects`` — extracted for testability."""
    from src.lib.s3 import list_objects as s3_list_objects

    return await s3_list_objects(prefix)


# ---------------------------------------------------------------------------
# S3 key parsing
# ---------------------------------------------------------------------------

_S3_PREFIX = "slides/"


def _parse_s3_key(key: str) -> dict[str, Any] | None:
    """Parse an S3 key into file metadata.

    Expected layout: ``slides/<dataset_name>/<filename>``.
    Returns ``None`` for non-file keys (fewer than 3 parts or empty filename).
    """
    parts = key.split("/")
    if len(parts) < 3:
        return None
    filename = parts[-1]
    if not filename:
        return None
    dataset_name = parts[1]
    return {
        "dataset_name": dataset_name,
        "s3_key": key,
        "filename": filename,
        "display_name": parse_display_name(filename),
        "category": parse_category(filename),
        "sort_order": parse_sort_order(filename),
    }


# ---------------------------------------------------------------------------
# Cognee enrichment helpers
# ---------------------------------------------------------------------------


def _extract_concept_names(response: list[Any]) -> list[str]:
    """Best-effort extraction of concept names from a Cognee search response."""
    concepts: list[str] = []
    for item in response:
        text = ""
        if isinstance(item, dict):
            text = str(item.get("search_result", item.get("answer", "")))
        elif hasattr(item, "search_result"):
            text = str(item.search_result)
        else:
            text = str(item)

        # Try JSON parse first
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                concepts.extend(str(c) for c in parsed)
                continue
            if isinstance(parsed, str):
                concepts.append(parsed)
                continue
        except (json.JSONDecodeError, TypeError):
            pass

        if text and len(text) > 2:
            concepts.append(text)
    return concepts


async def _enrich_new_files(db: AsyncSession, s3_keys: list[str]) -> int:
    """Query Cognee for core concepts of newly inserted files.

    Best-effort: catches all exceptions, logs warning, leaves
    ``core_concepts=[]`` on failure.

    Returns:
        Count of files successfully enriched.
    """
    enriched = 0
    for key in s3_keys:
        try:
            from src.lib.cognee_init import ensure_cognee

            await ensure_cognee()
            import cognee

            parts = key.split("/")
            dataset_name = parts[1] if len(parts) > 1 else ""
            filename = parts[-1] if parts else ""

            results = await cognee.recall(
                query_text=f"core concepts in {filename}",
                query_type=cognee.SearchType.GRAPH_COMPLETION,
                datasets=[dataset_name] if dataset_name else None,
            )
            concepts = _extract_concept_names(results)
            if concepts:
                result = await db.execute(
                    select(CourseFileRow).where(CourseFileRow.s3_key == key)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.core_concepts = concepts
                    enriched += 1
        except Exception:
            logger.warning("enrich_file_failed", s3_key=key, exc_info=True)
    return enriched


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


async def sync_course_files_from_s3(db: AsyncSession) -> SyncResult:
    """List S3, upsert new files, delete stale ones, attempt KG enrichment.

    Returns:
        A ``SyncResult`` with counts of inserted, deleted, and enriched files.
    """
    objects = await list_objects(_S3_PREFIX)
    s3_keys_seen: set[str] = set()
    new_keys: list[str] = []

    for obj in objects:
        key: str = obj["key"]
        parsed = _parse_s3_key(key)
        if parsed is None:
            continue
        s3_keys_seen.add(key)

        # Check existence
        existing = await db.execute(
            select(CourseFileRow).where(CourseFileRow.s3_key == key)
        )
        if existing.scalar_one_or_none() is not None:
            continue

        row = CourseFileRow(
            dataset_name=parsed["dataset_name"],
            s3_key=parsed["s3_key"],
            filename=parsed["filename"],
            display_name=parsed["display_name"],
            category=parsed["category"],
            sort_order=parsed["sort_order"],
            core_concepts=[],
        )
        db.add(row)
        new_keys.append(key)

    # Delete stale rows whose s3_key is no longer in S3
    all_rows_result = await db.execute(select(CourseFileRow))
    all_rows = all_rows_result.scalars().all()
    stale_ids = [r.id for r in all_rows if r.s3_key not in s3_keys_seen]
    deleted = 0
    if stale_ids:
        await db.execute(delete(CourseFileRow).where(CourseFileRow.id.in_(stale_ids)))
        deleted = len(stale_ids)

    await db.flush()

    # Best-effort enrichment
    enriched = 0
    if new_keys:
        enriched = await _enrich_new_files(db, new_keys)

    await db.commit()

    logger.info(
        "course_files_synced",
        inserted=len(new_keys),
        deleted=deleted,
        enriched=enriched,
    )
    return SyncResult(inserted=len(new_keys), deleted=deleted, enriched=enriched)


# ---------------------------------------------------------------------------
# File progress (Task 4)
# ---------------------------------------------------------------------------


async def get_files_with_progress(
    db: AsyncSession,
    student_id: str,
    dataset_name: str,
) -> list[dict[str, Any]]:
    """Return course files for *dataset_name* with per-student completion status.

    Performs a LEFT JOIN with ``StudentFileProgressRow`` so every file appears
    even if the student has never toggled it.  Results are ordered by
    ``category``, ``sort_order``, ``filename``.
    """
    sid = resolve_student_id(student_id)

    stmt = (
        select(
            CourseFileRow,
            StudentFileProgressRow.completed,
            StudentFileProgressRow.completed_at,
        )
        .outerjoin(
            StudentFileProgressRow,
            (StudentFileProgressRow.course_file_id == CourseFileRow.id)
            & (StudentFileProgressRow.student_id == sid),
        )
        .where(CourseFileRow.dataset_name == dataset_name)
        .order_by(CourseFileRow.category, CourseFileRow.sort_order, CourseFileRow.filename)
    )

    result = await db.execute(stmt)
    rows = result.all()

    out: list[dict[str, Any]] = []
    for file_row, completed, completed_at in rows:
        out.append(
            {
                "id": file_row.id,
                "dataset_name": file_row.dataset_name,
                "s3_key": file_row.s3_key,
                "filename": file_row.filename,
                "display_name": file_row.display_name,
                "category": file_row.category,
                "sort_order": file_row.sort_order,
                "core_concepts": file_row.core_concepts,
                "completed": bool(completed) if completed is not None else False,
                "completed_at": completed_at,
            }
        )
    return out


async def toggle_file_progress(
    db: AsyncSession,
    student_id: str,
    file_id: str,
    *,
    completed: bool,
) -> dict[str, Any]:
    """Upsert per-student file completion.

    Args:
        db: Async database session.
        student_id: Student UUID or ``"demo"``.
        file_id: ``CourseFileRow.id``.
        completed: Target state.

    Returns:
        Dict with ``file_id``, ``completed``, ``completed_at``.
    """
    sid = resolve_student_id(student_id)
    now = datetime.now(timezone.utc) if completed else None

    # Try to find an existing progress row
    stmt = select(StudentFileProgressRow).where(
        StudentFileProgressRow.student_id == sid,
        StudentFileProgressRow.course_file_id == file_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()

    if progress is not None:
        progress.completed = completed
        progress.completed_at = now
    else:
        progress = StudentFileProgressRow(
            student_id=sid,
            course_file_id=file_id,
            completed=completed,
            completed_at=now,
        )
        db.add(progress)

    await db.commit()

    logger.info(
        "file_progress_toggled",
        student_id=sid,
        file_id=file_id,
        completed=completed,
    )
    return {
        "file_id": file_id,
        "completed": completed,
        "completed_at": now,
    }


# ---------------------------------------------------------------------------
# Concept mastery computation (Task 5)
# ---------------------------------------------------------------------------


async def compute_concept_mastery(
    db: AsyncSession,
    student_id: str,
    dataset_name: str,
) -> list[ConceptMastery]:
    """Compute weighted mastery for every concept in a course.

    Signals and weights:
    - Lecture file completion:   20 %
    - Exercise file completion:  30 %
    - Quiz pass rate:            35 %
    - Flashcard ratings:         15 %
    - Manual boost additive (caps total at 100).

    Returns:
        Sorted by concept name, all floats rounded to 2 decimals.
    """
    sid = resolve_student_id(student_id)

    # 1. All course files for this dataset
    files_result = await db.execute(
        select(CourseFileRow).where(CourseFileRow.dataset_name == dataset_name)
    )
    files: list[CourseFileRow] = list(files_result.scalars().all())

    # 2. Student's completed files
    file_ids = [f.id for f in files]
    completed_ids: set[str] = set()
    if file_ids:
        prog_result = await db.execute(
            select(StudentFileProgressRow).where(
                StudentFileProgressRow.student_id == sid,
                StudentFileProgressRow.course_file_id.in_(file_ids),
                StudentFileProgressRow.completed.is_(True),
            )
        )
        completed_ids = {p.course_file_id for p in prog_result.scalars().all()}

    # 3. Discover all concepts: union of file core_concepts + concept progress rows
    concept_progress_result = await db.execute(
        select(StudentConceptProgressRow).where(
            StudentConceptProgressRow.student_id == sid,
            StudentConceptProgressRow.course_id == dataset_name,
        )
    )
    concept_progress_rows: list[StudentConceptProgressRow] = list(
        concept_progress_result.scalars().all()
    )
    cp_map: dict[str, StudentConceptProgressRow] = {
        r.core_concept: r for r in concept_progress_rows
    }

    all_concepts: set[str] = set(cp_map.keys())
    for f in files:
        for c in f.core_concepts or []:
            all_concepts.add(c)

    if not all_concepts:
        return []

    # 4. Flashcard attempts for student + course
    flash_result = await db.execute(
        select(FlashcardAttemptRow).where(
            FlashcardAttemptRow.student_id == sid,
            FlashcardAttemptRow.course_id == dataset_name,
        )
    )
    flash_rows: list[FlashcardAttemptRow] = list(flash_result.scalars().all())

    # 5. Build per-concept file counts
    concept_lecture_total: dict[str, int] = {}
    concept_lecture_done: dict[str, int] = {}
    concept_exercise_total: dict[str, int] = {}
    concept_exercise_done: dict[str, int] = {}

    for f in files:
        for c in f.core_concepts or []:
            if f.category == "lecture":
                concept_lecture_total[c] = concept_lecture_total.get(c, 0) + 1
                if f.id in completed_ids:
                    concept_lecture_done[c] = concept_lecture_done.get(c, 0) + 1
            elif f.category == "exercise":
                concept_exercise_total[c] = concept_exercise_total.get(c, 0) + 1
                if f.id in completed_ids:
                    concept_exercise_done[c] = concept_exercise_done.get(c, 0) + 1

    # 6. Build per-concept flashcard scores
    concept_flash_scores: dict[str, list[float]] = {}
    for fa in flash_rows:
        concepts = fa.core_concepts or []
        for _card_id, rating in (fa.card_ratings or {}).items():
            score = FLASHCARD_RATING_MAP.get(rating.lower(), 0.0)
            for c in concepts:
                concept_flash_scores.setdefault(c, []).append(score)

    # 7. Compute mastery per concept
    results: list[ConceptMastery] = []
    for concept in sorted(all_concepts):
        lec_total = concept_lecture_total.get(concept, 0)
        lec_done = concept_lecture_done.get(concept, 0)
        lecture_pct = (lec_done / lec_total * 100.0) if lec_total > 0 else 0.0

        ex_total = concept_exercise_total.get(concept, 0)
        ex_done = concept_exercise_done.get(concept, 0)
        exercise_pct = (ex_done / ex_total * 100.0) if ex_total > 0 else 0.0

        cp = cp_map.get(concept)
        quiz_taken = cp.quizzes_taken if cp else 0
        quiz_passed = cp.quizzes_passed if cp else 0
        quiz_pct = (quiz_passed / quiz_taken * 100.0) if quiz_taken > 0 else 0.0

        flash_scores = concept_flash_scores.get(concept, [])
        flashcard_pct = (
            (sum(flash_scores) / len(flash_scores) * 100.0) if flash_scores else 0.0
        )

        manual_boost = (cp.manual_mastery or 0.0) if cp else 0.0

        weighted = (
            lecture_pct * WEIGHT_LECTURE
            + exercise_pct * WEIGHT_EXERCISE
            + quiz_pct * WEIGHT_QUIZ
            + flashcard_pct * WEIGHT_FLASHCARD
            + manual_boost
        )
        mastery = min(weighted, 100.0)

        results.append(
            ConceptMastery(
                concept=concept,
                mastery=round(mastery, 2),
                lecture_pct=round(lecture_pct, 2),
                exercise_pct=round(exercise_pct, 2),
                quiz_pct=round(quiz_pct, 2),
                flashcard_pct=round(flashcard_pct, 2),
                manual_boost=round(manual_boost, 2),
            )
        )

    return results


async def set_manual_boost(
    db: AsyncSession,
    student_id: str,
    dataset_name: str,
    concept: str,
    boost: float,
) -> None:
    """Upsert ``manual_mastery`` on the ``StudentConceptProgressRow``.

    Creates the row if it does not exist yet.
    """
    sid = resolve_student_id(student_id)

    stmt = select(StudentConceptProgressRow).where(
        StudentConceptProgressRow.student_id == sid,
        StudentConceptProgressRow.course_id == dataset_name,
        StudentConceptProgressRow.core_concept == concept,
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row is not None:
        row.manual_mastery = boost
    else:
        row = StudentConceptProgressRow(
            student_id=sid,
            course_id=dataset_name,
            core_concept=concept,
            manual_mastery=boost,
        )
        db.add(row)

    await db.commit()
    logger.info(
        "manual_boost_set",
        student_id=sid,
        dataset_name=dataset_name,
        concept=concept,
        boost=boost,
    )
