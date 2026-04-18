"""Unit tests for the Moodle integration.

Course/upload/slides paths hit the Playwright scraper at runtime; tests
monkeypatch them with canned data. Deadlines hit the mock implementation
directly.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.integrations import moodle
from src.integrations.moodle import get_courses, get_deadlines, get_slides

_FAKE_COURSES: list[dict[str, Any]] = [
    {
        "moodle_id": "100001",
        "name": "Introduction to Deep Learning",
        "url": "/course/view.php?id=100001",
    },
    {
        "moodle_id": "100002",
        "name": "Machine Learning",
        "url": "/course/view.php?id=100002",
    },
]

_FAKE_UPLOADS: dict[str, list[dict[str, Any]]] = {
    "100001": [
        {
            "filename": "Lecture01_NN_Basics.pdf",
            "url": "/pluginfile.php/1/mod_resource/content/1/lec01.pdf",
            "moodle_course_id": "100001",
        },
        {
            "filename": "Lecture02_Backprop.pptx",
            "url": "/pluginfile.php/2/mod_resource/content/1/lec02.pptx",
            "moodle_course_id": "100001",
        },
        {
            "filename": "exercises.zip",
            "url": "/pluginfile.php/3/mod_resource/content/1/exercises.zip",
            "moodle_course_id": "100001",
        },
    ],
    "nonexistent": [],
}


@pytest.mark.asyncio
async def test_get_courses_returns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_courses(semester: str | None = None) -> list[dict[str, Any]]:
        return _FAKE_COURSES

    monkeypatch.setattr(moodle, "get_courses", fake_get_courses)
    courses = await moodle.get_courses(semester=None)
    assert len(courses) > 0
    for c in courses:
        assert "moodle_id" in c
        assert "name" in c
        assert "url" in c


@pytest.mark.asyncio
async def test_get_slides_returns_lectures(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_uploads(moodle_course_id: str) -> list[dict[str, Any]]:
        return _FAKE_UPLOADS.get(moodle_course_id, [])

    monkeypatch.setattr(moodle, "get_uploads", fake_get_uploads)
    slides = await get_slides(course_id="100001")
    assert len(slides) >= 2
    for s in slides:
        assert "filename" in s
        assert "url" in s
    assert all(
        s["filename"].lower().endswith((".pdf", ".pptx", ".ppt", ".key")) for s in slides
    )


@pytest.mark.asyncio
async def test_get_slides_unknown_course(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_uploads(moodle_course_id: str) -> list[dict[str, Any]]:
        return _FAKE_UPLOADS.get(moodle_course_id, [])

    monkeypatch.setattr(moodle, "get_uploads", fake_get_uploads)
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


# Quiet unused-import warnings — `get_courses` is exercised via `moodle.get_courses`
_ = get_courses
