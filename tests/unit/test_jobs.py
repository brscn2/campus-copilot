"""Unit tests for the job board integration (mock + TheirStack paths)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.exceptions import JobSearchError
from src.integrations import jobs as jobs_module
from src.integrations.jobs import (
    EUROPE_COUNTRY_CODES,
    _build_theirstack_payload,
    _map_theirstack_result,
    _search_mock,
    search_jobs,
)


@pytest.fixture(autouse=True)
def _clear_search_cache() -> None:
    """Each test starts with an empty in-process job-search cache."""
    jobs_module._search_cache.clear()


# ---------------------------------------------------------------------------
# _build_theirstack_payload
# ---------------------------------------------------------------------------


class TestBuildTheirStackPayload:
    def test_always_includes_country_and_age_window(self) -> None:
        payload = _build_theirstack_payload(kind=None, keywords=None, company=None, location=None)
        assert payload["job_country_code_or"] == EUROPE_COUNTRY_CODES
        assert payload["posted_at_max_age_days"] == 30
        assert payload["include_total_results"] is False
        assert payload["page"] == 0
        assert payload["limit"] == 10

    def test_limit_is_configurable(self) -> None:
        payload = _build_theirstack_payload(
            kind=None, keywords=None, company=None, location=None, limit=12
        )
        assert payload["limit"] == 12

    def test_internship_maps_to_employment_status(self) -> None:
        payload = _build_theirstack_payload(
            kind="internship", keywords=None, company=None, location=None
        )
        assert payload["employment_statuses_or"] == ["internship"]
        assert "job_seniority_or" not in payload

    def test_working_student_maps_to_part_time_plus_title_regex(self) -> None:
        payload = _build_theirstack_payload(
            kind="working_student", keywords=None, company=None, location=None
        )
        assert payload["employment_statuses_or"] == ["part_time"]
        assert payload["job_title_pattern_or"] == [
            "(?i)werkstudent",
            "(?i)working student",
        ]

    def test_new_grad_maps_to_full_time_plus_junior(self) -> None:
        payload = _build_theirstack_payload(
            kind="new_grad", keywords=None, company=None, location=None
        )
        assert payload["employment_statuses_or"] == ["full_time"]
        assert payload["job_seniority_or"] == ["junior"]

    def test_keywords_become_description_filter(self) -> None:
        payload = _build_theirstack_payload(
            kind=None, keywords=["python", "ML"], company=None, location=None
        )
        assert payload["job_description_contains_or"] == ["python", "ML"]

    def test_location_does_not_inject_description_terms(self) -> None:
        payload = _build_theirstack_payload(
            kind=None, keywords=None, company=None, location="Munich"
        )
        assert "job_description_contains_or" not in payload

    def test_uses_europe_country_codes(self) -> None:
        payload = _build_theirstack_payload(kind=None, keywords=None, company=None, location=None)
        assert "DE" in payload["job_country_code_or"]
        assert "GB" in payload["job_country_code_or"]
        assert len(payload["job_country_code_or"]) > 5

    def test_company_filter(self) -> None:
        payload = _build_theirstack_payload(kind=None, keywords=None, company="BMW", location=None)
        assert payload["company_name_case_insensitive_or"] == ["BMW"]


# ---------------------------------------------------------------------------
# _map_theirstack_result
# ---------------------------------------------------------------------------


SAMPLE_THEIRSTACK_ITEM: dict[str, Any] = {
    "id": 9876,
    "job_title": "Werkstudent Backend Engineering (m/w/d)",
    "url": "https://theirstack.com/job/9876",
    "final_url": "https://techco.com/jobs/werkstudent-backend",
    "company_object": {"name": "TechCo GmbH"},
    "location": "Munich",
    "long_location": "Munich, Bavaria, Germany",
    "description": "Build backend services with Python and PostgreSQL.",
    "salary_string": "18-22 €/hr",
    "min_annual_salary": None,
    "max_annual_salary": None,
    "salary_currency": "EUR",
    "employment_statuses": ["part_time"],
    "seniority": "junior",
    "date_posted": "2026-04-15",
    "technology_slugs": ["python", "postgresql"],
}


class TestMapTheirStackResult:
    def test_maps_all_core_fields(self) -> None:
        result = _map_theirstack_result(SAMPLE_THEIRSTACK_ITEM, requested_kind=None)
        assert result["id"] == "9876"
        assert result["company"] == "TechCo GmbH"
        assert result["title"] == "Werkstudent Backend Engineering (m/w/d)"
        assert result["location"] == "Munich, Bavaria, Germany"
        assert result["salary"] == "18-22 €/hr"
        assert result["description"].startswith("Build backend services")
        assert result["source_url"] == "https://techco.com/jobs/werkstudent-backend"
        assert result["posted_at"] == "2026-04-15"

    def test_werkstudent_title_resolves_to_working_student(self) -> None:
        result = _map_theirstack_result(SAMPLE_THEIRSTACK_ITEM, requested_kind=None)
        assert result["kind"] == "working_student"

    def test_internship_employment_status_wins(self) -> None:
        item = {
            **SAMPLE_THEIRSTACK_ITEM,
            "job_title": "Software Engineering Intern",
            "employment_statuses": ["internship"],
        }
        result = _map_theirstack_result(item, requested_kind=None)
        assert result["kind"] == "internship"

    def test_new_grad_from_seniority_plus_full_time(self) -> None:
        item = {
            **SAMPLE_THEIRSTACK_ITEM,
            "job_title": "Junior Software Engineer",
            "employment_statuses": ["full_time"],
            "seniority": "junior",
        }
        result = _map_theirstack_result(item, requested_kind=None)
        assert result["kind"] == "new_grad"

    def test_falls_back_to_requested_kind_when_ambiguous(self) -> None:
        item = {
            **SAMPLE_THEIRSTACK_ITEM,
            "job_title": "Software Engineer",
            "employment_statuses": [],
            "seniority": None,
        }
        result = _map_theirstack_result(item, requested_kind="internship")
        assert result["kind"] == "internship"

    def test_salary_falls_back_to_min_max(self) -> None:
        item = {
            **SAMPLE_THEIRSTACK_ITEM,
            "salary_string": None,
            "min_annual_salary": 55000,
            "max_annual_salary": 65000,
            "salary_currency": "EUR",
        }
        result = _map_theirstack_result(item, requested_kind=None)
        assert "55000" in result["salary"]
        assert "65000" in result["salary"]
        assert "EUR" in result["salary"]

    def test_missing_company_object_uses_company_string(self) -> None:
        item = {**SAMPLE_THEIRSTACK_ITEM, "company_object": None, "company": "Legacy Co"}
        result = _map_theirstack_result(item, requested_kind=None)
        assert result["company"] == "Legacy Co"

    def test_missing_optional_fields_do_not_crash(self) -> None:
        item: dict[str, Any] = {"id": 1, "job_title": "Engineer"}
        result = _map_theirstack_result(item, requested_kind=None)
        assert result["id"] == "1"
        assert result["title"] == "Engineer"
        assert result["company"] == ""
        assert result["location"] == ""
        assert result["salary"] == ""
        assert result["description"] == ""
        assert result["source_url"] == ""
        assert result["posted_at"] == ""

    def test_description_is_truncated(self) -> None:
        item = {**SAMPLE_THEIRSTACK_ITEM, "description": "x" * 9000}
        result = _map_theirstack_result(item, requested_kind=None)
        assert len(result["description"]) == 4000


# ---------------------------------------------------------------------------
# _search_mock
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


def _make_settings(
    *,
    mode: str = "mock",
    key: str = "",
    cache_dir: str = "/tmp/campus-copilot-test-cache-does-not-exist-xyz",
    cache_ttl: int = 0,
    results_per_call: int = 5,
) -> MagicMock:
    """Create a mock Settings object.

    Defaults point the disk cache at a non-existent path with TTL 0 so disk
    reads always miss and routing tests exercise the in-memory cache + live
    path without depending on whatever the developer's real .cache/jobs holds.
    """
    s = MagicMock()
    s.jobs_mode = mode
    s.theirstack_api_key = key
    s.theirstack_cache_dir = cache_dir
    s.theirstack_cache_ttl_seconds = cache_ttl
    s.theirstack_results_per_call = results_per_call
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
    async def test_live_mode_calls_theirstack(self) -> None:
        live_result = [
            {
                "id": "live-1",
                "company": "LiveCo",
                "title": "Werkstudent Test",
                "kind": "working_student",
                "location": "Munich",
                "salary": "",
                "description": "",
                "source_url": "",
                "posted_at": "2026-04-15",
            }
        ]
        with (
            patch(
                "src.integrations.jobs.get_settings",
                return_value=_make_settings(mode="live", key="test-key"),
            ),
            patch(
                "src.integrations.jobs._search_theirstack",
                new_callable=AsyncMock,
                return_value=live_result,
            ),
        ):
            results = await search_jobs(kind="working_student")
            assert results == live_result

    @pytest.mark.asyncio
    async def test_live_mode_falls_back_on_error(self) -> None:
        with (
            patch(
                "src.integrations.jobs.get_settings",
                return_value=_make_settings(mode="live", key="test-key"),
            ),
            patch(
                "src.integrations.jobs._search_theirstack",
                new_callable=AsyncMock,
                side_effect=JobSearchError("boom"),
            ),
        ):
            results = await search_jobs()
            assert len(results) > 0
            assert results[0]["company"] == "BMW Group"

    @pytest.mark.asyncio
    async def test_live_mode_empty_falls_back_to_mock(self) -> None:
        with (
            patch(
                "src.integrations.jobs.get_settings",
                return_value=_make_settings(mode="live", key="test-key"),
            ),
            patch(
                "src.integrations.jobs._search_theirstack",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            results = await search_jobs()
            assert len(results) > 0

    @pytest.mark.asyncio
    async def test_live_mode_caches_results(self) -> None:
        live_result = [
            {
                "id": "cache-1",
                "company": "CacheCo",
                "title": "Werkstudent",
                "kind": "working_student",
                "location": "Munich",
                "salary": "",
                "description": "",
                "source_url": "",
                "posted_at": "2026-04-15",
            }
        ]
        mock_search = AsyncMock(return_value=live_result)
        with (
            patch(
                "src.integrations.jobs.get_settings",
                return_value=_make_settings(mode="live", key="test-key"),
            ),
            patch("src.integrations.jobs._search_theirstack", mock_search),
        ):
            await search_jobs(kind="working_student")
            await search_jobs(kind="working_student")
            assert mock_search.await_count == 1
