"""Pydantic models for quiz, flashcard, and summary learning content.

This module defines all data models used by the learning system including:
- S3-stored content schemas (quiz files, flashcard decks, summaries)
- API request/response models for quiz and flashcard sessions
- Progress tracking and mastery score models
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# S3 Content Schemas
# ============================================================================


class QuizQuestion(BaseModel):
    """A single multiple-choice quiz question with metadata."""

    model_config = ConfigDict(frozen=True)

    id: str
    core_concept: str
    leaf_concepts: list[str]
    question: str
    type: str = "multiple_choice"
    options: list[str]
    correct: str
    difficulty: str = "medium"
    explanation: str = ""


class QuizFile(BaseModel):
    """A quiz file stored in S3 containing multiple questions for a core concept."""

    core_concept: str
    total_leaf_concepts: int
    questions: list[QuizQuestion]
    generated_at: str


class FlashcardItem(BaseModel):
    """A single flashcard with front/back content."""

    model_config = ConfigDict(frozen=True)

    id: str
    core_concept: str
    leaf_concepts: list[str]
    front: str
    back: str
    difficulty: str = "medium"


class FlashcardFile(BaseModel):
    """A flashcard deck stored in S3 for a core concept."""

    core_concept: str
    total_leaf_concepts: int
    cards: list[FlashcardItem]
    generated_at: str


class SummaryFile(BaseModel):
    """A lecture summary stored in S3."""

    lecture: str
    summary: str
    key_takeaways: list[str]
    generated_at: str


# ============================================================================
# API Request Models
# ============================================================================


class QuizRequest(BaseModel):
    """Request to generate or retrieve a quiz session."""

    student_id: str
    course_id: str
    num_questions: int = Field(10, ge=5, le=30)
    core_concepts: list[str] = []


class FlashcardRequest(BaseModel):
    """Request to generate or retrieve a flashcard session."""

    student_id: str
    course_id: str
    num_cards: int = Field(15, ge=5, le=50)
    core_concepts: list[str] = []


class QuizAnswer(BaseModel):
    """A single answer submitted by the student."""

    question_id: str
    selected: str


class QuizSubmission(BaseModel):
    """A complete quiz submission with all answers."""

    student_id: str
    course_id: str
    answers: list[QuizAnswer]


class FlashcardRating(BaseModel):
    """A single flashcard difficulty rating from the student."""

    card_id: str
    rating: str = Field(..., pattern="^(easy|medium|hard)$")


class FlashcardSubmission(BaseModel):
    """A complete flashcard session submission with all ratings."""

    student_id: str
    course_id: str
    ratings: list[FlashcardRating]


class SetMasteryRequest(BaseModel):
    """Request to manually set mastery score for a concept."""

    student_id: str
    course_id: str
    core_concept: str
    mastery: float = Field(..., ge=0.0, le=1.0)


# ============================================================================
# API Response Models
# ============================================================================


class QuizQuestionServed(BaseModel):
    """A quiz question served to the student, with correct answer for feedback."""

    model_config = ConfigDict(frozen=True)

    id: str
    core_concept: str
    leaf_concepts: list[str]
    question: str
    options: list[str]
    difficulty: str
    correct: str = ""
    explanation: str = ""


class QuizSession(BaseModel):
    """A quiz session ready for the student to take."""

    course_id: str
    core_concepts: list[str]
    questions: list[QuizQuestionServed]
    total_available: int


class FlashcardSession(BaseModel):
    """A flashcard session ready for the student to study."""

    course_id: str
    core_concepts: list[str]
    cards: list[FlashcardItem]
    total_available: int


class QuizResult(BaseModel):
    """Results from a graded quiz submission."""

    score: float
    total: int
    correct: int
    per_concept: dict[str, float]
    mastery_updates: dict[str, float]


class FlashcardResult(BaseModel):
    """Results from a flashcard session submission."""

    per_concept: dict[str, float]
    mastery_updates: dict[str, float]


class ConceptProgress(BaseModel):
    """Progress tracking for a single core concept."""

    core_concept: str
    mastery_score: float
    mastery_sources: dict[str, float]
    manual_mastery: float | None = None
    quizzes_taken: int = 0
    quizzes_passed: int = 0
    exercises_completed: int = 0


class CourseProgress(BaseModel):
    """Overall progress for a course with per-concept breakdowns."""

    course_id: str
    overall_mastery: float
    concepts: list[ConceptProgress]


class GenerationResult(BaseModel):
    """Result of a content generation operation."""

    course_id: str
    quizzes_generated: int = 0
    flashcards_generated: int = 0
    summaries_generated: int = 0
    errors: list[str] = []
