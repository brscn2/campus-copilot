"""Mock ZHS (Zentraler Hochschulsport) integration — sports registration sniper.

In live mode this would interact with the ZHS booking system via Playwright.
For the hackathon demo, returns realistic fake data with slot availability.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.lib.logging import get_logger

logger = get_logger(__name__)

MOCK_COURSES: list[dict[str, Any]] = [
    {
        "course_id": "zhs-bould-01",
        "name": "Bouldering — Beginner",
        "category": "climbing",
        "location": "ZHS Kletteranlage, Olympiapark",
        "day": "Monday",
        "time": "18:00-20:00",
        "instructor": "Maximilian Huber",
        "spots_total": 20,
        "spots_available": 0,
        "price": "35 €/semester",
        "registration_opens": "2026-04-20T10:00:00+02:00",
    },
    {
        "course_id": "zhs-bould-02",
        "name": "Bouldering — Advanced",
        "category": "climbing",
        "location": "ZHS Kletteranlage, Olympiapark",
        "day": "Wednesday",
        "time": "18:00-20:00",
        "instructor": "Maximilian Huber",
        "spots_total": 15,
        "spots_available": 2,
        "price": "35 €/semester",
        "registration_opens": "2026-04-20T10:00:00+02:00",
    },
    {
        "course_id": "zhs-yoga-01",
        "name": "Yoga — Hatha Flow",
        "category": "yoga",
        "location": "ZHS Halle 1, Olympiapark",
        "day": "Tuesday",
        "time": "07:30-09:00",
        "instructor": "Lena Fischer",
        "spots_total": 30,
        "spots_available": 5,
        "price": "25 €/semester",
        "registration_opens": "2026-04-20T10:00:00+02:00",
    },
    {
        "course_id": "zhs-swim-01",
        "name": "Swimming — Technique Training",
        "category": "swimming",
        "location": "Olympia-Schwimmhalle",
        "day": "Thursday",
        "time": "12:00-13:30",
        "instructor": "Stefan Richter",
        "spots_total": 20,
        "spots_available": 8,
        "price": "30 €/semester",
        "registration_opens": "2026-04-20T10:00:00+02:00",
    },
    {
        "course_id": "zhs-box-01",
        "name": "Boxing — Beginner",
        "category": "martial_arts",
        "location": "ZHS Halle 3, Olympiapark",
        "day": "Friday",
        "time": "17:00-18:30",
        "instructor": "Ali Yilmaz",
        "spots_total": 25,
        "spots_available": 0,
        "price": "30 €/semester",
        "registration_opens": "2026-04-20T10:00:00+02:00",
    },
    {
        "course_id": "zhs-bball-01",
        "name": "Basketball — Open Gym",
        "category": "ball_sports",
        "location": "ZHS Halle 2, Olympiapark",
        "day": "Wednesday",
        "time": "20:00-22:00",
        "instructor": "Chris Weber",
        "spots_total": 30,
        "spots_available": 12,
        "price": "20 €/semester",
        "registration_opens": "2026-04-20T10:00:00+02:00",
    },
]


async def search_courses(
    *,
    category: str | None = None,
    day: str | None = None,
    keyword: str | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Search for ZHS sport courses.

    Args:
        category: Filter by category (e.g. 'climbing', 'yoga', 'swimming').
        day: Filter by day of week (e.g. 'Monday').
        keyword: Keyword to match against course name.
        available_only: If True, only return courses with open spots.

    Returns:
        List of matching ZHS course dicts.
    """
    logger.info(
        "zhs_search_courses",
        category=category,
        day=day,
        keyword=keyword,
        available_only=available_only,
    )

    results: list[dict[str, Any]] = []
    for course in MOCK_COURSES:
        if category and course["category"] != category:
            continue
        if day and course["day"].lower() != day.lower():
            continue
        if keyword and keyword.lower() not in course["name"].lower():
            continue
        if available_only and course["spots_available"] == 0:
            continue
        results.append(course)

    return results


async def register_for_course(
    *,
    course_id: str,
    student_id: str,
) -> dict[str, Any]:
    """Register a student for a ZHS course.

    Args:
        course_id: The ZHS course identifier.
        student_id: The student making the registration.

    Returns:
        Registration result dict.
    """
    logger.info(
        "zhs_register",
        course_id=course_id,
        student_id=student_id,
    )

    matching = [c for c in MOCK_COURSES if c["course_id"] == course_id]
    if not matching:
        return {"error": f"Course {course_id} not found", "recoverable": False}

    course = matching[0]
    if course["spots_available"] == 0:
        return {
            "status": "waitlisted",
            "course_id": course_id,
            "course_name": course["name"],
            "message": "No spots available. You have been added to the waitlist.",
            "registration_id": f"zhs-wait-{uuid4().hex[:8]}",
        }

    return {
        "status": "confirmed",
        "course_id": course_id,
        "course_name": course["name"],
        "day": course["day"],
        "time": course["time"],
        "location": course["location"],
        "registration_id": f"zhs-reg-{uuid4().hex[:8]}",
        "student_id": student_id,
    }


async def set_snipe_alert(
    *,
    course_id: str,
    student_id: str,
) -> dict[str, Any]:
    """Set a snipe alert for a full ZHS course.

    When a spot opens or registration starts, the student will be notified.

    Args:
        course_id: The ZHS course to watch.
        student_id: The student to notify.

    Returns:
        Snipe alert confirmation.
    """
    logger.info(
        "zhs_set_snipe",
        course_id=course_id,
        student_id=student_id,
    )

    matching = [c for c in MOCK_COURSES if c["course_id"] == course_id]
    if not matching:
        return {"error": f"Course {course_id} not found", "recoverable": False}

    course = matching[0]
    return {
        "status": "snipe_active",
        "course_id": course_id,
        "course_name": course["name"],
        "registration_opens": course["registration_opens"],
        "alert_id": f"zhs-snipe-{uuid4().hex[:8]}",
        "message": (
            f"Snipe alert set for {course['name']}. "
            f"Registration opens {course['registration_opens']}. "
            "You'll be notified when a spot opens up."
        ),
    }
