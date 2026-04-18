"""End-to-end tests for the REST data endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_academic_courses(client: TestClient) -> None:
    response = client.get("/api/academic/courses")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "code" in data[0]


def test_academic_slides(client: TestClient) -> None:
    response = client.get("/api/academic/courses/moodle-IN2346/slides")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "title" in data[0]


def test_academic_deadlines(client: TestClient) -> None:
    response = client.get("/api/academic/deadlines")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "due_at" in data[0]


def test_academic_thesis(client: TestClient) -> None:
    response = client.get("/api/academic/thesis")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "topic" in data[0]


def test_academic_rooms(client: TestClient) -> None:
    response = client.get("/api/academic/rooms")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "room_id" in data[0]


def test_career_jobs(client: TestClient) -> None:
    response = client.get("/api/career/jobs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "company" in data[0]


def test_career_jobs_filtered(client: TestClient) -> None:
    response = client.get("/api/career/jobs?kind=internship")
    assert response.status_code == 200
    data = response.json()
    assert all(j["kind"] == "internship" for j in data)


def test_social_zhs(client: TestClient) -> None:
    response = client.get("/api/social/zhs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "course_id" in data[0]


def test_social_events(client: TestClient) -> None:
    response = client.get("/api/social/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "title" in data[0]


def test_social_mensa(client: TestClient) -> None:
    response = client.get("/api/social/mensa")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "name" in data[0]


def test_social_mensa_vegan(client: TestClient) -> None:
    response = client.get("/api/social/mensa?vegan_only=true")
    assert response.status_code == 200
    data = response.json()
    assert all(item["vegan"] for item in data)
