"""Smoke test for the health endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_sse_stream(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={"message": "hello", "session_id": "test", "student_id": "demo"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: final" in response.text
