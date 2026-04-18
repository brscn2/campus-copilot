"""Unit tests for the mock Moodle integration."""

from __future__ import annotations

import pytest

from src.integrations.moodle import get_courses, get_deadlines, get_slides


@pytest.mark.asyncio
async def test_get_courses_returns_results() -> None:
    courses = await get_courses(student_id="demo")
    assert len(courses) > 0
    for c in courses:
        assert "course_id" in c
        assert "code" in c
        assert "title" in c


@pytest.mark.asyncio
async def test_get_slides_returns_lectures() -> None:
    slides = await get_slides(course_id="moodle-IN2346")
    assert len(slides) >= 2
    for s in slides:
        assert "lecture_id" in s
        assert "title" in s
        assert "filename" in s


@pytest.mark.asyncio
async def test_get_slides_unknown_course() -> None:
    slides = await get_slides(course_id="nonexistent")
    assert slides == []


@pytest.mark.asyncio
async def test_get_deadlines_all_courses() -> None:
    deadlines = await get_deadlines(student_id="demo")
    assert len(deadlines) > 0
    due_dates = [d["due_at"] for d in deadlines]
    assert due_dates == sorted(due_dates)


@pytest.mark.asyncio
async def test_get_deadlines_single_course() -> None:
    deadlines = await get_deadlines(student_id="demo", course_id="moodle-IN2346")
    assert len(deadlines) >= 2
    assert all("idl" in d["deadline_id"] for d in deadlines)


@pytest.mark.asyncio
async def test_get_deadlines_unknown_course() -> None:
    deadlines = await get_deadlines(student_id="demo", course_id="nonexistent")
    assert deadlines == []
