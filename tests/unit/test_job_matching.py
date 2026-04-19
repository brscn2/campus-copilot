"""Unit tests for the Cognee-enriched job matching pipeline."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lib.job_matching import (
    JOBS_DATASET,
    _format_kg_section,
    _match_via_haiku,
    _query_cognee_insights,
    match_jobs_via_cognee,
)


@pytest.fixture(autouse=True)
def _clear_match_cache() -> None:
    """Each test starts with an empty in-process match cache."""
    from src.lib import job_matching

    job_matching._match_cache.clear()


@pytest.fixture()
def sample_jobs() -> list[dict[str, Any]]:
    return [
        {
            "id": f"job-{i}",
            "title": f"Job {i}",
            "company": f"Co {i}",
            "kind": "working_student",
            "location": "Berlin",
            "salary": "",
            "description": f"Description for job {i}",
            "source_url": "",
            "posted_at": "",
        }
        for i in range(25)
    ]


def _make_settings(**overrides: Any) -> MagicMock:
    s = MagicMock()
    s.jobs_mode = overrides.get("mode", "mock")
    s.cognee_api_key = overrides.get("cognee_key", "test-key")
    s.cognee_api_url = overrides.get("cognee_url", "https://api.cognee.ai")
    s.match_cache_dir = overrides.get("cache_dir", "/tmp/no-such-cache-dir-xyz")
    s.match_cache_ttl_seconds = overrides.get("cache_ttl", 0)
    return s


# ---------------------------------------------------------------------------
# JOBS_DATASET
# ---------------------------------------------------------------------------


class TestJobsDataset:
    def test_dataset_is_europe(self) -> None:
        assert JOBS_DATASET == "jobs_europe"


# ---------------------------------------------------------------------------
# _format_kg_section
# ---------------------------------------------------------------------------


class TestFormatKgSection:
    def test_returns_section_with_content(self) -> None:
        result = _format_kg_section("PyTorch maps to ML Engineer roles")
        assert result.startswith("## Knowledge Graph Insights")
        assert "PyTorch maps to ML Engineer roles" in result

    def test_returns_empty_for_empty_string(self) -> None:
        assert _format_kg_section("") == ""

    def test_returns_empty_for_whitespace(self) -> None:
        assert _format_kg_section("   ") == ""

    def test_returns_empty_for_none_equivalent(self) -> None:
        assert _format_kg_section("") == ""


# ---------------------------------------------------------------------------
# _query_cognee_insights
# ---------------------------------------------------------------------------


def _mock_cognee(recall_return: Any = None, recall_side_effect: Any = None) -> MagicMock:
    """Build a mock cognee module for patching into sys.modules."""
    mock = MagicMock()
    mock.SearchType.GRAPH_COMPLETION = "GRAPH_COMPLETION"
    if recall_side_effect:
        mock.recall = AsyncMock(side_effect=recall_side_effect)
    else:
        mock.recall = AsyncMock(return_value=recall_return or [])
    return mock


class TestQueryCogneeInsights:
    @pytest.mark.asyncio
    async def test_returns_text_on_success(self) -> None:
        mock_results = [SimpleNamespace(search_result="PyTorch is used in ML Engineer roles")]
        cognee_mod = _mock_cognee(recall_return=mock_results)
        with (
            patch("src.lib.job_matching.ensure_cognee", new_callable=AsyncMock),
            patch.dict("sys.modules", {"cognee": cognee_mod}),
        ):
            result = await _query_cognee_insights("Student profile text")
            assert "PyTorch" in result

    @pytest.mark.asyncio
    async def test_returns_empty_on_recall_failure(self) -> None:
        cognee_mod = _mock_cognee(recall_side_effect=RuntimeError("connection refused"))
        with (
            patch("src.lib.job_matching.ensure_cognee", new_callable=AsyncMock),
            patch.dict("sys.modules", {"cognee": cognee_mod}),
        ):
            result = await _query_cognee_insights("Student profile text")
            assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_results(self) -> None:
        cognee_mod = _mock_cognee(recall_return=[])
        with (
            patch("src.lib.job_matching.ensure_cognee", new_callable=AsyncMock),
            patch.dict("sys.modules", {"cognee": cognee_mod}),
        ):
            result = await _query_cognee_insights("Student profile text")
            assert result == ""

    @pytest.mark.asyncio
    async def test_parses_dict_results(self) -> None:
        mock_results = [{"search_result": "Kubernetes relates to Cloud Engineer positions"}]
        cognee_mod = _mock_cognee(recall_return=mock_results)
        with (
            patch("src.lib.job_matching.ensure_cognee", new_callable=AsyncMock),
            patch.dict("sys.modules", {"cognee": cognee_mod}),
        ):
            result = await _query_cognee_insights("Student profile text")
            assert "Kubernetes" in result

    @pytest.mark.asyncio
    async def test_truncates_long_results(self) -> None:
        mock_results = [SimpleNamespace(search_result="x" * 3000)]
        cognee_mod = _mock_cognee(recall_return=mock_results)
        with (
            patch("src.lib.job_matching.ensure_cognee", new_callable=AsyncMock),
            patch.dict("sys.modules", {"cognee": cognee_mod}),
        ):
            result = await _query_cognee_insights("Student profile text")
            assert len(result) <= 2000


# ---------------------------------------------------------------------------
# _match_via_haiku
# ---------------------------------------------------------------------------


class TestMatchViaHaiku:
    @pytest.mark.asyncio
    async def test_includes_kg_section_when_insights_present(
        self, sample_jobs: list[dict[str, Any]]
    ) -> None:
        mock_invoke = AsyncMock(
            return_value={
                "content": [{"text": '[{"index": 0, "score": 85, "reason": "good match"}]'}]
            }
        )
        with (
            patch("src.lib.bedrock.invoke_model", mock_invoke),
            patch("src.lib.bedrock.get_haiku_model_id", return_value="haiku-test"),
        ):
            await _match_via_haiku(
                sample_jobs[:5], "Student profile", kg_insights="PyTorch skill overlap"
            )
            prompt_text = mock_invoke.call_args[1]["messages"][0]["content"]
            assert "Knowledge Graph Insights" in prompt_text
            assert "PyTorch skill overlap" in prompt_text

    @pytest.mark.asyncio
    async def test_omits_kg_section_when_no_insights(
        self, sample_jobs: list[dict[str, Any]]
    ) -> None:
        mock_invoke = AsyncMock(
            return_value={
                "content": [{"text": '[{"index": 0, "score": 85, "reason": "good match"}]'}]
            }
        )
        with (
            patch("src.lib.bedrock.invoke_model", mock_invoke),
            patch("src.lib.bedrock.get_haiku_model_id", return_value="haiku-test"),
        ):
            await _match_via_haiku(sample_jobs[:5], "Student profile", kg_insights="")
            prompt_text = mock_invoke.call_args[1]["messages"][0]["content"]
            assert "Knowledge Graph Insights" not in prompt_text

    @pytest.mark.asyncio
    async def test_processes_up_to_20_jobs(self, sample_jobs: list[dict[str, Any]]) -> None:
        scores_json = [{"index": i, "score": 90 - i, "reason": f"reason {i}"} for i in range(20)]
        mock_invoke = AsyncMock(
            return_value={"content": [{"text": str(scores_json).replace("'", '"')}]}
        )
        with (
            patch("src.lib.bedrock.invoke_model", mock_invoke),
            patch("src.lib.bedrock.get_haiku_model_id", return_value="haiku-test"),
        ):
            result = await _match_via_haiku(sample_jobs, "Student profile")
            assert len(result) == 20

    @pytest.mark.asyncio
    async def test_defaults_score_to_50_on_missing(self, sample_jobs: list[dict[str, Any]]) -> None:
        mock_invoke = AsyncMock(return_value={"content": [{"text": "[]"}]})
        with (
            patch("src.lib.bedrock.invoke_model", mock_invoke),
            patch("src.lib.bedrock.get_haiku_model_id", return_value="haiku-test"),
        ):
            result = await _match_via_haiku(sample_jobs[:3], "Student profile")
            assert all(j["match_score"] == 50 for j in result)


# ---------------------------------------------------------------------------
# match_jobs_via_cognee (integration-style with mocks)
# ---------------------------------------------------------------------------


class TestMatchJobsViaCognee:
    @pytest.mark.asyncio
    async def test_continues_on_insights_failure(self, sample_jobs: list[dict[str, Any]]) -> None:
        """Cognee insights failure should not prevent Haiku scoring."""
        mock_haiku_result = [{**sample_jobs[0], "match_score": 80, "reasoning": "good"}]
        with (
            patch(
                "src.lib.job_matching.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "src.lib.job_matching.ingest_jobs",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.lib.job_matching._query_cognee_insights",
                new_callable=AsyncMock,
                side_effect=RuntimeError("cognee down"),
            ),
            patch(
                "src.lib.job_matching._match_via_haiku",
                new_callable=AsyncMock,
                return_value=mock_haiku_result,
            ) as mock_haiku,
        ):
            result = await match_jobs_via_cognee(
                jobs=sample_jobs[:5],
                grades=[],
                lectures=[],
                skills=[],
                identity={"first_name": "Test", "last_name": "User"},
            )
            assert len(result) == 1
            mock_haiku.assert_awaited_once()
            assert mock_haiku.call_args[1]["kg_insights"] == ""

    @pytest.mark.asyncio
    async def test_passes_insights_to_haiku(self, sample_jobs: list[dict[str, Any]]) -> None:
        """When Cognee returns insights, they should be forwarded to Haiku."""
        mock_haiku_result = [{**sample_jobs[0], "match_score": 90, "reasoning": "great"}]
        with (
            patch(
                "src.lib.job_matching.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "src.lib.job_matching.ingest_jobs",
                new_callable=AsyncMock,
                return_value=5,
            ),
            patch(
                "src.lib.job_matching._query_cognee_insights",
                new_callable=AsyncMock,
                return_value="PyTorch maps to ML roles",
            ),
            patch(
                "src.lib.job_matching._match_via_haiku",
                new_callable=AsyncMock,
                return_value=mock_haiku_result,
            ) as mock_haiku,
        ):
            await match_jobs_via_cognee(
                jobs=sample_jobs[:5],
                grades=[],
                lectures=[],
                skills=[],
                identity={"first_name": "Test", "last_name": "User"},
            )
            assert mock_haiku.call_args[1]["kg_insights"] == "PyTorch maps to ML roles"

    @pytest.mark.asyncio
    async def test_caches_scored_results(self, sample_jobs: list[dict[str, Any]]) -> None:
        """Second call with same profile should hit memory cache."""
        mock_haiku_result = [{**sample_jobs[0], "match_score": 80, "reasoning": "cached"}]
        with (
            patch(
                "src.lib.job_matching.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "src.lib.job_matching.ingest_jobs",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.lib.job_matching._query_cognee_insights",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "src.lib.job_matching._match_via_haiku",
                new_callable=AsyncMock,
                return_value=mock_haiku_result,
            ) as mock_haiku,
        ):
            await match_jobs_via_cognee(
                jobs=sample_jobs[:5],
                grades=[],
                lectures=[],
                skills=[],
                identity={"first_name": "Test", "last_name": "User"},
            )
            await match_jobs_via_cognee(
                jobs=sample_jobs[:5],
                grades=[],
                lectures=[],
                skills=[],
                identity={"first_name": "Test", "last_name": "User"},
            )
            assert mock_haiku.await_count == 1
