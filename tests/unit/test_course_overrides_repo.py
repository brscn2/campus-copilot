"""Unit tests for the course-override repository.

Uses an in-memory SQLite database to exercise the real SQLAlchemy code path
without requiring Postgres.  JSONB is mapped to the SQLite ``JSON`` type by
SQLAlchemy automatically.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.storage.repositories import course_overrides as repo
from src.storage.schema import Base, StudentRow


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            StudentRow(
                id=repo.DEMO_STUDENT_ID,
                tum_email="demo@tum.de",
                display_name="Demo",
                program="",
                semester=0,
                priorities={},
                course_overrides={},
            )
        )
        await s.commit()
        yield s
    await engine.dispose()


def test_resolve_student_id_demo_alias() -> None:
    assert repo.resolve_student_id("demo") == repo.DEMO_STUDENT_ID
    assert repo.resolve_student_id(None) == repo.DEMO_STUDENT_ID
    assert repo.resolve_student_id("custom-uuid") == "custom-uuid"


@pytest.mark.asyncio
async def test_get_overrides_empty(session) -> None:
    assert await repo.get_overrides(session, "demo") == {}


@pytest.mark.asyncio
async def test_set_then_get_override(session) -> None:
    await repo.set_override(session, "demo", "ds_intro_dl", "WiSe 2025/26")
    overrides = await repo.get_overrides(session, "demo")
    assert overrides == {"ds_intro_dl": {"semester": "WiSe 2025/26"}}


@pytest.mark.asyncio
async def test_set_override_overwrites_existing(session) -> None:
    await repo.set_override(session, "demo", "ds_intro_dl", "SoSe 2025")
    await repo.set_override(session, "demo", "ds_intro_dl", "WiSe 2025/26")
    overrides = await repo.get_overrides(session, "demo")
    assert overrides["ds_intro_dl"]["semester"] == "WiSe 2025/26"


@pytest.mark.asyncio
async def test_delete_override(session) -> None:
    await repo.set_override(session, "demo", "a", "SoSe 2025")
    await repo.set_override(session, "demo", "b", "WiSe 2025/26")
    remaining = await repo.delete_override(session, "demo", "a")
    assert "a" not in remaining
    assert remaining["b"]["semester"] == "WiSe 2025/26"


@pytest.mark.asyncio
async def test_delete_missing_override_is_noop(session) -> None:
    remaining = await repo.delete_override(session, "demo", "nope")
    assert remaining == {}


@pytest.mark.asyncio
async def test_clear_overrides(session) -> None:
    await repo.set_override(session, "demo", "a", "SoSe 2025")
    await repo.set_override(session, "demo", "b", "WiSe 2025/26")
    await repo.clear_overrides(session, "demo")
    assert await repo.get_overrides(session, "demo") == {}


@pytest.mark.asyncio
async def test_set_override_creates_missing_student(session) -> None:
    """`set_override` must auto-create the student row on a fresh DB."""
    fresh_id = "11111111-1111-1111-1111-111111111111"
    await repo.set_override(session, fresh_id, "ds", "WiSe 2025/26")
    overrides = await repo.get_overrides(session, fresh_id)
    assert overrides == {"ds": {"semester": "WiSe 2025/26"}}
