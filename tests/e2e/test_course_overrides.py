"""End-to-end tests for the course-metadata override endpoints.

These tests stub out the repository layer (which talks to Postgres) so the
HTTP surface can be exercised in isolation without a live DB.  The repository
itself is covered separately in ``tests/unit``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from src.api import pipeline as pipeline_api

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def _stub_repo(monkeypatch: pytest.MonkeyPatch, store: dict[str, dict[str, dict[str, str]]]) -> None:
    """Replace the repo with an in-memory dict keyed by student_id."""

    async def fake_get(_session: Any, student_id: str) -> dict[str, dict[str, str]]:
        return dict(store.get(student_id, {}))

    async def fake_set(
        _session: Any, student_id: str, dataset_name: str, semester: str
    ) -> dict[str, dict[str, str]]:
        bucket = store.setdefault(student_id, {})
        bucket[dataset_name] = {"semester": semester}
        return dict(bucket)

    async def fake_delete(
        _session: Any, student_id: str, dataset_name: str
    ) -> dict[str, dict[str, str]]:
        bucket = store.setdefault(student_id, {})
        bucket.pop(dataset_name, None)
        return dict(bucket)

    async def fake_clear(_session: Any, student_id: str) -> None:
        store.pop(student_id, None)

    monkeypatch.setattr(pipeline_api.overrides_repo, "get_overrides", fake_get)
    monkeypatch.setattr(pipeline_api.overrides_repo, "set_override", fake_set)
    monkeypatch.setattr(pipeline_api.overrides_repo, "delete_override", fake_delete)
    monkeypatch.setattr(pipeline_api.overrides_repo, "clear_overrides", fake_clear)


def _stub_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the real DB session dependency."""

    async def fake_session() -> Any:  # pragma: no cover - pytest fixture style
        yield None

    from src.storage import db as db_module

    monkeypatch.setattr(db_module, "get_session", fake_session)


def test_overrides_empty_by_default(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_session(monkeypatch)
    _stub_repo(monkeypatch, {})

    response = client.get("/api/pipeline/synced/overrides?student_id=demo")
    assert response.status_code == 200
    assert response.json() == {"overrides": {}}


def test_set_then_get_override(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, dict[str, dict[str, str]]] = {}
    _stub_session(monkeypatch)
    _stub_repo(monkeypatch, store)

    put = client.put(
        "/api/pipeline/synced/overrides/demo_dataset",
        json={"student_id": "demo", "semester": "WiSe 2025/26"},
    )
    assert put.status_code == 200
    assert put.json() == {"overrides": {"demo_dataset": {"semester": "WiSe 2025/26"}}}

    get = client.get("/api/pipeline/synced/overrides?student_id=demo")
    assert get.status_code == 200
    assert get.json()["overrides"]["demo_dataset"]["semester"] == "WiSe 2025/26"


def test_set_rejects_empty_semester(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_session(monkeypatch)
    _stub_repo(monkeypatch, {})

    response = client.put(
        "/api/pipeline/synced/overrides/demo_dataset",
        json={"student_id": "demo", "semester": "   "},
    )
    assert response.status_code == 400


def test_delete_single_override(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store = {"demo": {"a": {"semester": "SoSe 2025"}, "b": {"semester": "WiSe 2025/26"}}}
    _stub_session(monkeypatch)
    _stub_repo(monkeypatch, store)

    response = client.delete("/api/pipeline/synced/overrides/a?student_id=demo")
    assert response.status_code == 200
    assert response.json() == {"overrides": {"b": {"semester": "WiSe 2025/26"}}}


def test_clear_all_overrides(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store = {"demo": {"a": {"semester": "SoSe 2025"}}}
    _stub_session(monkeypatch)
    _stub_repo(monkeypatch, store)

    response = client.delete("/api/pipeline/synced/overrides?student_id=demo")
    assert response.status_code == 200
    assert response.json() == {"overrides": {}}
    assert "demo" not in store


def test_synced_courses_apply_override(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The /synced endpoint must swap in the user's chosen semester."""
    _stub_session(monkeypatch)
    _stub_repo(
        monkeypatch,
        {"demo": {"in2346_intro_to_dl_wise_2024_25": {"semester": "WiSe 2025/26"}}},
    )

    async def fake_list_objects(_prefix: str) -> list[dict[str, Any]]:
        return [
            {"key": "slides/in2346_intro_to_dl_wise_2024_25/lec01.pdf", "size": 1, "last_modified": "x"},
            {"key": "slides/in2346_intro_to_dl_wise_2024_25/lec02.pdf", "size": 1, "last_modified": "x"},
        ]

    monkeypatch.setattr("src.lib.s3.list_objects", fake_list_objects)

    response = client.get("/api/pipeline/synced?student_id=demo")
    assert response.status_code == 200
    courses = response.json()["courses"]
    assert len(courses) == 1
    course = courses[0]
    # dataset_name is preserved (still keys S3 / quizzes / Cognee)…
    assert course["dataset_name"] == "in2346_intro_to_dl_wise_2024_25"
    # …but the displayed semester is the user's correction, not the regex value.
    assert course["semester"] == "WiSe 2025/26"
    assert course["pdf_count"] == 2


def test_synced_courses_no_override_uses_regex(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_session(monkeypatch)
    _stub_repo(monkeypatch, {})

    async def fake_list_objects(_prefix: str) -> list[dict[str, Any]]:
        return [
            {"key": "slides/in2346_intro_to_dl_wise_2024_25/lec01.pdf", "size": 1, "last_modified": "x"},
        ]

    monkeypatch.setattr("src.lib.s3.list_objects", fake_list_objects)

    response = client.get("/api/pipeline/synced?student_id=demo")
    assert response.status_code == 200
    course = response.json()["courses"][0]
    # Regex extracts WiSe 2024/25 from the folder name when no override exists.
    assert course["semester"] == "WiSe 2024/25"
