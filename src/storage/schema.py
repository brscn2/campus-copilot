"""SQLAlchemy ORM models — the persistence layer."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class StudentRow(Base):
    __tablename__ = "students"

    tum_email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    program: Mapped[str] = mapped_column(String(255))
    semester: Mapped[int] = mapped_column(Integer)
    priorities: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    google_calendar_token: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    tum_credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    courses: Mapped[list[CourseRow]] = relationship(back_populates="student")
    bookings: Mapped[list[BookingRow]] = relationship(back_populates="student")
    sessions: Mapped[list[SessionRow]] = relationship(back_populates="student")


class CourseRow(Base):
    __tablename__ = "courses"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    professor: Mapped[str] = mapped_column(String(255), default="")
    chair: Mapped[str] = mapped_column(String(255), default="")
    credits: Mapped[int] = mapped_column(Integer, default=0)
    moodle_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tumonline_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    student: Mapped[StudentRow] = relationship(back_populates="courses")
    lectures: Mapped[list[LectureRow]] = relationship(back_populates="course")
    deadlines: Mapped[list[DeadlineRow]] = relationship(back_populates="course")

    __table_args__ = (Index("ix_courses_student_code", "student_id", "code"),)


class LectureRow(Base):
    __tablename__ = "lectures"

    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(500))
    slide_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed: Mapped[bool] = mapped_column(default=False)

    course: Mapped[CourseRow] = relationship(back_populates="lectures")
    quiz_results: Mapped[list[QuizResultRow]] = relationship(back_populates="lecture")


class QuizResultRow(Base):
    __tablename__ = "quiz_results"

    lecture_id: Mapped[str] = mapped_column(ForeignKey("lectures.id"))
    score: Mapped[float] = mapped_column(Float)
    questions: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)

    lecture: Mapped[LectureRow] = relationship(back_populates="quiz_results")


class DeadlineRow(Base):
    __tablename__ = "deadlines"

    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(500))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    weight: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50))
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)

    course: Mapped[CourseRow] = relationship(back_populates="deadlines")


class ThesisOpportunityRow(Base):
    __tablename__ = "thesis_opportunities"

    chair: Mapped[str] = mapped_column(String(255))
    professor_name: Mapped[str] = mapped_column(String(255))
    professor_email: Mapped[str] = mapped_column(String(255))
    topic: Mapped[str] = mapped_column(String(1000))
    description: Mapped[str] = mapped_column(Text)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_url: Mapped[str] = mapped_column(String(1000))


class JobRow(Base):
    __tablename__ = "jobs"

    company: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(255), default="")
    salary: Mapped[str] = mapped_column(String(100), default="")
    source_url: Mapped[str] = mapped_column(String(1000))
    posted_at: Mapped[str] = mapped_column(String(50), default="")
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)


class BookingRow(Base):
    __tablename__ = "bookings"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    kind: Mapped[str] = mapped_column(String(50))
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    student: Mapped[StudentRow] = relationship(back_populates="bookings")


class SessionRow(Base):
    __tablename__ = "sessions"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    turns: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)

    student: Mapped[StudentRow] = relationship(back_populates="sessions")
