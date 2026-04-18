"""Pure-function tools for the Academic agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.integrations.library import book_room as _book_room
from src.integrations.library import search_rooms as _search_rooms
from src.integrations.moodle import get_courses as _get_courses
from src.integrations.moodle import get_uploads as _get_uploads
from src.lib.memory import get_core_concepts as _get_core_concepts
from src.lib.memory import get_prerequisites as _get_prerequisites
from src.lib.memory import query_course_knowledge as _query_course_knowledge
from src.lib.quiz import list_available_quizzes as _list_quizzes
from src.lib.quiz import load_quiz as _load_quiz


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
async def search_lectures(
    course_id: str,
    query: str,
) -> list[str]:
    """Search lecture content for a course using the Cognee knowledge graph.

    Use this when the student asks about lecture topics, concepts, or definitions.

    Args:
        course_id: The course identifier (e.g. 'IN2064').
        query: Natural language question about lecture content.
    """
    return await _query_course_knowledge(course_id, query)


@tool
async def get_progress(
    course_id: str,
) -> dict[str, Any]:
    """Get the concept hierarchy and available quizzes for a course.

    Use this to show what topics exist and which quizzes are available.

    Args:
        course_id: The course identifier.
    """
    concepts = await _get_core_concepts(course_id)
    quizzes = _list_quizzes(course_id)
    return {
        "course_id": course_id,
        "core_concepts": concepts,
        "available_quizzes": quizzes,
    }


@tool
async def take_quiz(
    course_id: str,
    core_concept: str,
    num_questions: int = 5,
) -> dict[str, Any]:
    """Load quiz questions for a specific core concept.

    Returns multiple-choice questions the student can answer. After the student
    answers, their progress will be updated.

    Args:
        course_id: The course identifier.
        core_concept: The core concept to quiz on (e.g. 'Modularity').
        num_questions: Number of questions to serve (default 5).
    """
    quiz = _load_quiz(course_id, core_concept)
    if quiz is None:
        return {"error": f"No quiz found for '{core_concept}'. Try running cognify first."}

    questions = quiz.get("questions", [])
    served = questions[:num_questions]
    for q in served:
        q.pop("correct", None)
        q.pop("explanation", None)

    return {
        "core_concept": core_concept,
        "questions": served,
        "total_available": len(questions),
    }


@tool
async def get_prerequisites(
    course_id: str,
    topic: str,
) -> list[str]:
    """Get prerequisite concepts needed to understand a topic.

    Args:
        course_id: The course identifier.
        topic: The topic to find prerequisites for.
    """
    return await _get_prerequisites(course_id, topic)


@tool
async def list_moodle_courses(
    semester: str | None = None,
) -> list[dict[str, Any]]:
    """List the student's enrolled Moodle courses.

    Scrapes the Moodle dashboard for active courses, optionally filtered
    by semester. Each result includes the moodle_id, name, and URL.

    Args:
        semester: Optional semester filter value (e.g. '20252' for SS2025).
    """
    return await _get_courses(semester=semester)


@tool
async def list_course_uploads(
    moodle_course_id: str,
) -> list[dict[str, Any]]:
    """List recent file uploads and resources for a Moodle course.

    Args:
        moodle_course_id: The Moodle course ID (numeric string).
    """
    return await _get_uploads(moodle_course_id)
