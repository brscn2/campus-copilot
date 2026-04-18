"""Seed a demo student with courses, deadlines, and lectures for the hackathon demo."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import DEMO_STUDENT_ID, get_settings
from src.storage.schema import (
    AgentActivityRow,
    Base,
    CourseRow,
    DeadlineRow,
    LectureRow,
    StudentRow,
)


async def seed() -> None:
    engine = create_async_engine(get_settings().database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        student_id = DEMO_STUDENT_ID
        student = StudentRow(
            id=student_id,
            tum_email="alex.mueller@tum.de",
            display_name="Alex Müller",
            program="Informatics, B.Sc.",
            semester=4,
            priorities={"academics": 5, "career": 3, "social": 4},
        )
        session.add(student)

        # Create courses with proper UUIDs
        course_in2346_id = str(uuid4())
        course_in2064_id = str(uuid4())
        course_in2349_id = str(uuid4())

        courses = [
            CourseRow(
                id=course_in2346_id,
                student_id=student_id,
                code="IN2346",
                title="Introduction to Deep Learning",
                professor="Prof. Dr. Niels Landwehr",
                credits=6,
                moodle_id="100001",
            ),
            CourseRow(
                id=course_in2064_id,
                student_id=student_id,
                code="IN2064",
                title="Machine Learning",
                professor="Prof. Dr. Stephan Günnemann",
                credits=6,
                moodle_id="100002",
            ),
            CourseRow(
                id=course_in2349_id,
                student_id=student_id,
                code="IN2349",
                title="Advanced Deep Learning",
                professor="Prof. Dr. Nassir Navab",
                credits=5,
                moodle_id="100003",
            ),
        ]
        session.add_all(courses)

        now = datetime.now(UTC)
        deadlines = [
            DeadlineRow(
                course_id=course_in2346_id,
                title="Homework 1 — Neural Network Implementation",
                due_at=now + timedelta(days=7),
                weight=0.15,
                source="moodle",
                priority_score=85.0,
            ),
            DeadlineRow(
                course_id=course_in2064_id,
                title="Exercise Sheet 1 — Linear Regression",
                due_at=now + timedelta(days=4),
                weight=0.10,
                source="moodle",
                priority_score=92.0,
            ),
            DeadlineRow(
                course_id=course_in2346_id,
                title="Midterm Exam",
                due_at=now + timedelta(days=32),
                weight=0.30,
                source="tumonline",
                priority_score=78.0,
            ),
        ]
        session.add_all(deadlines)

        lectures = [
            LectureRow(
                course_id=course_in2346_id,
                title="Lecture 1 — Neural Network Basics",
                summary="Introduction to artificial neurons, activation functions, forward pass.",
                reviewed=True,
            ),
            LectureRow(
                course_id=course_in2346_id,
                title="Lecture 2 — Backpropagation & Optimization",
                summary="Chain rule, computational graphs, gradient descent variants.",
                reviewed=False,
            ),
            LectureRow(
                course_id=course_in2064_id,
                title="Lecture 1 — Supervised Learning Overview",
                summary="Problem formulation, hypothesis spaces, bias-variance tradeoff.",
                reviewed=True,
            ),
        ]
        session.add_all(lectures)

        activities = [
            AgentActivityRow(
                student_id=student_id,
                agent="academic",
                icon="\U0001f4da",
                text="Summarized new slides from IN2346 (Neural Network Basics)",
                metadata_={},
            ),
            AgentActivityRow(
                student_id=student_id,
                agent="social",
                icon="\U0001f3cb\ufe0f",
                text="ZHS Climbing slot secured for Tue 18:00",
                metadata_={},
            ),
            AgentActivityRow(
                student_id=student_id,
                agent="career",
                icon="\U0001f4e7",
                text="Draft email to Prof. Günnemann ready for review",
                metadata_={},
            ),
            AgentActivityRow(
                student_id=student_id,
                agent="academic",
                icon="\U0001f4dd",
                text="Generated 14 flashcards for IN2064 — Linear Regression",
                metadata_={},
            ),
            AgentActivityRow(
                student_id=student_id,
                agent="social",
                icon="\U0001f37d\ufe0f",
                text="Found 3 overlapping lunch slots with Jonas & Lena",
                metadata_={},
            ),
            AgentActivityRow(
                student_id=student_id,
                agent="career",
                icon="\U0001f4bc",
                text="Matched 2 new working-student roles at BMW & Siemens",
                metadata_={},
            ),
        ]
        session.add_all(activities)

        await session.commit()
        print(f"Seeded demo student: {student.display_name} ({student.tum_email})")
        print(
            f"  {len(courses)} courses, {len(deadlines)} deadlines,"
            f" {len(lectures)} lectures, {len(activities)} activities"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
