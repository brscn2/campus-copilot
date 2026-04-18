"""Unit tests for the mock job board integration."""

from __future__ import annotations

import pytest

from src.integrations.jobs import search_jobs


@pytest.mark.asyncio
async def test_search_jobs_returns_results() -> None:
    results = await search_jobs()
    assert len(results) > 0
    for job in results:
        assert "id" in job
        assert "title" in job
        assert "company" in job


@pytest.mark.asyncio
async def test_search_jobs_filters_by_kind() -> None:
    results = await search_jobs(kind="internship")
    assert all(j["kind"] == "internship" for j in results)


@pytest.mark.asyncio
async def test_search_jobs_filters_by_company() -> None:
    results = await search_jobs(company="BMW")
    assert len(results) >= 1
    assert all("BMW" in j["company"] for j in results)


@pytest.mark.asyncio
async def test_search_jobs_filters_by_keywords() -> None:
    results = await search_jobs(keywords=["machine learning"])
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_jobs_no_results() -> None:
    results = await search_jobs(keywords=["underwater basket weaving"])
    assert results == []
