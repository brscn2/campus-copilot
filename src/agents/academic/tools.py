"""Pure-function tools for the Academic agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.config import get_settings
from src.integrations.library import book_room as _book_room
from src.integrations.library import list_library_branches as _list_branches
from src.integrations.library import search_rooms as _search_rooms
from src.integrations.library import verify_booking as _verify_booking
from src.integrations.moodle import get_courses as _get_courses
from src.integrations.moodle import get_deadlines as _get_deadlines
from src.integrations.moodle import get_slides as _get_slides
from src.integrations.moodle import get_uploads as _get_uploads
from src.integrations.tumonline import get_professor_info as _get_professor_info
from src.integrations.tumonline import search_thesis_opportunities as _search_thesis
from src.lib.memory import get_core_concepts as _get_core_concepts
from src.lib.memory import get_prerequisites as _get_prerequisites
from src.lib.memory import query_course_knowledge as _query_course_knowledge
from src.lib.s3 import list_objects as _list_s3_objects


@tool
async def list_library_branches() -> list[dict[str, str]]:
    """List all TUM library branches where group rooms can be booked.

    Returns branches with slugs and names. Use the slug with search_rooms
    to see available rooms and time slots at that branch.
    """
    return await _list_branches()


@tool
async def search_rooms(
    branch: str,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Search available rooms and time slots at a TUM library branch.

    Scrapes anny.eu for real-time room availability. Returns rooms with
    capacities and available start/end times for the selected date.

    ALWAYS call this before booking to show the student what's available.

    Args:
        branch: Branch slug — use list_library_branches to see options.
                Common: 'mathematics-informatics', 'main-campus', 'chemistry',
                'physics', 'medicine', 'sport-health', 'weihenstephan'.
        target_date: Day number to check (e.g. '21' for the 21st). Defaults to today.
    """
    settings = get_settings()
    return await _search_rooms(
        tum_username=settings.tum_username,
        tum_password=settings.tum_password,
        branch=branch,
        target_date=target_date,
    )


@tool
async def book_room(
    branch: str,
    room_name: str,
    date_day: str,
    start_time: str,
    end_time: str,
    student_id: str,
    num_persons: int = 3,
) -> dict[str, Any]:
    """Book a specific group room at a TUM library branch via anny.eu.

    Completes the FULL booking flow: date/time/room selection → checkout
    with number of persons → confirmation. Returns booking confirmation
    with QR code for entrance if available.

    IMPORTANT: Always call search_rooms first to show available options,
    then confirm with the student before calling this.

    Args:
        branch: Branch slug (e.g. 'mathematics-informatics').
        room_name: Room name from search results (e.g. 'Group Room 1').
        date_day: Day number in the calendar (e.g. '21').
        start_time: Start time (e.g. '10:00').
        end_time: End time (e.g. '12:00').
        student_id: The student making the booking.
        num_persons: Number of persons using the room (3-8, default 3).
    """
    settings = get_settings()
    result = await _book_room(
        tum_username=settings.tum_username,
        tum_password=settings.tum_password,
        branch=branch,
        room_name=room_name,
        date_day=date_day,
        start_time=start_time,
        end_time=end_time,
        num_persons=num_persons,
    )

    if result.get("status") in ("confirmed", "pending"):
        from datetime import datetime

        from src.cal.orchestrator import register_booking

        today = datetime.now()
        day = int(date_day)
        start_dt = today.replace(
            day=day,
            hour=int(start_time.split(":")[0]),
            minute=int(start_time.split(":")[1]),
            second=0,
            microsecond=0,
        )
        end_dt = today.replace(
            day=day,
            hour=int(end_time.split(":")[0]),
            minute=int(end_time.split(":")[1]),
            second=0,
            microsecond=0,
        )

        try:
            booking = await register_booking(
                student_id=student_id,
                kind="study_room",
                title=f"Library: {room_name} @ {result.get('branch', branch)}",
                starts_at=start_dt,
                ends_at=end_dt,
                location=result.get("branch", branch),
                agent="academic",
            )
            result["calendar"] = booking
        except Exception:
            pass

    return result


@tool
async def verify_library_booking(
    booking_url: str,
) -> dict[str, Any]:
    """Verify a library room booking and retrieve its QR code.

    Use this after booking to confirm the reservation status and get
    the entrance QR code the student needs to check in.

    Args:
        booking_url: The manage_url from the book_room result.
    """
    settings = get_settings()
    return await _verify_booking(
        tum_username=settings.tum_username,
        tum_password=settings.tum_password,
        booking_url=booking_url,
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
    quiz_objects = await _list_s3_objects(f"quizzes/course_{course_id}/")
    available_quizzes = [
        obj["key"].rsplit("/", 1)[-1].replace(".json", "").replace("_", " ") for obj in quiz_objects
    ]
    return {
        "course_id": course_id,
        "core_concepts": concepts,
        "available_quizzes": available_quizzes,
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
    import json

    from src.lib.content_generator import _safe_filename
    from src.lib.s3 import download_file

    key = f"quizzes/course_{course_id}/{_safe_filename(core_concept)}.json"
    try:
        data = await download_file(key)
        quiz = json.loads(data)
    except Exception:
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
async def get_lecture_slides(
    course_id: str,
) -> list[dict[str, Any]]:
    """Get lecture slide decks for a Moodle course.

    Args:
        course_id: The Moodle course identifier (numeric string).
    """
    return await _get_slides(course_id=course_id)


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


@tool
async def get_lecture_slides(
    course_id: str,
) -> list[dict[str, Any]]:
    """Get lecture slides with summaries for a Moodle course.

    Args:
        course_id: The course identifier (e.g. 'IN2064').
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
