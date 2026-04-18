"""Pure-function tools for the Academic agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.integrations.library import book_room as _book_room
from src.integrations.library import search_rooms as _search_rooms
from src.integrations.moodle import get_courses as _get_courses
from src.integrations.moodle import get_deadlines as _get_deadlines
from src.integrations.moodle import get_slides as _get_slides
from src.integrations.tumonline import get_professor_info as _get_professor_info
from src.integrations.tumonline import search_thesis_opportunities as _search_thesis


@tool
async def search_rooms(
    date: str,
    duration_hours: int = 2,
    capacity: int = 1,
    building: str | None = None,
) -> list[dict[str, Any]]:
    """Search for available TUM library study rooms.

    Args:
        date: ISO date string, e.g. '2026-04-18'.
        duration_hours: How many hours you need the room.
        capacity: Minimum number of seats needed.
        building: Optional building filter (e.g. 'Garching', 'Stammgelände').
    """
    return await _search_rooms(
        date=date,
        duration_hours=duration_hours,
        capacity=capacity,
        building=building,
    )


@tool
async def book_room(
    room_id: str,
    start: str,
    end: str,
    student_id: str,
) -> dict[str, Any]:
    """Book a specific library study room.

    Args:
        room_id: The room identifier from search results.
        start: ISO datetime for booking start.
        end: ISO datetime for booking end.
        student_id: The student making the booking.
    """
    return await _book_room(
        room_id=room_id,
        start=start,
        end=end,
        student_id=student_id,
    )


@tool
async def search_thesis_opportunities(
    keywords: list[str] | None = None,
    chair: str | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search for thesis opportunities at TUM chairs.

    Args:
        keywords: Keywords to match against topic/description (e.g. ['reinforcement learning']).
        chair: Chair name filter (e.g. 'Robotics').
        tags: Topic tags to filter by (e.g. ['machine-learning', 'robotics']).
    """
    return await _search_thesis(keywords=keywords, chair=chair, tags=tags)


@tool
async def get_professor_contact(professor_email: str) -> dict[str, Any] | None:
    """Look up a professor's contact details and office hours.

    Args:
        professor_email: The professor's email address from thesis search results.
    """
    return await _get_professor_info(professor_email)


@tool
async def draft_thesis_email(
    student_name: str,
    student_program: str,
    professor_name: str,
    professor_email: str,
    thesis_topic: str,
    motivation: str,
) -> dict[str, str]:
    """Draft a cold email to a professor about a thesis opportunity.

    This returns a draft — the student must review and approve before sending.

    Args:
        student_name: The student's full name.
        student_program: The student's program (e.g. 'Informatics, M.Sc.').
        professor_name: The professor's name.
        professor_email: The professor's email.
        thesis_topic: The thesis topic title.
        motivation: A brief motivation why the student is interested.
    """
    subject = f"Thesis Inquiry: {thesis_topic}"
    body = (
        f"Dear {professor_name},\n\n"
        f"I am {student_name}, a student in the {student_program} program at TUM. "
        f"I am writing to express my interest in the thesis topic "
        f'"{thesis_topic}" listed on your chair\'s website.\n\n'
        f"{motivation}\n\n"
        f"I would welcome the opportunity to discuss this topic further during your "
        f"office hours or at your convenience.\n\n"
        f"Best regards,\n{student_name}"
    )
    return {
        "to": professor_email,
        "subject": subject,
        "body": body,
        "status": "draft",
    }


@tool
async def get_my_courses(student_id: str) -> list[dict[str, Any]]:
    """Get the student's enrolled Moodle courses.

    Args:
        student_id: The student identifier.
    """
    return await _get_courses(student_id=student_id)


@tool
async def get_lecture_slides(course_id: str) -> list[dict[str, Any]]:
    """Get lecture slides for a course, including AI-generated summaries.

    Args:
        course_id: The Moodle course identifier from get_my_courses results.
    """
    return await _get_slides(course_id=course_id)


@tool
async def get_deadlines(
    student_id: str,
    course_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get upcoming deadlines for the student, optionally filtered by course.

    Args:
        student_id: The student identifier.
        course_id: Optional course filter — omit to get all deadlines.
    """
    return await _get_deadlines(student_id=student_id, course_id=course_id)
