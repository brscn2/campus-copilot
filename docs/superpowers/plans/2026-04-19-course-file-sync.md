# Course File Sync & Mastery Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-sync S3 course files to Postgres, let students toggle lecture/exercise completion, and compute per-concept mastery on-the-fly from file progress, quizzes, flashcards, and a manual boost.

**Architecture:** Two new tables (`course_files`, `student_file_progress`) added to the existing SQLAlchemy schema. A sync function scans S3 on startup and after pipeline ingest, upserting file rows and enriching them with Cognee KG concepts. Mastery is computed at query time by joining file progress, quiz/flashcard data, and the existing `manual_mastery` column. New API endpoints expose files, progress toggles, concept mastery, and manual boost.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, Alembic, Cognee SDK, pytest + pytest-asyncio, SQLite for unit tests.

**Spec:** `docs/superpowers/specs/2026-04-19-course-file-sync-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/storage/schema.py` | Modify (append) | Add `CourseFileRow` and `StudentFileProgressRow` ORM models |
| `alembic/versions/a1b2c3d4e5f6_add_course_files.py` | Create | Migration for both new tables |
| `src/storage/repositories/course_files.py` | Create | Filename parsing, S3 sync, file queries, progress upsert, concept mastery computation, manual boost |
| `src/api/pipeline.py` | Modify (append) | 4 new endpoints: list files, toggle progress, get concepts, set boost |
| `src/main.py` | Modify (lifespan) | Call sync on startup |
| `tests/unit/test_course_files_repo.py` | Create | Unit tests for parsing, sync, progress, mastery computation |

---

## Task 1: ORM Models

**Files:**
- Modify: `src/storage/schema.py:203-216` (append after `AgentActivityRow`)

- [ ] **Step 1: Add `CourseFileRow` and `StudentFileProgressRow` to schema.py**

Append after the `AgentActivityRow` class at the end of `src/storage/schema.py`:

```python
class CourseFileRow(Base):
    """A file (PDF) synced from S3 — shared across all students."""

    __tablename__ = "course_files"

    dataset_name: Mapped[str] = mapped_column(String(100), index=True)
    s3_key: Mapped[str] = mapped_column(String(500), unique=True)
    filename: Mapped[str] = mapped_column(String(500))
    display_name: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    core_concepts: Mapped[list[str]] = mapped_column(JSONB, default=list)

    progress: Mapped[list[StudentFileProgressRow]] = relationship(
        back_populates="course_file", cascade="all, delete-orphan"
    )


class StudentFileProgressRow(Base):
    """Per-student completion tracking for a course file."""

    __tablename__ = "student_file_progress"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    course_file_id: Mapped[str] = mapped_column(
        ForeignKey("course_files.id", ondelete="CASCADE")
    )
    completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    course_file: Mapped[CourseFileRow] = relationship(back_populates="progress")

    __table_args__ = (
        Index(
            "uq_student_file_progress",
            "student_id",
            "course_file_id",
            unique=True,
        ),
    )
```

- [ ] **Step 2: Verify models load without import errors**

Run: `uv run python -c "from src.storage.schema import CourseFileRow, StudentFileProgressRow; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/storage/schema.py
git commit -m "feat: add CourseFileRow and StudentFileProgressRow ORM models"
```

---

## Task 2: Alembic Migration

**Files:**
- Create: `alembic/versions/a1b2c3d4e5f6_add_course_files.py`

- [ ] **Step 1: Generate the migration**

Run: `uv run alembic revision --autogenerate -m "add course_files and student_file_progress"`

This will create a new migration file in `alembic/versions/`. The revision ID will be auto-generated.

- [ ] **Step 2: Review the generated migration**

Open the generated file and verify it contains:
- `op.create_table('course_files', ...)` with all columns from `CourseFileRow`
- `op.create_table('student_file_progress', ...)` with the FK to `course_files` having `ondelete='CASCADE'`
- `op.create_index('ix_course_files_dataset_name', 'course_files', ['dataset_name'])`
- The unique index `uq_student_file_progress` on `(student_id, course_file_id)`
- A `downgrade()` that drops both tables in the correct order (progress first, then files)

If anything is missing, manually edit the file.

- [ ] **Step 3: Run the migration against the Docker Postgres**

Run: `uv run alembic upgrade head`
Expected: `Running upgrade ... -> ... add course_files and student_file_progress`

- [ ] **Step 4: Verify the tables exist**

Run: `docker compose exec postgres psql -U copilot -d campus_copilot -c "\dt course_files; \dt student_file_progress;"`
Expected: both tables listed.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat: add migration for course_files and student_file_progress"
```

---

## Task 3: Filename Parsing & Sync Logic

**Files:**
- Create: `src/storage/repositories/course_files.py`
- Test: `tests/unit/test_course_files_repo.py`

- [ ] **Step 1: Write failing tests for filename parsing**

Create `tests/unit/test_course_files_repo.py`:

```python
"""Unit tests for the course_files repository — parsing, sync, progress, mastery."""

from __future__ import annotations

import pytest

from src.storage.repositories.course_files import (
    parse_category,
    parse_display_name,
    parse_sort_order,
)


class TestFilenameParser:
    def test_lecture_default(self) -> None:
        assert parse_category("03_linear_algebra.pdf") == "lecture"

    def test_exercise_english(self) -> None:
        assert parse_category("exercise_sheet_03.pdf") == "exercise"

    def test_exercise_german_uebung(self) -> None:
        assert parse_category("Uebung_04.pdf") == "exercise"

    def test_exercise_german_umlaut(self) -> None:
        assert parse_category("Übung_02.pdf") == "exercise"

    def test_exercise_homework(self) -> None:
        assert parse_category("homework_1.pdf") == "exercise"

    def test_exercise_assignment(self) -> None:
        assert parse_category("Assignment_05.pdf") == "exercise"

    def test_exercise_aufgabe(self) -> None:
        assert parse_category("Aufgabenblatt_01.pdf") == "exercise"

    def test_exercise_blatt(self) -> None:
        assert parse_category("Blatt_07.pdf") == "exercise"

    def test_sort_order_leading_number(self) -> None:
        assert parse_sort_order("03_lecture.pdf") == 3

    def test_sort_order_no_number(self) -> None:
        assert parse_sort_order("introduction.pdf") == 0

    def test_sort_order_large_number(self) -> None:
        assert parse_sort_order("12_final_review.pdf") == 12

    def test_display_name_strips_number_and_ext(self) -> None:
        assert parse_display_name("03_binary_search_trees.pdf") == "Binary Search Trees"

    def test_display_name_handles_dashes(self) -> None:
        assert parse_display_name("07 - Graph Traversal.pdf") == "Graph Traversal"

    def test_display_name_no_number(self) -> None:
        assert parse_display_name("introduction.pdf") == "Introduction"

    def test_display_name_exercise(self) -> None:
        assert parse_display_name("exercise_sheet_03.pdf") == "Exercise Sheet 03"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_course_files_repo.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_category'`

- [ ] **Step 3: Implement the parsing functions**

Create `src/storage/repositories/course_files.py`:

```python
"""Course file inventory — S3 sync, progress tracking, and concept mastery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

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

_EXERCISE_RE = re.compile(
    r"(exercise|übung|uebung|homework|assignment|aufgabe|blatt)",
    re.IGNORECASE,
)
_LEADING_NUM_RE = re.compile(r"^(\d+)")
_LEADING_NUM_SEP_RE = re.compile(r"^\d+[\s_\-]*(?:-\s*)?")


def parse_category(filename: str) -> str:
    """Classify a filename as 'lecture' or 'exercise'."""
    return "exercise" if _EXERCISE_RE.search(filename) else "lecture"


def parse_sort_order(filename: str) -> int:
    """Extract a leading integer from the filename stem for natural ordering."""
    stem = PurePosixPath(filename).stem
    m = _LEADING_NUM_RE.match(stem)
    return int(m.group(1)) if m else 0


def parse_display_name(filename: str) -> str:
    """Derive a human-friendly display name from a filename."""
    stem = PurePosixPath(filename).stem
    name = _LEADING_NUM_SEP_RE.sub("", stem)
    if not name:
        name = stem
    name = name.replace("_", " ").replace("-", " ")
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name.title() if name == name.lower() else name
```

- [ ] **Step 4: Run parsing tests to verify they pass**

Run: `uv run pytest tests/unit/test_course_files_repo.py::TestFilenameParser -v`
Expected: all 14 tests PASS

- [ ] **Step 5: Write failing tests for S3 sync**

Append to `tests/unit/test_course_files_repo.py`:

```python
from typing import Any

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.storage.repositories.course_files import sync_course_files_from_s3
from src.storage.schema import Base, CourseFileRow


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _fake_s3_objects(keys: list[str]) -> list[dict[str, Any]]:
    """Build a minimal S3 object listing from key strings."""
    return [{"key": k, "size": 1024, "last_modified": "2026-01-01T00:00:00"} for k in keys]


def _mock_s3(monkeypatch, keys: list[str]) -> None:
    """Patch list_objects to return a fake S3 listing (async-compatible)."""

    async def _list(prefix: str) -> list[dict[str, Any]]:
        return _fake_s3_objects(keys)

    monkeypatch.setattr("src.storage.repositories.course_files.list_objects", _list)


class TestSyncCourseFiles:
    @pytest.mark.asyncio
    async def test_inserts_new_files(self, db_session, monkeypatch) -> None:
        _mock_s3(monkeypatch, [
            "slides/ml_course/01_intro.pdf",
            "slides/ml_course/02_trees.pdf",
            "slides/ml_course/exercise_01.pdf",
        ])
        result = await sync_course_files_from_s3(db_session)
        assert result.inserted == 3
        assert result.deleted == 0

        rows = (await db_session.execute(select(CourseFileRow))).scalars().all()
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_idempotent_second_run(self, db_session, monkeypatch) -> None:
        _mock_s3(monkeypatch, ["slides/ml_course/01_intro.pdf"])
        await sync_course_files_from_s3(db_session)
        result = await sync_course_files_from_s3(db_session)
        assert result.inserted == 0
        assert result.deleted == 0

    @pytest.mark.asyncio
    async def test_deletes_stale_files(self, db_session, monkeypatch) -> None:
        _mock_s3(monkeypatch, [
            "slides/ml_course/01_intro.pdf",
            "slides/ml_course/02_trees.pdf",
        ])
        await sync_course_files_from_s3(db_session)

        _mock_s3(monkeypatch, ["slides/ml_course/01_intro.pdf"])
        result = await sync_course_files_from_s3(db_session)
        assert result.deleted == 1
        rows = (await db_session.execute(select(CourseFileRow))).scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_parses_category_and_sort_order(self, db_session, monkeypatch) -> None:
        _mock_s3(monkeypatch, [
            "slides/ml_course/03_regression.pdf",
            "slides/ml_course/exercise_02.pdf",
        ])
        await sync_course_files_from_s3(db_session)
        rows = (
            (await db_session.execute(select(CourseFileRow).order_by(CourseFileRow.sort_order)))
            .scalars()
            .all()
        )
        exercise = [r for r in rows if r.category == "exercise"][0]
        lecture = [r for r in rows if r.category == "lecture"][0]
        assert lecture.sort_order == 3
        assert lecture.display_name == "Regression"
        assert exercise.sort_order == 0
        assert exercise.category == "exercise"

    @pytest.mark.asyncio
    async def test_skips_non_file_keys(self, db_session, monkeypatch) -> None:
        _mock_s3(monkeypatch, [
            "slides/ml_course/",
            "slides/",
        ])
        result = await sync_course_files_from_s3(db_session)
        assert result.inserted == 0
```

- [ ] **Step 6: Run sync tests to verify they fail**

Run: `uv run pytest tests/unit/test_course_files_repo.py::TestSyncCourseFiles -v`
Expected: FAIL — `ImportError: cannot import name 'sync_course_files_from_s3'`

- [ ] **Step 7: Implement `sync_course_files_from_s3`**

Append to `src/storage/repositories/course_files.py`:

```python
@dataclass
class SyncResult:
    """Summary of a sync operation."""

    inserted: int
    deleted: int
    enriched: int = 0


async def list_objects(prefix: str) -> list[dict[str, Any]]:
    """Proxy to S3 list_objects — extracted for testability."""
    from src.lib.s3 import list_objects as s3_list

    return await s3_list(prefix)


def _parse_s3_key(key: str) -> dict[str, str] | None:
    """Parse an S3 key into file metadata, or None if it's not a file."""
    parts = key.split("/")
    if len(parts) < 3 or not parts[2]:
        return None
    dataset_name = parts[1]
    filename = parts[2]
    return {
        "dataset_name": dataset_name,
        "s3_key": key,
        "filename": filename,
        "display_name": parse_display_name(filename),
        "category": parse_category(filename),
        "sort_order": str(parse_sort_order(filename)),
    }


async def sync_course_files_from_s3(db: AsyncSession) -> SyncResult:
    """Scan S3 slides/ prefix and upsert file rows into course_files.

    Args:
        db: Async database session.

    Returns:
        Summary of inserted/deleted counts.
    """
    objects = await list_objects("slides/")

    s3_files: dict[str, dict[str, str]] = {}
    for obj in objects:
        parsed = _parse_s3_key(obj["key"])
        if parsed:
            s3_files[parsed["s3_key"]] = parsed

    existing_result = await db.execute(select(CourseFileRow.s3_key))
    existing_keys: set[str] = {row[0] for row in existing_result.all()}

    new_keys = set(s3_files.keys()) - existing_keys
    stale_keys = existing_keys - set(s3_files.keys())

    for key in new_keys:
        meta = s3_files[key]
        db.add(
            CourseFileRow(
                dataset_name=meta["dataset_name"],
                s3_key=meta["s3_key"],
                filename=meta["filename"],
                display_name=meta["display_name"],
                category=meta["category"],
                sort_order=int(meta["sort_order"]),
                core_concepts=[],
            )
        )

    if stale_keys:
        await db.execute(
            delete(CourseFileRow).where(CourseFileRow.s3_key.in_(stale_keys))
        )

    await db.commit()

    enriched = 0
    if new_keys:
        enriched = await _enrich_new_files(db, new_keys)

    logger.info(
        "course_files_synced",
        inserted=len(new_keys),
        deleted=len(stale_keys),
        enriched=enriched,
    )
    return SyncResult(inserted=len(new_keys), deleted=len(stale_keys), enriched=enriched)


async def _enrich_new_files(db: AsyncSession, s3_keys: set[str]) -> int:
    """Query Cognee KG to populate core_concepts for newly synced files."""
    enriched = 0
    result = await db.execute(
        select(CourseFileRow).where(CourseFileRow.s3_key.in_(s3_keys))
    )
    rows = result.scalars().all()

    for row in rows:
        try:
            from src.lib.memory import query_course_knowledge

            response = await query_course_knowledge(
                row.dataset_name,
                f"Which core concepts does '{row.filename}' cover? "
                f"Return only concept names as a JSON list.",
            )
            concepts = _extract_concept_names(response)
            if concepts:
                row.core_concepts = concepts
                enriched += 1
        except Exception:
            logger.warning(
                "kg_enrichment_failed",
                s3_key=row.s3_key,
                exc_info=True,
            )
    await db.commit()
    return enriched


def _extract_concept_names(response: list[str]) -> list[str]:
    """Try to extract concept names from a Cognee response."""
    import json

    for text in response:
        text = text.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(c) for c in parsed if isinstance(c, str)]
        except (json.JSONDecodeError, ValueError):
            continue
    return []
```

- [ ] **Step 8: Run sync tests to verify they pass**

Run: `uv run pytest tests/unit/test_course_files_repo.py -v`
Expected: all tests PASS

- [ ] **Step 9: Run full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: all tests PASS

- [ ] **Step 10: Commit**

```bash
git add src/storage/repositories/course_files.py tests/unit/test_course_files_repo.py
git commit -m "feat: add course file S3 sync with filename parsing and tests"
```

---

## Task 4: Progress Toggle (per-student file completion)

**Files:**
- Modify: `src/storage/repositories/course_files.py` (append)
- Modify: `tests/unit/test_course_files_repo.py` (append)

- [ ] **Step 1: Write failing tests for progress toggle**

Append to `tests/unit/test_course_files_repo.py`:

```python
from src.storage.repositories.course_files import (
    get_files_with_progress,
    toggle_file_progress,
)
from src.storage.schema import StudentRow


@pytest_asyncio.fixture
async def db_with_files(db_session):
    """Session pre-populated with a student and some course files."""
    db_session.add(
        StudentRow(
            id="00000000-0000-0000-0000-000000000001",
            tum_email="demo@tum.de",
            display_name="Demo",
            program="",
            semester=0,
            priorities={},
            course_overrides={},
        )
    )
    db_session.add(
        CourseFileRow(
            id="file-1",
            dataset_name="ml_course",
            s3_key="slides/ml_course/01_intro.pdf",
            filename="01_intro.pdf",
            display_name="Intro",
            category="lecture",
            sort_order=1,
            core_concepts=["Basics"],
        )
    )
    db_session.add(
        CourseFileRow(
            id="file-2",
            dataset_name="ml_course",
            s3_key="slides/ml_course/exercise_01.pdf",
            filename="exercise_01.pdf",
            display_name="Exercise 01",
            category="exercise",
            sort_order=1,
            core_concepts=["Basics"],
        )
    )
    await db_session.commit()
    return db_session


class TestFileProgress:
    @pytest.mark.asyncio
    async def test_files_default_not_completed(self, db_with_files) -> None:
        files = await get_files_with_progress(
            db_with_files, "00000000-0000-0000-0000-000000000001", "ml_course"
        )
        assert len(files) == 2
        assert all(not f["completed"] for f in files)

    @pytest.mark.asyncio
    async def test_toggle_on(self, db_with_files) -> None:
        await toggle_file_progress(
            db_with_files, "00000000-0000-0000-0000-000000000001", "file-1", completed=True
        )
        files = await get_files_with_progress(
            db_with_files, "00000000-0000-0000-0000-000000000001", "ml_course"
        )
        lecture = [f for f in files if f["id"] == "file-1"][0]
        assert lecture["completed"] is True
        assert lecture["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_toggle_off(self, db_with_files) -> None:
        await toggle_file_progress(
            db_with_files, "00000000-0000-0000-0000-000000000001", "file-1", completed=True
        )
        await toggle_file_progress(
            db_with_files, "00000000-0000-0000-0000-000000000001", "file-1", completed=False
        )
        files = await get_files_with_progress(
            db_with_files, "00000000-0000-0000-0000-000000000001", "ml_course"
        )
        lecture = [f for f in files if f["id"] == "file-1"][0]
        assert lecture["completed"] is False
        assert lecture["completed_at"] is None

    @pytest.mark.asyncio
    async def test_files_ordered_by_category_then_sort_order(self, db_with_files) -> None:
        files = await get_files_with_progress(
            db_with_files, "00000000-0000-0000-0000-000000000001", "ml_course"
        )
        categories = [f["category"] for f in files]
        assert categories == ["exercise", "lecture"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_course_files_repo.py::TestFileProgress -v`
Expected: FAIL — `ImportError: cannot import name 'get_files_with_progress'`

- [ ] **Step 3: Implement `get_files_with_progress` and `toggle_file_progress`**

Append to `src/storage/repositories/course_files.py`:

```python
async def get_files_with_progress(
    db: AsyncSession,
    student_id: str,
    dataset_name: str,
) -> list[dict[str, Any]]:
    """Return all files for a dataset, annotated with the student's completion status.

    Args:
        db: Async database session.
        student_id: Student UUID.
        dataset_name: S3 folder name.

    Returns:
        List of file dicts with 'completed' and 'completed_at' fields.
    """
    sid = resolve_student_id(student_id)
    result = await db.execute(
        select(CourseFileRow)
        .where(CourseFileRow.dataset_name == dataset_name)
        .order_by(CourseFileRow.category, CourseFileRow.sort_order, CourseFileRow.filename)
    )
    files = result.scalars().all()

    progress_result = await db.execute(
        select(StudentFileProgressRow).where(
            StudentFileProgressRow.student_id == sid,
            StudentFileProgressRow.course_file_id.in_([f.id for f in files]),
        )
    )
    progress_map: dict[str, StudentFileProgressRow] = {
        p.course_file_id: p for p in progress_result.scalars().all()
    }

    out: list[dict[str, Any]] = []
    for f in files:
        p = progress_map.get(f.id)
        out.append(
            {
                "id": f.id,
                "dataset_name": f.dataset_name,
                "s3_key": f.s3_key,
                "filename": f.filename,
                "display_name": f.display_name,
                "category": f.category,
                "sort_order": f.sort_order,
                "core_concepts": f.core_concepts,
                "completed": p.completed if p else False,
                "completed_at": p.completed_at.isoformat() if p and p.completed_at else None,
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
    """Upsert a student's completion status for a file.

    Args:
        db: Async database session.
        student_id: Student UUID.
        file_id: CourseFileRow id.
        completed: Whether to mark as done.

    Returns:
        The updated progress dict.
    """
    sid = resolve_student_id(student_id)
    now = datetime.now(timezone.utc) if completed else None

    result = await db.execute(
        select(StudentFileProgressRow).where(
            StudentFileProgressRow.student_id == sid,
            StudentFileProgressRow.course_file_id == file_id,
        )
    )
    row = result.scalar_one_or_none()

    if row:
        row.completed = completed
        row.completed_at = now
    else:
        row = StudentFileProgressRow(
            student_id=sid,
            course_file_id=file_id,
            completed=completed,
            completed_at=now,
        )
        db.add(row)

    await db.commit()
    return {
        "student_id": sid,
        "course_file_id": file_id,
        "completed": row.completed,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }
```

- [ ] **Step 4: Run progress tests to verify they pass**

Run: `uv run pytest tests/unit/test_course_files_repo.py::TestFileProgress -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/storage/repositories/course_files.py tests/unit/test_course_files_repo.py
git commit -m "feat: add per-student file progress toggle with tests"
```

---

## Task 5: On-the-Fly Concept Mastery Computation

**Files:**
- Modify: `src/storage/repositories/course_files.py` (append)
- Modify: `tests/unit/test_course_files_repo.py` (append)

- [ ] **Step 1: Write failing tests for mastery computation**

Append to `tests/unit/test_course_files_repo.py`:

```python
from src.storage.repositories.course_files import compute_concept_mastery, set_manual_boost
from src.storage.schema import StudentConceptProgressRow, FlashcardAttemptRow


@pytest_asyncio.fixture
async def db_with_mastery_data(db_with_files):
    """Extend db_with_files with quiz and flashcard data for mastery testing."""
    db = db_with_files
    db.add(
        StudentConceptProgressRow(
            id="scp-1",
            student_id="00000000-0000-0000-0000-000000000001",
            course_id="ml_course",
            core_concept="Basics",
            mastery_score=0.0,
            quizzes_taken=10,
            quizzes_passed=7,
        )
    )
    db.add(
        FlashcardAttemptRow(
            id="fc-1",
            student_id="00000000-0000-0000-0000-000000000001",
            course_id="ml_course",
            core_concepts=["Basics"],
            card_ratings={"c1": "easy", "c2": "good", "c3": "hard"},
        )
    )
    await db.commit()
    return db


class TestConceptMastery:
    @pytest.mark.asyncio
    async def test_zero_mastery_when_nothing_done(self, db_with_files) -> None:
        """No progress, no quizzes, no flashcards → all signals 0."""
        concepts = await compute_concept_mastery(
            db_with_files, "00000000-0000-0000-0000-000000000001", "ml_course"
        )
        basics = [c for c in concepts if c.concept == "Basics"]
        assert len(basics) == 1
        assert basics[0].mastery == 0.0

    @pytest.mark.asyncio
    async def test_lecture_only_caps_at_20(self, db_with_files) -> None:
        """Completing the one lecture covering 'Basics' → lecture_pct=100, weighted=20."""
        await toggle_file_progress(
            db_with_files, "00000000-0000-0000-0000-000000000001", "file-1", completed=True
        )
        concepts = await compute_concept_mastery(
            db_with_files, "00000000-0000-0000-0000-000000000001", "ml_course"
        )
        basics = [c for c in concepts if c.concept == "Basics"][0]
        assert basics.lecture_pct == 100.0
        assert basics.mastery == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_full_signals(self, db_with_mastery_data) -> None:
        """All signals active: lectures + exercises + quizzes + flashcards."""
        db = db_with_mastery_data
        await toggle_file_progress(
            db, "00000000-0000-0000-0000-000000000001", "file-1", completed=True
        )
        await toggle_file_progress(
            db, "00000000-0000-0000-0000-000000000001", "file-2", completed=True
        )
        concepts = await compute_concept_mastery(
            db, "00000000-0000-0000-0000-000000000001", "ml_course"
        )
        basics = [c for c in concepts if c.concept == "Basics"][0]
        assert basics.lecture_pct == 100.0
        assert basics.exercise_pct == 100.0
        assert basics.quiz_pct == pytest.approx(70.0)
        # flashcard: easy=1.0, good=0.66, hard=0.33 → avg=0.6633 → 66.33
        assert basics.flashcard_pct == pytest.approx(66.33, abs=1.0)
        # weighted = 100*0.20 + 100*0.30 + 70*0.35 + 66.33*0.15 = 20+30+24.5+9.95 = 84.45
        assert basics.mastery == pytest.approx(84.45, abs=1.0)

    @pytest.mark.asyncio
    async def test_manual_boost_adds_and_caps(self, db_with_files) -> None:
        """Manual boost adds flat %, capped at 100."""
        db = db_with_files
        await set_manual_boost(
            db, "00000000-0000-0000-0000-000000000001", "ml_course", "Basics", 90.0
        )
        await toggle_file_progress(
            db, "00000000-0000-0000-0000-000000000001", "file-1", completed=True
        )
        concepts = await compute_concept_mastery(
            db, "00000000-0000-0000-0000-000000000001", "ml_course"
        )
        basics = [c for c in concepts if c.concept == "Basics"][0]
        # weighted=20.0 (lecture only) + 90.0 boost = 110 → capped to 100
        assert basics.manual_boost == 90.0
        assert basics.mastery == 100.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_course_files_repo.py::TestConceptMastery -v`
Expected: FAIL — `ImportError: cannot import name 'compute_concept_mastery'`

- [ ] **Step 3: Implement `compute_concept_mastery` and `set_manual_boost`**

Append to `src/storage/repositories/course_files.py`:

```python
FLASHCARD_RATING_MAP: dict[str, float] = {
    "again": 0.0,
    "hard": 0.33,
    "good": 0.66,
    "easy": 1.0,
}

WEIGHT_LECTURE = 0.20
WEIGHT_EXERCISE = 0.30
WEIGHT_QUIZ = 0.35
WEIGHT_FLASHCARD = 0.15


@dataclass
class ConceptMastery:
    """Per-concept mastery breakdown."""

    concept: str
    mastery: float
    lecture_pct: float
    exercise_pct: float
    quiz_pct: float
    flashcard_pct: float
    manual_boost: float


async def compute_concept_mastery(
    db: AsyncSession,
    student_id: str,
    dataset_name: str,
) -> list[ConceptMastery]:
    """Compute per-concept mastery on-the-fly.

    Args:
        db: Async database session.
        student_id: Student UUID or "demo".
        dataset_name: S3 folder / Cognee dataset name.

    Returns:
        List of ConceptMastery for every concept found in this dataset.
    """
    sid = resolve_student_id(student_id)

    # 1. Get all files for this dataset
    file_result = await db.execute(
        select(CourseFileRow).where(CourseFileRow.dataset_name == dataset_name)
    )
    files = file_result.scalars().all()

    # 2. Get student's file progress
    file_ids = [f.id for f in files]
    progress_result = await db.execute(
        select(StudentFileProgressRow).where(
            StudentFileProgressRow.student_id == sid,
            StudentFileProgressRow.course_file_id.in_(file_ids) if file_ids else False,
        )
    )
    completed_file_ids: set[str] = {
        p.course_file_id for p in progress_result.scalars().all() if p.completed
    }

    # 3. Discover all concepts (union of file concepts + progress rows)
    concept_set: set[str] = set()
    for f in files:
        for c in f.core_concepts:
            concept_set.add(c)

    scp_result = await db.execute(
        select(StudentConceptProgressRow).where(
            StudentConceptProgressRow.student_id == sid,
            StudentConceptProgressRow.course_id == dataset_name,
        )
    )
    scp_rows = {r.core_concept: r for r in scp_result.scalars().all()}
    concept_set.update(scp_rows.keys())

    # 4. Get flashcard attempts
    fc_result = await db.execute(
        select(FlashcardAttemptRow).where(
            FlashcardAttemptRow.student_id == sid,
            FlashcardAttemptRow.course_id == dataset_name,
        )
    )
    fc_rows = fc_result.scalars().all()

    # 5. Build per-concept file counts
    file_counts: dict[str, dict[str, dict[str, int]]] = {}
    for concept in concept_set:
        file_counts[concept] = {
            "lecture": {"total": 0, "done": 0},
            "exercise": {"total": 0, "done": 0},
        }

    for f in files:
        for concept in f.core_concepts:
            if concept in file_counts:
                cat = f.category
                file_counts[concept][cat]["total"] += 1
                if f.id in completed_file_ids:
                    file_counts[concept][cat]["done"] += 1

    # 6. Build per-concept flashcard scores
    fc_scores: dict[str, list[float]] = {c: [] for c in concept_set}
    for fc in fc_rows:
        for concept in fc.core_concepts:
            if concept in fc_scores:
                for rating in fc.card_ratings.values():
                    score = FLASHCARD_RATING_MAP.get(rating.lower(), 0.0)
                    fc_scores[concept].append(score)

    # 7. Compute mastery per concept
    results: list[ConceptMastery] = []
    for concept in sorted(concept_set):
        lec = file_counts[concept]["lecture"]
        lecture_pct = (lec["done"] / lec["total"] * 100) if lec["total"] > 0 else 0.0

        exc = file_counts[concept]["exercise"]
        exercise_pct = (exc["done"] / exc["total"] * 100) if exc["total"] > 0 else 0.0

        scp = scp_rows.get(concept)
        quiz_pct = (
            (scp.quizzes_passed / scp.quizzes_taken * 100)
            if scp and scp.quizzes_taken > 0
            else 0.0
        )

        fc_vals = fc_scores[concept]
        flashcard_pct = (sum(fc_vals) / len(fc_vals) * 100) if fc_vals else 0.0

        manual_boost = scp.manual_mastery if scp and scp.manual_mastery else 0.0

        weighted = (
            lecture_pct * WEIGHT_LECTURE
            + exercise_pct * WEIGHT_EXERCISE
            + quiz_pct * WEIGHT_QUIZ
            + flashcard_pct * WEIGHT_FLASHCARD
        )
        mastery = min(100.0, weighted + manual_boost)

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
    """Set the manual mastery boost for a student-concept pair.

    Args:
        db: Async database session.
        student_id: Student UUID or "demo".
        dataset_name: Course dataset name (used as course_id).
        concept: Core concept name.
        boost: Flat percentage to add (0–100).
    """
    sid = resolve_student_id(student_id)

    result = await db.execute(
        select(StudentConceptProgressRow).where(
            StudentConceptProgressRow.student_id == sid,
            StudentConceptProgressRow.course_id == dataset_name,
            StudentConceptProgressRow.core_concept == concept,
        )
    )
    row = result.scalar_one_or_none()

    if row:
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
```

- [ ] **Step 4: Run mastery tests to verify they pass**

Run: `uv run pytest tests/unit/test_course_files_repo.py::TestConceptMastery -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/storage/repositories/course_files.py tests/unit/test_course_files_repo.py
git commit -m "feat: add on-the-fly concept mastery computation with manual boost"
```

---

## Task 6: API Endpoints

**Files:**
- Modify: `src/api/pipeline.py` (append 4 new endpoints)

- [ ] **Step 1: Add Pydantic models and file listing endpoint**

Append to `src/api/pipeline.py`:

```python
from src.storage.repositories import course_files as files_repo


class CourseFileResponse(BaseModel):
    """A single course file with student progress."""

    id: str
    dataset_name: str
    s3_key: str
    filename: str
    display_name: str
    category: str
    sort_order: int
    core_concepts: list[str]
    completed: bool
    completed_at: str | None


class CategorySummary(BaseModel):
    """Completion summary for a file category."""

    total: int
    completed: int


class FileSummary(BaseModel):
    """Aggregate completion summary."""

    total: int
    completed: int
    lectures: CategorySummary
    exercises: CategorySummary


class CourseFilesResponse(BaseModel):
    """Response listing files with progress and summary."""

    files: list[CourseFileResponse]
    summary: FileSummary


@router.get("/synced/{dataset_name}/files", response_model=CourseFilesResponse)
async def list_course_files_with_progress(
    dataset_name: str,
    student_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> CourseFilesResponse:
    """List all files for a course with per-student completion status."""
    files = await files_repo.get_files_with_progress(session, student_id, dataset_name)

    lectures = [f for f in files if f["category"] == "lecture"]
    exercises = [f for f in files if f["category"] == "exercise"]

    summary = FileSummary(
        total=len(files),
        completed=sum(1 for f in files if f["completed"]),
        lectures=CategorySummary(
            total=len(lectures),
            completed=sum(1 for f in lectures if f["completed"]),
        ),
        exercises=CategorySummary(
            total=len(exercises),
            completed=sum(1 for f in exercises if f["completed"]),
        ),
    )
    return CourseFilesResponse(
        files=[CourseFileResponse(**f) for f in files],
        summary=summary,
    )
```

- [ ] **Step 2: Add progress toggle endpoint**

Append to `src/api/pipeline.py`:

```python
class ProgressToggleRequest(BaseModel):
    """Body for toggling file completion."""

    student_id: str = "demo"
    completed: bool


class ProgressToggleResponse(BaseModel):
    """Response after toggling progress."""

    student_id: str
    course_file_id: str
    completed: bool
    completed_at: str | None


@router.put(
    "/synced/{dataset_name}/files/{file_id}/progress",
    response_model=ProgressToggleResponse,
)
async def toggle_progress(
    dataset_name: str,
    file_id: str,
    body: ProgressToggleRequest,
    session: AsyncSession = Depends(get_session),
) -> ProgressToggleResponse:
    """Toggle a student's completion status for a file."""
    result = await files_repo.toggle_file_progress(
        session, body.student_id, file_id, completed=body.completed
    )
    return ProgressToggleResponse(**result)
```

- [ ] **Step 3: Add concepts + mastery endpoint**

Append to `src/api/pipeline.py`:

```python
class MasteryBreakdown(BaseModel):
    """Breakdown of mastery signals for a concept."""

    lectures: float
    exercises: float
    quizzes: float
    flashcards: float
    manual_boost: float


class ConceptMasteryResponse(BaseModel):
    """A single concept's mastery."""

    name: str
    mastery: float
    breakdown: MasteryBreakdown


class ConceptsResponse(BaseModel):
    """Response listing all concepts with mastery."""

    concepts: list[ConceptMasteryResponse]


@router.get("/synced/{dataset_name}/concepts", response_model=ConceptsResponse)
async def get_concepts_with_mastery(
    dataset_name: str,
    student_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> ConceptsResponse:
    """Get all concepts for a course with on-the-fly mastery computation."""
    mastery_list = await files_repo.compute_concept_mastery(session, student_id, dataset_name)
    return ConceptsResponse(
        concepts=[
            ConceptMasteryResponse(
                name=m.concept,
                mastery=m.mastery,
                breakdown=MasteryBreakdown(
                    lectures=m.lecture_pct,
                    exercises=m.exercise_pct,
                    quizzes=m.quiz_pct,
                    flashcards=m.flashcard_pct,
                    manual_boost=m.manual_boost,
                ),
            )
            for m in mastery_list
        ]
    )
```

- [ ] **Step 4: Add manual boost endpoint**

Append to `src/api/pipeline.py`:

```python
class ManualBoostRequest(BaseModel):
    """Body for setting manual mastery boost."""

    student_id: str = "demo"
    boost: float


@router.put("/synced/{dataset_name}/concepts/{concept_name}/boost")
async def set_concept_boost(
    dataset_name: str,
    concept_name: str,
    body: ManualBoostRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Set the manual mastery boost for a concept."""
    if body.boost < 0 or body.boost > 100:
        raise HTTPException(status_code=400, detail="boost must be between 0 and 100")
    await files_repo.set_manual_boost(
        session, body.student_id, dataset_name, concept_name, body.boost
    )
    return {"dataset_name": dataset_name, "concept": concept_name, "boost": body.boost}
```

- [ ] **Step 5: Run lint and type check**

Run: `uv run ruff check src/api/pipeline.py && uv run mypy src/api/pipeline.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/api/pipeline.py
git commit -m "feat: add API endpoints for file listing, progress, mastery, and boost"
```

---

## Task 7: Startup Sync & Pipeline Integration

**Files:**
- Modify: `src/main.py:32-43` (lifespan function)
- Modify: `src/api/pipeline.py:88-105` (ingest + run endpoints)

- [ ] **Step 1: Add sync call to lifespan**

In `src/main.py`, update the `lifespan` function to call sync after the DB check:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — verify DB connectivity and sync course files on startup."""
    try:
        from src.storage.db import _engine

        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("startup_db_connected", database=get_settings().database_url.split("@")[-1])

        from src.storage.db import get_db_session
        from src.storage.repositories.course_files import sync_course_files_from_s3

        async with get_db_session() as session:
            result = await sync_course_files_from_s3(session)
            logger.info(
                "startup_course_files_synced",
                inserted=result.inserted,
                deleted=result.deleted,
                enriched=result.enriched,
            )
    except Exception as exc:
        logger.warning("startup_db_unavailable", reason=str(exc))
    yield
```

- [ ] **Step 2: Add sync call to ingest endpoint**

In `src/api/pipeline.py`, update the `ingest_courses` function (around line 88):

```python
@router.post("/ingest", response_model=IngestResponse)
async def ingest_courses(
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    """Extract zips, upload PDFs to Cognee, and trigger cognify."""
    from src.integrations.content_pipeline import ingest_all_courses

    logger.info("pipeline_ingest_all")
    results = await ingest_all_courses()

    sync_result = await files_repo.sync_course_files_from_s3(session)
    logger.info(
        "post_ingest_sync",
        inserted=sync_result.inserted,
        deleted=sync_result.deleted,
    )

    return IngestResponse(results=results)
```

- [ ] **Step 3: Add sync call to full pipeline endpoint**

In `src/api/pipeline.py`, update the `run_full` function (around line 98):

```python
@router.post("/run", response_model=FullPipelineResponse)
async def run_full(
    request: PipelineRequest,
    session: AsyncSession = Depends(get_session),
) -> FullPipelineResponse:
    """Run the complete pipeline: download → extract → upload → cognify."""
    from src.integrations.content_pipeline import run_full_pipeline

    logger.info("pipeline_run_full", semester=request.semester)
    result = await run_full_pipeline(semester=request.semester)

    sync_result = await files_repo.sync_course_files_from_s3(session)
    logger.info(
        "post_pipeline_sync",
        inserted=sync_result.inserted,
        deleted=sync_result.deleted,
    )

    return FullPipelineResponse(**result)
```

- [ ] **Step 4: Run lint and type check**

Run: `uv run ruff check src/main.py src/api/pipeline.py && uv run mypy src/main.py src/api/pipeline.py`
Expected: no errors

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/main.py src/api/pipeline.py
git commit -m "feat: trigger course file sync on startup and after pipeline ingest"
```

---

## Task 8: End-to-End Verification

- [ ] **Step 1: Run the full lint + type + test check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest -v`
Expected: all pass with zero errors.

- [ ] **Step 2: Fix any issues found**

If any lint/type/test failures, fix them and re-run.

- [ ] **Step 3: Rebuild and start Docker**

Run: `docker compose down && docker compose up --build -d`
Wait for healthy status, then run migration:
Run: `uv run alembic upgrade head`

- [ ] **Step 4: Verify API endpoints manually**

Test the new endpoints against the running server:

```bash
# List files for a dataset (replace with a real dataset_name from your S3)
curl -s http://localhost:8000/api/pipeline/synced/YOUR_DATASET/files | python -m json.tool

# Toggle progress
curl -s -X PUT http://localhost:8000/api/pipeline/synced/YOUR_DATASET/files/FILE_ID/progress \
  -H "Content-Type: application/json" \
  -d '{"student_id": "demo", "completed": true}'

# Get concepts with mastery
curl -s http://localhost:8000/api/pipeline/synced/YOUR_DATASET/concepts | python -m json.tool

# Set manual boost
curl -s -X PUT http://localhost:8000/api/pipeline/synced/YOUR_DATASET/concepts/CONCEPT_NAME/boost \
  -H "Content-Type: application/json" \
  -d '{"student_id": "demo", "boost": 25.0}'
```

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final fixes from e2e verification"
```
