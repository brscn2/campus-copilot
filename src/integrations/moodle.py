"""Mock Moodle integration — slide downloads, deadline scraping, course info.

In live mode this would scrape Moodle via Playwright.
For the hackathon demo, returns curated fake data.
"""

from __future__ import annotations

from typing import Any

from src.lib.logging import get_logger

logger = get_logger(__name__)

MOCK_COURSES: list[dict[str, Any]] = [
    {
        "course_id": "moodle-IN2346",
        "code": "IN2346",
        "title": "Introduction to Deep Learning",
        "professor": "Prof. Dr. Niels Landwehr",
        "semester": "SS 2026",
        "moodle_url": "https://www.moodle.tum.de/course/view.php?id=100001",
    },
    {
        "course_id": "moodle-IN2064",
        "code": "IN2064",
        "title": "Machine Learning",
        "professor": "Prof. Dr. Stephan Günnemann",
        "semester": "SS 2026",
        "moodle_url": "https://www.moodle.tum.de/course/view.php?id=100002",
    },
    {
        "course_id": "moodle-IN2349",
        "code": "IN2349",
        "title": "Advanced Deep Learning",
        "professor": "Prof. Dr. Nassir Navab",
        "semester": "SS 2026",
        "moodle_url": "https://www.moodle.tum.de/course/view.php?id=100003",
    },
]

MOCK_SLIDES: dict[str, list[dict[str, Any]]] = {
    "moodle-IN2346": [
        {
            "lecture_id": "lec-idl-01",
            "title": "Lecture 1 — Neural Network Basics",
            "filename": "IDL_Lecture01_NN_Basics.pdf",
            "uploaded_at": "2026-04-07",
            "summary": (
                "Introduction to artificial neurons, activation functions (ReLU, sigmoid, tanh), "
                "forward pass computation, and universal approximation theorem."
            ),
        },
        {
            "lecture_id": "lec-idl-02",
            "title": "Lecture 2 — Backpropagation & Optimization",
            "filename": "IDL_Lecture02_Backprop.pdf",
            "uploaded_at": "2026-04-14",
            "summary": (
                "Chain rule, computational graphs, gradient descent variants (SGD, Adam, AdaGrad), "
                "learning rate scheduling, and weight initialization strategies."
            ),
        },
        {
            "lecture_id": "lec-idl-03",
            "title": "Lecture 3 — Convolutional Neural Networks",
            "filename": "IDL_Lecture03_CNNs.pdf",
            "uploaded_at": "2026-04-21",
            "summary": None,
        },
    ],
    "moodle-IN2064": [
        {
            "lecture_id": "lec-ml-01",
            "title": "Lecture 1 — Supervised Learning Overview",
            "filename": "ML_Lecture01_Supervised.pdf",
            "uploaded_at": "2026-04-08",
            "summary": (
                "Problem formulation, hypothesis spaces, loss functions, empirical risk "
                "minimization, bias-variance tradeoff, and cross-validation."
            ),
        },
        {
            "lecture_id": "lec-ml-02",
            "title": "Lecture 2 — Linear Models & Regularization",
            "filename": "ML_Lecture02_Linear.pdf",
            "uploaded_at": "2026-04-15",
            "summary": (
                "Linear regression, ridge regression, LASSO, elastic net, "
                "logistic regression, and the connection to maximum likelihood."
            ),
        },
    ],
    "moodle-IN2349": [
        {
            "lecture_id": "lec-adl-01",
            "title": "Lecture 1 — Transformers & Attention",
            "filename": "ADL_Lecture01_Transformers.pdf",
            "uploaded_at": "2026-04-09",
            "summary": (
                "Self-attention mechanism, multi-head attention, positional encoding, "
                "encoder-decoder architecture, and the original Transformer paper."
            ),
        },
    ],
}

MOCK_DEADLINES: dict[str, list[dict[str, Any]]] = {
    "moodle-IN2346": [
        {
            "deadline_id": "dl-idl-hw1",
            "title": "Homework 1 — Neural Network Implementation",
            "due_at": "2026-04-25T23:59:00+02:00",
            "weight": 0.15,
            "source": "moodle",
        },
        {
            "deadline_id": "dl-idl-hw2",
            "title": "Homework 2 — CNN from Scratch",
            "due_at": "2026-05-09T23:59:00+02:00",
            "weight": 0.15,
            "source": "moodle",
        },
        {
            "deadline_id": "dl-idl-midterm",
            "title": "Midterm Exam",
            "due_at": "2026-05-20T10:00:00+02:00",
            "weight": 0.30,
            "source": "tumonline",
        },
    ],
    "moodle-IN2064": [
        {
            "deadline_id": "dl-ml-hw1",
            "title": "Exercise Sheet 1 — Linear Regression",
            "due_at": "2026-04-22T23:59:00+02:00",
            "weight": 0.10,
            "source": "moodle",
        },
        {
            "deadline_id": "dl-ml-project",
            "title": "Project Proposal Submission",
            "due_at": "2026-05-01T23:59:00+02:00",
            "weight": 0.20,
            "source": "moodle",
        },
    ],
    "moodle-IN2349": [
        {
            "deadline_id": "dl-adl-paper",
            "title": "Paper Review — Attention Is All You Need",
            "due_at": "2026-04-28T23:59:00+02:00",
            "weight": 0.10,
            "source": "moodle",
        },
    ],
}


async def get_courses(*, student_id: str) -> list[dict[str, Any]]:
    """Get the student's enrolled Moodle courses.

    Args:
        student_id: The student identifier.

    Returns:
        List of enrolled course dicts.
    """
    logger.info("moodle_get_courses", student_id=student_id)
    return MOCK_COURSES


async def get_slides(*, course_id: str) -> list[dict[str, Any]]:
    """Get lecture slides for a course.

    Args:
        course_id: The Moodle course identifier.

    Returns:
        List of lecture slide dicts with summaries where available.
    """
    logger.info("moodle_get_slides", course_id=course_id)
    return MOCK_SLIDES.get(course_id, [])


async def get_deadlines(
    *,
    student_id: str,
    course_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get upcoming deadlines, optionally filtered by course.

    Args:
        student_id: The student identifier.
        course_id: Optional course filter.

    Returns:
        List of deadline dicts sorted by due date.
    """
    logger.info("moodle_get_deadlines", student_id=student_id, course_id=course_id)

    if course_id:
        return MOCK_DEADLINES.get(course_id, [])

    all_deadlines: list[dict[str, Any]] = []
    for deadlines in MOCK_DEADLINES.values():
        all_deadlines.extend(deadlines)

    return sorted(all_deadlines, key=lambda d: d["due_at"])
