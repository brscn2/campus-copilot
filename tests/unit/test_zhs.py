"""Unit tests for the mock ZHS integration."""

from __future__ import annotations

import pytest

from src.integrations.zhs import register_for_course, search_courses, set_snipe_alert


@pytest.mark.asyncio
async def test_search_courses_returns_results() -> None:
    results = await search_courses()
    assert len(results) > 0
    for course in results:
        assert "course_id" in course
        assert "name" in course
        assert "spots_available" in course


@pytest.mark.asyncio
async def test_search_courses_filters_by_category() -> None:
    results = await search_courses(category="climbing")
    assert all(c["category"] == "climbing" for c in results)


@pytest.mark.asyncio
async def test_search_courses_filters_by_day() -> None:
    results = await search_courses(day="Tuesday")
    assert all(c["day"] == "Tuesday" for c in results)


@pytest.mark.asyncio
async def test_search_courses_available_only() -> None:
    results = await search_courses(available_only=True)
    assert all(c["spots_available"] > 0 for c in results)


@pytest.mark.asyncio
async def test_register_for_course_confirmed() -> None:
    result = await register_for_course(course_id="zhs-yoga-01", student_id="demo")
    assert result["status"] == "confirmed"
    assert "registration_id" in result


@pytest.mark.asyncio
async def test_register_for_full_course_waitlisted() -> None:
    result = await register_for_course(course_id="zhs-bould-01", student_id="demo")
    assert result["status"] == "waitlisted"


@pytest.mark.asyncio
async def test_register_for_invalid_course() -> None:
    result = await register_for_course(course_id="nonexistent", student_id="demo")
    assert "error" in result


@pytest.mark.asyncio
async def test_set_snipe_alert_success() -> None:
    result = await set_snipe_alert(course_id="zhs-bould-01", student_id="demo")
    assert result["status"] == "snipe_active"
    assert "alert_id" in result


@pytest.mark.asyncio
async def test_set_snipe_alert_invalid_course() -> None:
    result = await set_snipe_alert(course_id="nonexistent", student_id="demo")
    assert "error" in result
