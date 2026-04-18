"""Unit tests for the job board integration (mock + SerpAPI paths)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.exceptions import JobSearchError
from src.integrations.jobs import (
    _build_query,
    _infer_kind,
    _map_serpapi_result,
    _search_mock,
    search_jobs,
)

# ---------------------------------------------------------------------------
# _build_query
# ---------------------------------------------------------------------------


class TestBuildQuery:
    def test_kind_only(self) -> None:
        q = _build_query(kind="working_student")
        assert "Werkstudent" in q
        assert "working student" in q

    def test_keywords_and_company(self) -> None:
        q = _build_query(keywords=["python", "ML"], company="BMW")
        assert "python" in q
        assert "ML" in q
        assert "BMW" in q

    def test_empty_params_default(self) -> None:
        q = _build_query()
        assert "student jobs" in q


# ---------------------------------------------------------------------------
# _infer_kind
# ---------------------------------------------------------------------------


class TestInferKind:
    def test_werkstudent(self) -> None:
        assert _infer_kind("Werkstudent Data Science", None) == "working_student"

    def test_internship(self) -> None:
        assert _infer_kind("Praktikum Softwareentwicklung", None) == "internship"

    def test_default_new_grad(self) -> None:
        assert _infer_kind("Junior Software Engineer", None) == "new_grad"


# ---------------------------------------------------------------------------
# _map_serpapi_result
# ---------------------------------------------------------------------------


SAMPLE_SERPAPI_ITEM: dict[str, Any] = {
    "job_id": "abc123",
    "title": "Working Student — Backend Engineering",
    "company_name": "TechCo",
    "location": "Munich, Germany",
    "description": "Build backend services with Python.",
    "extensions": ["Working student", "Python"],
    "detected_extensions": {"salary": "18-22 €/hr", "posted_at": "3 days ago"},
    "apply_options": [{"title": "Apply on TechCo", "link": "https://techco.com/apply"}],
}


class TestMapSerpApiResult:
    def test_maps_all_fields(self) -> None:
        result = _map_serpapi_result(SAMPLE_SERPAPI_ITEM, fallback_kind=None)
        assert result["id"] == "abc123"
        assert result["company"] == "TechCo"
        assert result["title"] == "Working Student — Backend Engineering"
        assert result["kind"] == "working_student"
        assert result["location"] == "Munich, Germany"
        assert result["salary"] == "18-22 €/hr"
        assert result["description"] == "Build backend services with Python."
        assert result["source_url"] == "https://techco.com/apply"
        assert result["posted_at"] == "3 days ago"

    def test_missing_apply_options(self) -> None:
        item = {**SAMPLE_SERPAPI_ITEM, "apply_options": []}
        result = _map_serpapi_result(item, fallback_kind=None)
        assert result["source_url"] == ""

    def test_fallback_kind_overrides_default(self) -> None:
        item = {**SAMPLE_SERPAPI_ITEM, "title": "Software Engineer", "extensions": []}
        result = _map_serpapi_result(item, fallback_kind="internship")
        assert result["kind"] == "internship"

    def test_inferred_kind_wins_over_fallback(self) -> None:
        result = _map_serpapi_result(SAMPLE_SERPAPI_ITEM, fallback_kind="internship")
        assert result["kind"] == "working_student"


# ---------------------------------------------------------------------------
# _search_mock (existing tests, extracted)
# ---------------------------------------------------------------------------


class TestSearchMock:
    @pytest.mark.asyncio
    async def test_returns_results(self) -> None:
        results = await _search_mock()
        assert len(results) > 0
        for job in results:
            assert "id" in job
            assert "title" in job
            assert "company" in job

    @pytest.mark.asyncio
    async def test_filters_by_kind(self) -> None:
        results = await _search_mock(kind="internship")
        assert all(j["kind"] == "internship" for j in results)

    @pytest.mark.asyncio
    async def test_filters_by_company(self) -> None:
        results = await _search_mock(company="BMW")
        assert len(results) >= 1
        assert all("BMW" in j["company"] for j in results)

    @pytest.mark.asyncio
    async def test_filters_by_keywords(self) -> None:
        results = await _search_mock(keywords=["machine learning"])
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_no_results(self) -> None:
        results = await _search_mock(keywords=["underwater basket weaving"])
        assert results == []


# ---------------------------------------------------------------------------
# search_jobs (live path routing)
# ---------------------------------------------------------------------------


def _make_settings(*, mode: str = "mock", key: str = "") -> MagicMock:
    """Create a mock Settings object."""
    s = MagicMock()
    s.jobs_mode = mode
    s.serpapi_api_key = key
    return s


class TestSearchJobsRouting:
    @pytest.mark.asyncio
    async def test_mock_mode_uses_mock(self) -> None:
        with patch("src.integrations.jobs.get_settings", return_value=_make_settings()):
            results = await search_jobs()
            assert len(results) > 0

    @pytest.mark.asyncio
    async def test_live_mode_no_key_falls_back_to_mock(self) -> None:
        with patch(
            "src.integrations.jobs.get_settings",
            return_value=_make_settings(mode="live", key=""),
        ):
            results = await search_jobs()
            assert len(results) > 0

    @pytest.mark.asyncio
    async def test_live_mode_calls_serpapi(self) -> None:
        serpapi_result = [{"id": "live-1", "company": "LiveCo", "title": "Test"}]
        with (
            patch(
                "src.integrations.jobs.get_settings",
                return_value=_make_settings(mode="live", key="test-key"),
            ),
            patch(
                "src.integrations.jobs._search_serpapi",
                new_callable=AsyncMock,
                return_value=serpapi_result,
            ),
        ):
            results = await search_jobs(kind="working_student")
            assert results == serpapi_result

    @pytest.mark.asyncio
    async def test_live_mode_falls_back_on_error(self) -> None:
        with (
            patch(
                "src.integrations.jobs.get_settings",
                return_value=_make_settings(mode="live", key="test-key"),
            ),
            patch(
                "src.integrations.jobs._search_serpapi",
                new_callable=AsyncMock,
                side_effect=JobSearchError("boom"),
            ),
        ):
            results = await search_jobs()
            assert len(results) > 0
            assert results[0]["company"] == "BMW Group"
