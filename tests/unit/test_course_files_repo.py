"""Unit tests for the course-files repository.

Uses an in-memory SQLite database with ``aiosqlite`` to exercise the real
SQLAlchemy code paths without requiring Postgres.

The ``JSONB`` → ``JSON`` compilation hook lets SQLite handle Postgres JSONB
columns transparently.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from src.storage.repositories import course_files as repo
from src.storage.repositories.course_overrides import DEMO_STUDENT_ID
from src.storage.schema import (
    Base,
    CourseFileRow,
    FlashcardAttemptRow,
    StudentConceptProgressRow,
    StudentFileProgressRow,
    StudentRow,
)

# Make JSONB renderable on SQLite by falling back to plain JSON.
from sqlalchemy import select  # noqa: E402 — needed in tests below


@compiles(JSONB, "sqlite")  # type: ignore[misc]
def _compile_jsonb_sqlite(type_: JSONB, compiler: Any, **kw: Any) -> str:
    return compiler.process(JSON(), **kw)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Bare database with schema created — no seed data."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def db_with_files(db_session: AsyncSession):
    """Session seeded with a demo student and two course files."""
    db_session.add(
        StudentRow(
            id=DEMO_STUDENT_ID,
            tum_email="demo@tum.de",
            display_name="Demo",
            program="Informatics",
            semester=3,
            priorities={},
            course_overrides={},
        )
    )
    db_session.add(
        CourseFileRow(
            id="file-1",
            dataset_name="intro_ml",
            s3_key="slides/intro_ml/01_intro.pdf",
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
            dataset_name="intro_ml",
            s3_key="slides/intro_ml/02_exercise.pdf",
            filename="02_exercise.pdf",
            display_name="Exercise",
            category="exercise",
            sort_order=2,
            core_concepts=["Basics"],
        )
    )
    await db_session.commit()
    return db_session


@pytest_asyncio.fixture
async def db_with_mastery_data(db_with_files: AsyncSession):
    """Extends ``db_with_files`` with concept progress and flashcard data."""
    db_with_files.add(
        StudentConceptProgressRow(
            student_id=DEMO_STUDENT_ID,
            course_id="intro_ml",
            core_concept="Basics",
            quizzes_taken=10,
            quizzes_passed=7,
        )
    )
    db_with_files.add(
        FlashcardAttemptRow(
            student_id=DEMO_STUDENT_ID,
            course_id="intro_ml",
            core_concepts=["Basics"],
            card_ratings={"c1": "easy", "c2": "good", "c3": "hard"},
        )
    )
    await db_with_files.commit()
    return db_with_files


# ---------------------------------------------------------------------------
# S3 mock helpers
# ---------------------------------------------------------------------------


def _fake_s3_objects(keys: list[str]) -> list[dict[str, Any]]:
    """Build a fake S3 list_objects response from a list of keys."""
    return [
        {"key": k, "size": 1024, "last_modified": "2026-01-01T00:00:00"}
        for k in keys
    ]


async def _mock_s3(monkeypatch: pytest.MonkeyPatch, keys: list[str]) -> None:
    """Monkeypatch ``repo.list_objects`` to return *keys* as S3 objects."""

    async def _fake_list_objects(prefix: str) -> list[dict[str, Any]]:
        return _fake_s3_objects(keys)

    monkeypatch.setattr(repo, "list_objects", _fake_list_objects)


# ---------------------------------------------------------------------------
# Task 3 — Filename parsing
# ---------------------------------------------------------------------------


class TestFilenameParser:
    """Tests for the pure parsing functions."""

    # -- parse_category ------------------------------------------------------

    def test_lecture_default(self) -> None:
        assert repo.parse_category("01_intro_to_ml.pdf") == "lecture"

    def test_exercise_english(self) -> None:
        assert repo.parse_category("03_exercise_sheet.pdf") == "exercise"

    def test_german_uebung(self) -> None:
        assert repo.parse_category("04_uebung_3.pdf") == "exercise"

    def test_german_uebung_umlaut(self) -> None:
        assert repo.parse_category("04_Übung_3.pdf") == "exercise"

    def test_homework(self) -> None:
        assert repo.parse_category("homework_week5.pdf") == "exercise"

    def test_assignment(self) -> None:
        assert repo.parse_category("assignment_2.pdf") == "exercise"

    def test_aufgabe(self) -> None:
        assert repo.parse_category("aufgabe_7.pdf") == "exercise"

    def test_blatt(self) -> None:
        assert repo.parse_category("blatt_03.pdf") == "exercise"

    # -- parse_sort_order ----------------------------------------------------

    def test_leading_number(self) -> None:
        assert repo.parse_sort_order("03_lecture.pdf") == 3

    def test_no_number(self) -> None:
        assert repo.parse_sort_order("overview.pdf") == 0

    def test_large_number(self) -> None:
        assert repo.parse_sort_order("999_bonus.pdf") == 999

    # -- parse_display_name --------------------------------------------------

    def test_strips_number_and_extension(self) -> None:
        assert repo.parse_display_name("01_intro_to_ml.pdf") == "Intro To Ml"

    def test_handles_dashes(self) -> None:
        assert repo.parse_display_name("02-graph-algorithms.pdf") == "Graph Algorithms"

    def test_no_number(self) -> None:
        assert repo.parse_display_name("overview.pdf") == "Overview"

    def test_exercise_name(self) -> None:
        assert repo.parse_display_name("05_exercise_sheet.pdf") == "Exercise Sheet"


# ---------------------------------------------------------------------------
# Task 3 — Sync logic
# ---------------------------------------------------------------------------


class TestSyncCourseFiles:
    """Tests for ``sync_course_files_from_s3``."""

    async def test_inserts_new_files(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _mock_s3(
            monkeypatch,
            [
                "slides/ml101/01_intro.pdf",
                "slides/ml101/02_trees.pdf",
            ],
        )
        result = await repo.sync_course_files_from_s3(db_session)
        assert result.inserted == 2
        assert result.deleted == 0

        rows = (await db_session.execute(select(CourseFileRow))).scalars().all()
        assert len(rows) == 2

    async def test_idempotent_second_run(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _mock_s3(monkeypatch, ["slides/ml101/01_intro.pdf"])
        await repo.sync_course_files_from_s3(db_session)
        result = await repo.sync_course_files_from_s3(db_session)
        assert result.inserted == 0
        assert result.deleted == 0

    async def test_deletes_stale_files(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _mock_s3(
            monkeypatch,
            ["slides/ml101/01_intro.pdf", "slides/ml101/02_trees.pdf"],
        )
        await repo.sync_course_files_from_s3(db_session)

        # Second sync with only one file remaining
        await _mock_s3(monkeypatch, ["slides/ml101/01_intro.pdf"])
        result = await repo.sync_course_files_from_s3(db_session)
        assert result.deleted == 1

        rows = (await db_session.execute(select(CourseFileRow))).scalars().all()
        assert len(rows) == 1
        assert rows[0].filename == "01_intro.pdf"

    async def test_parses_category_and_sort_order(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _mock_s3(
            monkeypatch,
            ["slides/ml101/03_exercise_sheet.pdf"],
        )
        await repo.sync_course_files_from_s3(db_session)

        row = (await db_session.execute(select(CourseFileRow))).scalar_one()
        assert row.category == "exercise"
        assert row.sort_order == 3

    async def test_skips_non_file_keys(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _mock_s3(
            monkeypatch,
            [
                "slides/ml101/",  # directory marker
                "slides/",  # too few parts
                "slides/ml101/01_intro.pdf",  # valid
            ],
        )
        result = await repo.sync_course_files_from_s3(db_session)
        assert result.inserted == 1


# ---------------------------------------------------------------------------
# Task 4 — File progress
# ---------------------------------------------------------------------------


class TestFileProgress:
    """Tests for ``get_files_with_progress`` and ``toggle_file_progress``."""

    async def test_default_not_completed(self, db_with_files: AsyncSession) -> None:
        files = await repo.get_files_with_progress(db_with_files, "demo", "intro_ml")
        assert len(files) == 2
        assert files[0]["completed"] is False
        assert files[0]["completed_at"] is None

    async def test_toggle_on(self, db_with_files: AsyncSession) -> None:
        result = await repo.toggle_file_progress(
            db_with_files, "demo", "file-1", completed=True
        )
        assert result["completed"] is True
        assert result["completed_at"] is not None

        files = await repo.get_files_with_progress(db_with_files, "demo", "intro_ml")
        lecture = next(f for f in files if f["id"] == "file-1")
        assert lecture["completed"] is True

    async def test_toggle_off(self, db_with_files: AsyncSession) -> None:
        await repo.toggle_file_progress(db_with_files, "demo", "file-1", completed=True)
        result = await repo.toggle_file_progress(
            db_with_files, "demo", "file-1", completed=False
        )
        assert result["completed"] is False
        assert result["completed_at"] is None

    async def test_ordering_by_category_then_sort_order(
        self, db_with_files: AsyncSession
    ) -> None:
        files = await repo.get_files_with_progress(db_with_files, "demo", "intro_ml")
        # exercise < lecture alphabetically
        assert files[0]["category"] == "exercise"
        assert files[1]["category"] == "lecture"


# ---------------------------------------------------------------------------
# Task 5 — Concept mastery
# ---------------------------------------------------------------------------


class TestConceptMastery:
    """Tests for ``compute_concept_mastery`` and ``set_manual_boost``."""

    async def test_zero_mastery_when_nothing_done(
        self, db_with_files: AsyncSession
    ) -> None:
        mastery = await repo.compute_concept_mastery(db_with_files, "demo", "intro_ml")
        assert len(mastery) == 1
        assert mastery[0].concept == "Basics"
        assert mastery[0].mastery == 0.0

    async def test_lecture_only_caps_at_20(self, db_with_files: AsyncSession) -> None:
        # Complete the lecture file only
        await repo.toggle_file_progress(db_with_files, "demo", "file-1", completed=True)
        mastery = await repo.compute_concept_mastery(db_with_files, "demo", "intro_ml")
        basics = mastery[0]
        assert basics.lecture_pct == 100.0
        assert basics.exercise_pct == 0.0
        # 100 * 0.20 = 20.0
        assert basics.mastery == 20.0

    async def test_full_signals(self, db_with_mastery_data: AsyncSession) -> None:
        db = db_with_mastery_data
        # Complete both files
        await repo.toggle_file_progress(db, "demo", "file-1", completed=True)
        await repo.toggle_file_progress(db, "demo", "file-2", completed=True)

        mastery = await repo.compute_concept_mastery(db, "demo", "intro_ml")
        basics = mastery[0]

        # lecture: 1/1 = 100%
        assert basics.lecture_pct == 100.0
        # exercise: 1/1 = 100%
        assert basics.exercise_pct == 100.0
        # quiz: 7/10 = 70%
        assert basics.quiz_pct == 70.0
        # flashcard: (1.0 + 0.66 + 0.33) / 3 * 100 = 66.33...
        assert basics.flashcard_pct == 66.33

        # weighted: 100*0.20 + 100*0.30 + 70*0.35 + 66.33*0.15
        # = 20 + 30 + 24.5 + 9.9495 = 84.4495 -> round to 84.45
        assert basics.mastery == 84.45

    async def test_manual_boost_adds_and_caps_at_100(
        self, db_with_mastery_data: AsyncSession
    ) -> None:
        db = db_with_mastery_data
        await repo.toggle_file_progress(db, "demo", "file-1", completed=True)
        await repo.toggle_file_progress(db, "demo", "file-2", completed=True)
        await repo.set_manual_boost(db, "demo", "intro_ml", "Basics", 50.0)

        mastery = await repo.compute_concept_mastery(db, "demo", "intro_ml")
        basics = mastery[0]
        assert basics.manual_boost == 50.0
        # 84.45 + 50 would be 134.45, capped at 100
        assert basics.mastery == 100.0
