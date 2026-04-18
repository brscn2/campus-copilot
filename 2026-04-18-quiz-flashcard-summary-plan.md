# Quiz, Flashcard & Summary System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing quiz-only generation with a content generation + serving + progress tracking system that produces quizzes, flashcards, and lecture summaries after every cognify run, stores them on S3, and serves personalized sessions from Postgres mastery data.

**Architecture:** A `content_generator` module generates all three content types after cognify completes, uploading JSON to S3. A separate `quiz_serving` module reads from S3 and Postgres to assemble personalized sessions. A new `mastery` module computes weighted mastery scores from five signal types. New API routes expose quiz/flashcard/summary endpoints. Schema changes add attempt tracking tables and mastery columns.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, AWS Bedrock (Sonnet/Haiku), S3 (boto3), Cognee (cogwit-sdk), pytest + pytest-asyncio.

**Spec:** `2026-04-18-quiz-flashcard-summary-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/models/learning.py` | **Create** | Pydantic models for quiz/flashcard/summary requests, responses, S3 schemas |
| `src/lib/content_generator.py` | **Create** | Generate quizzes, flashcards, summaries after cognify; upload to S3 |
| `src/lib/quiz_serving.py` | **Create** | Sample quizzes/flashcards from S3, score submissions, update mastery |
| `src/lib/mastery.py` | **Create** | Mastery computation: weighted formula, leaf coverage, course-level aggregation |
| `src/storage/schema.py` | **Modify** | Add `QuizAttemptRow`, `FlashcardAttemptRow`, columns on `StudentConceptProgressRow`, remove `QuizResultRow` |
| `src/api/quiz.py` | **Create** | REST endpoints for quiz/flashcard/summary serving + submission |
| `src/main.py` | **Modify** | Register quiz router |
| `src/lib/cognify.py` | **Modify** | Replace quiz hook with content_generator call |
| `src/agents/academic/tools.py` | **Modify** | Update imports from quiz.py → new modules |
| `src/lib/quiz.py` | **Delete** | Superseded by content_generator.py + quiz_serving.py |
| `src/exceptions.py` | **Modify** | Add `QuizNotFoundError`, `ContentGenerationError` |

---

### Task 1: Pydantic Models (`src/models/learning.py`)

**Files:**
- Create: `src/models/learning.py`

All downstream tasks depend on these types. Define them first.

- [ ] **Step 1: Create `src/models/learning.py`**

```python
"""Pydantic models for quiz, flashcard, and summary content."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --- S3 content schemas (what gets stored/loaded from S3) ---


class QuizQuestion(BaseModel):
    """A single MCQ stored in S3."""

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
    """S3 JSON schema for a per-concept quiz file."""

    core_concept: str
    total_leaf_concepts: int
    questions: list[QuizQuestion]
    generated_at: str


class FlashcardItem(BaseModel):
    """A single flashcard stored in S3."""

    model_config = ConfigDict(frozen=True)

    id: str
    core_concept: str
    leaf_concepts: list[str]
    front: str
    back: str
    difficulty: str = "medium"


class FlashcardFile(BaseModel):
    """S3 JSON schema for a per-concept flashcard file."""

    core_concept: str
    total_leaf_concepts: int
    cards: list[FlashcardItem]
    generated_at: str


class SummaryFile(BaseModel):
    """S3 JSON schema for a per-lecture summary file."""

    lecture: str
    summary: str
    key_takeaways: list[str]
    generated_at: str


# --- API request/response models ---


class QuizRequest(BaseModel):
    """Student requests a quiz session."""

    student_id: str
    course_id: str
    num_questions: int = Field(10, ge=5, le=30)
    core_concepts: list[str] = []


class FlashcardRequest(BaseModel):
    """Student requests a flashcard session."""

    student_id: str
    course_id: str
    num_cards: int = Field(15, ge=5, le=50)
    core_concepts: list[str] = []


class QuizQuestionServed(BaseModel):
    """A quiz question served to the student (no correct answer)."""

    model_config = ConfigDict(frozen=True)

    id: str
    core_concept: str
    leaf_concepts: list[str]
    question: str
    options: list[str]
    difficulty: str


class QuizSession(BaseModel):
    """Quiz session returned to the student."""

    course_id: str
    core_concepts: list[str]
    questions: list[QuizQuestionServed]
    total_available: int


class FlashcardSession(BaseModel):
    """Flashcard session returned to the student."""

    course_id: str
    core_concepts: list[str]
    cards: list[FlashcardItem]
    total_available: int


class QuizAnswer(BaseModel):
    """A single answer from the student."""

    question_id: str
    selected: str


class QuizSubmission(BaseModel):
    """Student submits quiz answers."""

    student_id: str
    course_id: str
    answers: list[QuizAnswer]


class FlashcardRating(BaseModel):
    """A single flashcard rating from the student."""

    card_id: str
    rating: str = Field(..., pattern="^(easy|medium|hard)$")


class FlashcardSubmission(BaseModel):
    """Student submits flashcard ratings."""

    student_id: str
    course_id: str
    ratings: list[FlashcardRating]


class QuizResult(BaseModel):
    """Result returned after quiz scoring."""

    score: float
    total: int
    correct: int
    per_concept: dict[str, float]
    mastery_updates: dict[str, float]


class FlashcardResult(BaseModel):
    """Result returned after flashcard rating submission."""

    per_concept: dict[str, float]
    mastery_updates: dict[str, float]


class ConceptProgress(BaseModel):
    """Progress for a single core concept."""

    core_concept: str
    mastery_score: float
    mastery_sources: dict[str, float]
    manual_mastery: float | None = None
    quizzes_taken: int = 0
    quizzes_passed: int = 0
    exercises_completed: int = 0


class CourseProgress(BaseModel):
    """Aggregated course progress."""

    course_id: str
    overall_mastery: float
    concepts: list[ConceptProgress]


class SetMasteryRequest(BaseModel):
    """Student manually sets mastery for a concept."""

    student_id: str
    course_id: str
    core_concept: str
    mastery: float = Field(..., ge=0.0, le=1.0)


class GenerationResult(BaseModel):
    """Result of content generation for a course."""

    course_id: str
    quizzes_generated: int = 0
    flashcards_generated: int = 0
    summaries_generated: int = 0
    errors: list[str] = []
```

- [ ] **Step 2: Verify the file is syntactically valid**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.models.learning import QuizRequest, QuizFile, FlashcardFile, SummaryFile, GenerationResult; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/models/learning.py
git commit -m "feat: add Pydantic models for quiz, flashcard, summary content"
```

---

### Task 2: Schema Changes (`src/storage/schema.py`)

**Files:**
- Modify: `src/storage/schema.py`

Add new tables and columns, remove `QuizResultRow`.

- [ ] **Step 1: Add `manual_mastery` and `mastery_sources` to `StudentConceptProgressRow`**

In `src/storage/schema.py`, add two columns to the existing `StudentConceptProgressRow` class. After the `last_activity` column (line 161), add:

```python
    manual_mastery: Mapped[float | None] = mapped_column(Float, nullable=True)
    mastery_sources: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)
```

- [ ] **Step 2: Add `QuizAttemptRow`**

After the `StudentConceptProgressRow` class, add:

```python
class QuizAttemptRow(Base):
    """Records a student's quiz attempt with per-question answers."""

    __tablename__ = "quiz_attempts"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    core_concepts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    question_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    answers: Mapped[dict[str, dict[str, str]]] = mapped_column(JSONB, default=dict)
    score: Mapped[float] = mapped_column(Float)

    __table_args__ = (Index("ix_quiz_attempts_student_course", "student_id", "course_id"),)
```

- [ ] **Step 3: Add `FlashcardAttemptRow`**

After `QuizAttemptRow`, add:

```python
class FlashcardAttemptRow(Base):
    """Records a student's flashcard review session with per-card ratings."""

    __tablename__ = "flashcard_attempts"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    core_concepts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    card_ratings: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)

    __table_args__ = (Index("ix_flashcard_attempts_student_course", "student_id", "course_id"),)
```

- [ ] **Step 4: Remove `QuizResultRow`**

Delete the entire `QuizResultRow` class (lines 73–80) and remove the `quiz_results` relationship from `LectureRow` (line 70):

```python
    quiz_results: Mapped[list[QuizResultRow]] = relationship(back_populates="lecture")
```

Replace that line with nothing (delete it).

- [ ] **Step 5: Verify imports compile**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.storage.schema import QuizAttemptRow, FlashcardAttemptRow, StudentConceptProgressRow; print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/storage/schema.py
git commit -m "feat: add quiz/flashcard attempt tables, mastery columns, remove QuizResultRow"
```

---

### Task 3: Exceptions (`src/exceptions.py`)

**Files:**
- Modify: `src/exceptions.py`

- [ ] **Step 1: Add new exception classes**

After the `CogneeIngestionError` class, add:

```python
class ContentGenerationError(CogneeError):
    """Failed to generate learning content from the knowledge graph."""


class QuizNotFoundError(CampusCopilotError):
    """Requested quiz content not found on S3."""
```

- [ ] **Step 2: Verify imports**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.exceptions import ContentGenerationError, QuizNotFoundError; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/exceptions.py
git commit -m "feat: add ContentGenerationError and QuizNotFoundError exceptions"
```

---

### Task 4: Mastery Computation (`src/lib/mastery.py`)

**Files:**
- Create: `src/lib/mastery.py`

This is a pure computation module with no I/O — just the mastery formula and helpers.

- [ ] **Step 1: Create `src/lib/mastery.py`**

```python
"""Mastery computation — weighted formula from multiple learning signals."""

from __future__ import annotations

WEIGHT_QUIZ = 0.40
WEIGHT_FLASHCARD = 0.15
WEIGHT_EXERCISE = 0.25
WEIGHT_LECTURE = 0.10
WEIGHT_MANUAL = 0.10

RATING_MAP: dict[str, float] = {"easy": 1.0, "medium": 0.5, "hard": 0.0}


def compute_mastery_score(
    mastery_sources: dict[str, float],
    manual_mastery: float | None,
    has_activity_since_override: bool,
) -> float:
    """Compute the composite mastery score from individual signal sources.

    Args:
        mastery_sources: Per-signal scores, e.g. {"quiz": 0.7, "flashcard": 0.6}.
        manual_mastery: Student self-assessment, or None if not set.
        has_activity_since_override: Whether any signal updated since last manual set.

    Returns:
        Mastery score in [0.0, 1.0].
    """
    if manual_mastery is not None and not has_activity_since_override:
        return max(0.0, min(1.0, manual_mastery))

    manual_val = manual_mastery if manual_mastery is not None else 0.0
    score = (
        WEIGHT_QUIZ * mastery_sources.get("quiz", 0.0)
        + WEIGHT_FLASHCARD * mastery_sources.get("flashcard", 0.0)
        + WEIGHT_EXERCISE * mastery_sources.get("exercise", 0.0)
        + WEIGHT_LECTURE * mastery_sources.get("lecture", 0.0)
        + WEIGHT_MANUAL * manual_val
    )
    return max(0.0, min(1.0, score))


def compute_leaf_coverage(
    served_leaf_concepts: list[str],
    total_leaf_concepts: int,
) -> float:
    """Compute what fraction of a concept's leaf concepts were covered.

    Args:
        served_leaf_concepts: Leaf concepts that appeared in the session.
        total_leaf_concepts: Total leaf concepts for this core concept (from S3 file).

    Returns:
        Coverage ratio in [0.0, 1.0]. Returns 1.0 if total is 0 to avoid division by zero.
    """
    if total_leaf_concepts <= 0:
        return 1.0
    unique = len(set(served_leaf_concepts))
    return min(1.0, unique / total_leaf_concepts)


def update_signal_moving_average(
    current: float,
    new_value: float,
    coverage: float,
    alpha: float = 0.3,
) -> float:
    """Update a mastery signal as an exponential moving average, dampened by leaf coverage.

    Args:
        current: Current signal value.
        new_value: New observation (e.g. quiz score for this concept).
        coverage: Leaf coverage ratio — dampens the update weight.
        alpha: Base learning rate before coverage dampening.

    Returns:
        Updated signal value in [0.0, 1.0].
    """
    effective_alpha = alpha * coverage
    updated = current * (1 - effective_alpha) + new_value * effective_alpha
    return max(0.0, min(1.0, updated))


def average_flashcard_rating(ratings: dict[str, str]) -> float:
    """Convert flashcard ratings to a 0-1 score.

    Args:
        ratings: Mapping of card_id → "easy"|"medium"|"hard".

    Returns:
        Average score. Returns 0.5 if no ratings.
    """
    if not ratings:
        return 0.5
    values = [RATING_MAP.get(r, 0.5) for r in ratings.values()]
    return sum(values) / len(values)
```

- [ ] **Step 2: Verify the module loads**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.lib.mastery import compute_mastery_score, compute_leaf_coverage, update_signal_moving_average; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/lib/mastery.py
git commit -m "feat: add mastery computation module with weighted formula and leaf coverage"
```

---

### Task 5: Content Generator (`src/lib/content_generator.py`)

**Files:**
- Create: `src/lib/content_generator.py`

This is the main generation module that runs after cognify. It queries Cognee, calls Bedrock, and uploads JSON to S3.

- [ ] **Step 1: Create `src/lib/content_generator.py`**

```python
"""Content generation pipeline — quizzes, flashcards, and summaries.

Replaces src/lib/quiz.py. Triggered after cognify completes. All content is
regenerated on every cognify run (full S3 overwrite).

Future direction: track a concept manifest on S3 to diff against and only
regenerate for new/changed concepts. This avoids redundant LLM calls when
only a single lecture is added to a course.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from src.lib.bedrock import get_haiku_model_id, get_sonnet_model_id, invoke_model
from src.lib.memory import get_core_concepts, get_quiz_material, query_course_knowledge
from src.lib.s3 import upload_file as s3_upload
from src.models.learning import GenerationResult

logger = structlog.get_logger(__name__)

# --- LLM system prompts ---

QUIZ_SYSTEM_PROMPT = """\
You are a quiz generator for university courses. Given leaf concepts with definitions, \
generate multiple-choice questions that test understanding.

Rules:
- 3-5 questions per core concept
- Each question has exactly 4 options (A, B, C, D)
- Exactly one correct answer
- A question may test multiple leaf concepts
- Vary difficulty: easy, medium, hard
- Include a brief explanation for the correct answer
- Questions should test understanding, not just memorization

Respond with valid JSON only. No markdown, no code fences. Use this exact format:
[
  {
    "leaf_concepts": ["concept1", "concept2"],
    "question": "the question text",
    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
    "correct": "A",
    "difficulty": "medium",
    "explanation": "brief explanation"
  }
]
"""

FLASHCARD_SYSTEM_PROMPT = """\
You are a flashcard generator for university courses. Given leaf concepts with definitions, \
create flashcards focused on the most important leaf concepts.

Rules:
- Focus on concepts most likely to appear on exams or that form prerequisites
- Each flashcard has a front (question/prompt) and back (answer/explanation)
- A flashcard may cover multiple related leaf concepts
- Vary difficulty: easy, medium, hard
- Be precise and concise — no filler

Respond with valid JSON only. No markdown, no code fences. Use this exact format:
[
  {
    "leaf_concepts": ["concept1"],
    "front": "question or prompt",
    "back": "answer or explanation",
    "difficulty": "medium"
  }
]
"""

SUMMARY_SYSTEM_PROMPT = """\
You are a lecture summarizer for university courses. Given information about a lecture, \
produce a concise summary.

Rules:
- Summary must be exactly 3 sentences
- Extract 3-5 key takeaways as bullet points
- Be precise and factual — no filler or generic statements

Respond with valid JSON only. No markdown, no code fences. Use this exact format:
{
  "summary": "Three sentence summary here.",
  "key_takeaways": ["takeaway 1", "takeaway 2", "takeaway 3"]
}
"""


def _safe_filename(name: str) -> str:
    """Convert a concept/lecture name to a safe S3 key component."""
    return "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip().replace(" ", "_")[:80]


async def generate_all_for_course(course_id: str) -> GenerationResult:
    """Generate all learning content for a course and upload to S3.

    Args:
        course_id: Course identifier matching the Cognee dataset.

    Returns:
        Summary of what was generated.
    """
    logger.info("content_generation_start", course_id=course_id)
    result = GenerationResult(course_id=course_id)

    concepts = await get_core_concepts(course_id)
    if not concepts:
        logger.warning("content_generation_no_concepts", course_id=course_id)
        result.errors.append("No core concepts found in knowledge graph")
        return result

    concept_names = [c.get("name", "") for c in concepts if c.get("name")]

    for concept_name in concept_names:
        leaf_material = await get_quiz_material(course_id, concept_name)
        if not leaf_material:
            logger.warning("content_generation_no_material", course_id=course_id, concept=concept_name)
            continue

        total_leaf = len(leaf_material)
        material_text = "\n\n".join(leaf_material)

        quiz_ok = await _generate_quiz(course_id, concept_name, material_text, total_leaf)
        if quiz_ok:
            result.quizzes_generated += 1

        flashcard_ok = await _generate_flashcards(course_id, concept_name, material_text, total_leaf)
        if flashcard_ok:
            result.flashcards_generated += 1

    summary_count = await _generate_summaries(course_id)
    result.summaries_generated = summary_count

    logger.info(
        "content_generation_done",
        course_id=course_id,
        quizzes=result.quizzes_generated,
        flashcards=result.flashcards_generated,
        summaries=result.summaries_generated,
    )
    return result


async def _generate_quiz(
    course_id: str,
    concept_name: str,
    material_text: str,
    total_leaf: int,
) -> bool:
    """Generate quiz questions for one core concept and upload to S3."""
    logger.info("quiz_generate_start", course_id=course_id, concept=concept_name)
    prompt = (
        f"Core concept: {concept_name}\n\n"
        f"Leaf concepts and definitions:\n{material_text}\n\n"
        f"Generate 3-5 quiz questions for these leaf concepts."
    )

    try:
        response = await invoke_model(
            model_id=get_sonnet_model_id(),
            messages=[{"role": "user", "content": prompt}],
            system=QUIZ_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.5,
        )
        raw_text = response.get("content", [{}])[0].get("text", "[]")
        questions_raw = json.loads(raw_text)
    except (json.JSONDecodeError, KeyError, IndexError):
        logger.error("quiz_generate_parse_failed", course_id=course_id, concept=concept_name)
        return False

    questions = []
    for q in questions_raw:
        questions.append({
            "id": str(uuid4()),
            "core_concept": concept_name,
            "leaf_concepts": q.get("leaf_concepts", []),
            "question": q.get("question", ""),
            "type": "multiple_choice",
            "options": q.get("options", []),
            "correct": q.get("correct", ""),
            "difficulty": q.get("difficulty", "medium"),
            "explanation": q.get("explanation", ""),
        })

    quiz_data = {
        "core_concept": concept_name,
        "total_leaf_concepts": total_leaf,
        "questions": questions,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    key = f"quizzes/course_{course_id}/{_safe_filename(concept_name)}.json"
    await s3_upload(key, json.dumps(quiz_data, indent=2).encode(), content_type="application/json")
    logger.info("quiz_generated", course_id=course_id, concept=concept_name, questions=len(questions))
    return True


async def _generate_flashcards(
    course_id: str,
    concept_name: str,
    material_text: str,
    total_leaf: int,
) -> bool:
    """Generate flashcards for one core concept and upload to S3."""
    logger.info("flashcard_generate_start", course_id=course_id, concept=concept_name)
    prompt = (
        f"Core concept: {concept_name}\n\n"
        f"Leaf concepts and definitions:\n{material_text}\n\n"
        f"Generate flashcards for the most important leaf concepts."
    )

    try:
        response = await invoke_model(
            model_id=get_haiku_model_id(),
            messages=[{"role": "user", "content": prompt}],
            system=FLASHCARD_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.3,
        )
        raw_text = response.get("content", [{}])[0].get("text", "[]")
        cards_raw = json.loads(raw_text)
    except (json.JSONDecodeError, KeyError, IndexError):
        logger.error("flashcard_generate_parse_failed", course_id=course_id, concept=concept_name)
        return False

    cards = []
    for c in cards_raw:
        cards.append({
            "id": str(uuid4()),
            "core_concept": concept_name,
            "leaf_concepts": c.get("leaf_concepts", []),
            "front": c.get("front", ""),
            "back": c.get("back", ""),
            "difficulty": c.get("difficulty", "medium"),
        })

    flashcard_data = {
        "core_concept": concept_name,
        "total_leaf_concepts": total_leaf,
        "cards": cards,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    key = f"flashcards/course_{course_id}/{_safe_filename(concept_name)}.json"
    await s3_upload(key, json.dumps(flashcard_data, indent=2).encode(), content_type="application/json")
    logger.info("flashcard_generated", course_id=course_id, concept=concept_name, cards=len(cards))
    return True


async def _generate_summaries(course_id: str) -> int:
    """Generate lecture summaries for a course and upload to S3."""
    logger.info("summary_generate_start", course_id=course_id)

    lectures_raw = await query_course_knowledge(
        course_id,
        "List all distinct lectures or chapters covered in this course. "
        "For each, give the title and a brief description of what it covers.",
    )

    if not lectures_raw:
        logger.warning("summary_generate_no_lectures", course_id=course_id)
        return 0

    count = 0
    for lecture_text in lectures_raw:
        lecture_title = lecture_text[:100].split("\n")[0].strip()
        if not lecture_title:
            continue

        prompt = (
            f"Lecture: {lecture_title}\n\n"
            f"Content overview:\n{lecture_text}\n\n"
            f"Generate a concise summary (exactly 3 sentences) and key takeaways."
        )

        try:
            response = await invoke_model(
                model_id=get_sonnet_model_id(),
                messages=[{"role": "user", "content": prompt}],
                system=SUMMARY_SYSTEM_PROMPT,
                max_tokens=1024,
                temperature=0.3,
            )
            raw_text = response.get("content", [{}])[0].get("text", "{}")
            summary_data = json.loads(raw_text)
        except (json.JSONDecodeError, KeyError, IndexError):
            logger.error("summary_generate_parse_failed", course_id=course_id, lecture=lecture_title)
            continue

        file_data = {
            "lecture": lecture_title,
            "summary": summary_data.get("summary", ""),
            "key_takeaways": summary_data.get("key_takeaways", []),
            "generated_at": datetime.now(UTC).isoformat(),
        }

        key = f"summaries/course_{course_id}/{_safe_filename(lecture_title)}.json"
        await s3_upload(key, json.dumps(file_data, indent=2).encode(), content_type="application/json")
        count += 1

    logger.info("summary_generated", course_id=course_id, count=count)
    return count
```

- [ ] **Step 2: Verify the module loads**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.lib.content_generator import generate_all_for_course; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/lib/content_generator.py
git commit -m "feat: add content generator for quizzes, flashcards, and summaries"
```

---

### Task 6: Quiz & Flashcard Serving (`src/lib/quiz_serving.py`)

**Files:**
- Create: `src/lib/quiz_serving.py`

Reads from S3 + Postgres to assemble personalized sessions, scores submissions, updates mastery.

- [ ] **Step 1: Create `src/lib/quiz_serving.py`**

```python
"""Quiz and flashcard serving — sample from S3, score submissions, update mastery."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import QuizNotFoundError
from src.lib.mastery import (
    average_flashcard_rating,
    compute_leaf_coverage,
    compute_mastery_score,
    update_signal_moving_average,
)
from src.lib.s3 import download_file, list_objects
from src.models.learning import (
    FlashcardItem,
    FlashcardResult,
    FlashcardSession,
    FlashcardSubmission,
    QuizFile,
    QuizQuestionServed,
    QuizResult,
    QuizSession,
    QuizSubmission,
)
from src.storage.schema import (
    FlashcardAttemptRow,
    QuizAttemptRow,
    StudentConceptProgressRow,
)

logger = structlog.get_logger(__name__)


# --- S3 helpers ---


async def _load_quiz_file(course_id: str, concept: str) -> QuizFile | None:
    """Load a quiz JSON file from S3 for a given concept."""
    from src.lib.content_generator import _safe_filename

    key = f"quizzes/course_{course_id}/{_safe_filename(concept)}.json"
    try:
        data = await download_file(key)
        return QuizFile.model_validate_json(data)
    except Exception:
        logger.warning("quiz_file_not_found", key=key)
        return None


async def _load_flashcard_file(course_id: str, concept: str) -> Any | None:
    """Load a flashcard JSON file from S3 for a given concept."""
    from src.lib.content_generator import _safe_filename
    from src.models.learning import FlashcardFile

    key = f"flashcards/course_{course_id}/{_safe_filename(concept)}.json"
    try:
        data = await download_file(key)
        return FlashcardFile.model_validate_json(data)
    except Exception:
        logger.warning("flashcard_file_not_found", key=key)
        return None


async def _list_available_concepts(course_id: str, content_type: str) -> list[str]:
    """List all concepts that have generated content on S3."""
    prefix = f"{content_type}/course_{course_id}/"
    objects = await list_objects(prefix)
    concepts = []
    for obj in objects:
        name = obj["key"].rsplit("/", 1)[-1].replace(".json", "").replace("_", " ")
        concepts.append(name)
    return concepts


async def _get_seen_question_ids(
    session: AsyncSession,
    student_id: str,
    course_id: str,
) -> set[str]:
    """Get all question IDs this student has already answered for this course."""
    stmt = select(QuizAttemptRow.question_ids).where(
        QuizAttemptRow.student_id == student_id,
        QuizAttemptRow.course_id == course_id,
    )
    result = await session.execute(stmt)
    seen: set[str] = set()
    for (qids,) in result:
        if qids:
            seen.update(qids)
    return seen


async def _get_seen_card_ids(
    session: AsyncSession,
    student_id: str,
    course_id: str,
) -> set[str]:
    """Get all flashcard IDs this student has already rated for this course."""
    stmt = select(FlashcardAttemptRow.card_ratings).where(
        FlashcardAttemptRow.student_id == student_id,
        FlashcardAttemptRow.course_id == course_id,
    )
    result = await session.execute(stmt)
    seen: set[str] = set()
    for (ratings,) in result:
        if ratings:
            seen.update(ratings.keys())
    return seen


async def _pick_weakest_concepts(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    available: list[str],
    limit: int,
) -> list[str]:
    """Pick the weakest concepts from the student's progress, falling back to random."""
    stmt = select(
        StudentConceptProgressRow.core_concept,
        StudentConceptProgressRow.mastery_score,
    ).where(
        StudentConceptProgressRow.student_id == student_id,
        StudentConceptProgressRow.course_id == course_id,
    )
    result = await session.execute(stmt)
    scores = {row[0]: row[1] for row in result}

    ranked = sorted(available, key=lambda c: scores.get(c, 0.0))
    return ranked[:limit]


# --- Serving ---


async def serve_quiz(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    num_questions: int,
    core_concepts: list[str],
) -> QuizSession:
    """Assemble a personalized quiz from S3 content.

    Args:
        session: DB session.
        student_id: Student identifier.
        course_id: Course identifier.
        num_questions: Desired number of questions.
        core_concepts: Explicit concepts, or empty for auto-pick weakest.

    Returns:
        QuizSession ready for the frontend.
    """
    available = await _list_available_concepts(course_id, "quizzes")
    if not available:
        raise QuizNotFoundError(f"No quizzes found for course {course_id}")

    if not core_concepts:
        max_concepts = max(1, num_questions // 3)
        core_concepts = await _pick_weakest_concepts(session, student_id, course_id, available, max_concepts)

    seen_ids = await _get_seen_question_ids(session, student_id, course_id)

    all_questions: list[QuizQuestionServed] = []
    total_available = 0

    for concept in core_concepts:
        quiz_file = await _load_quiz_file(course_id, concept)
        if quiz_file is None:
            continue
        total_available += len(quiz_file.questions)
        for q in quiz_file.questions:
            if q.id not in seen_ids:
                all_questions.append(QuizQuestionServed(
                    id=q.id,
                    core_concept=q.core_concept,
                    leaf_concepts=q.leaf_concepts,
                    question=q.question,
                    options=q.options,
                    difficulty=q.difficulty,
                ))

    if not all_questions:
        all_questions = []
        for concept in core_concepts:
            quiz_file = await _load_quiz_file(course_id, concept)
            if quiz_file is None:
                continue
            for q in quiz_file.questions:
                all_questions.append(QuizQuestionServed(
                    id=q.id,
                    core_concept=q.core_concept,
                    leaf_concepts=q.leaf_concepts,
                    question=q.question,
                    options=q.options,
                    difficulty=q.difficulty,
                ))

    random.shuffle(all_questions)
    served = all_questions[:num_questions]

    return QuizSession(
        course_id=course_id,
        core_concepts=list({q.core_concept for q in served}),
        questions=served,
        total_available=total_available,
    )


async def serve_flashcards(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    num_cards: int,
    core_concepts: list[str],
) -> FlashcardSession:
    """Assemble a personalized flashcard session from S3 content.

    Args:
        session: DB session.
        student_id: Student identifier.
        course_id: Course identifier.
        num_cards: Desired number of cards.
        core_concepts: Explicit concepts, or empty for auto-pick weakest.

    Returns:
        FlashcardSession ready for the frontend.
    """
    available = await _list_available_concepts(course_id, "flashcards")
    if not available:
        raise QuizNotFoundError(f"No flashcards found for course {course_id}")

    if not core_concepts:
        max_concepts = max(1, num_cards // 5)
        core_concepts = await _pick_weakest_concepts(session, student_id, course_id, available, max_concepts)

    seen_ids = await _get_seen_card_ids(session, student_id, course_id)

    all_cards: list[FlashcardItem] = []
    total_available = 0

    for concept in core_concepts:
        fc_file = await _load_flashcard_file(course_id, concept)
        if fc_file is None:
            continue
        total_available += len(fc_file.cards)
        for card in fc_file.cards:
            if card.id not in seen_ids:
                all_cards.append(card)

    if not all_cards:
        for concept in core_concepts:
            fc_file = await _load_flashcard_file(course_id, concept)
            if fc_file is None:
                continue
            all_cards.extend(fc_file.cards)

    random.shuffle(all_cards)
    served = all_cards[:num_cards]

    return FlashcardSession(
        course_id=course_id,
        core_concepts=list({c.core_concept for c in served}),
        cards=served,
        total_available=total_available,
    )


# --- Scoring & mastery updates ---


async def score_quiz(
    session: AsyncSession,
    submission: QuizSubmission,
) -> QuizResult:
    """Score a quiz submission and update mastery.

    Args:
        session: DB session.
        submission: Student's quiz answers.

    Returns:
        QuizResult with scores and mastery updates.
    """
    answer_lookup: dict[str, dict[str, Any]] = {}
    concept_questions: dict[str, list[dict[str, Any]]] = {}

    for ans in submission.answers:
        answer_lookup[ans.question_id] = {"selected": ans.selected}

    available_concepts = await _list_available_concepts(submission.course_id, "quizzes")
    total_correct = 0
    total_count = len(submission.answers)

    for concept in available_concepts:
        quiz_file = await _load_quiz_file(submission.course_id, concept)
        if quiz_file is None:
            continue
        for q in quiz_file.questions:
            if q.id in answer_lookup:
                is_correct = answer_lookup[q.id]["selected"] == q.correct
                answer_lookup[q.id]["correct"] = is_correct
                answer_lookup[q.id]["core_concept"] = q.core_concept
                answer_lookup[q.id]["leaf_concepts"] = q.leaf_concepts
                if is_correct:
                    total_correct += 1
                concept_questions.setdefault(q.core_concept, []).append({
                    "correct": is_correct,
                    "leaf_concepts": q.leaf_concepts,
                    "total_leaf_concepts": quiz_file.total_leaf_concepts,
                })

    overall_score = total_correct / total_count if total_count > 0 else 0.0

    attempt = QuizAttemptRow(
        student_id=submission.student_id,
        course_id=submission.course_id,
        core_concepts=list(concept_questions.keys()),
        question_ids=[a.question_id for a in submission.answers],
        answers={a.question_id: answer_lookup.get(a.question_id, {}) for a in submission.answers},
        score=overall_score,
    )
    session.add(attempt)

    per_concept: dict[str, float] = {}
    mastery_updates: dict[str, float] = {}

    for concept, qs in concept_questions.items():
        concept_correct = sum(1 for q in qs if q["correct"])
        concept_score = concept_correct / len(qs) if qs else 0.0
        per_concept[concept] = concept_score

        all_leafs = []
        for q in qs:
            all_leafs.extend(q["leaf_concepts"])
        total_leaf = qs[0]["total_leaf_concepts"] if qs else 1
        coverage = compute_leaf_coverage(all_leafs, total_leaf)

        new_mastery = await _update_concept_mastery(
            session,
            submission.student_id,
            submission.course_id,
            concept,
            signal="quiz",
            new_value=concept_score,
            coverage=coverage,
            passed=concept_score >= 0.7,
        )
        mastery_updates[concept] = new_mastery

    await session.commit()

    return QuizResult(
        score=overall_score,
        total=total_count,
        correct=total_correct,
        per_concept=per_concept,
        mastery_updates=mastery_updates,
    )


async def score_flashcards(
    session: AsyncSession,
    submission: FlashcardSubmission,
) -> FlashcardResult:
    """Score a flashcard submission and update mastery.

    Args:
        session: DB session.
        submission: Student's flashcard ratings.

    Returns:
        FlashcardResult with mastery updates.
    """
    card_lookup: dict[str, str] = {r.card_id: r.rating for r in submission.ratings}

    concept_cards: dict[str, dict[str, Any]] = {}

    available_concepts = await _list_available_concepts(submission.course_id, "flashcards")

    for concept in available_concepts:
        fc_file = await _load_flashcard_file(submission.course_id, concept)
        if fc_file is None:
            continue
        for card in fc_file.cards:
            if card.id in card_lookup:
                concept_cards.setdefault(card.core_concept, {
                    "ratings": {},
                    "leaf_concepts": [],
                    "total_leaf_concepts": fc_file.total_leaf_concepts,
                })
                concept_cards[card.core_concept]["ratings"][card.id] = card_lookup[card.id]
                concept_cards[card.core_concept]["leaf_concepts"].extend(card.leaf_concepts)

    attempt = FlashcardAttemptRow(
        student_id=submission.student_id,
        course_id=submission.course_id,
        core_concepts=list(concept_cards.keys()),
        card_ratings=card_lookup,
    )
    session.add(attempt)

    per_concept: dict[str, float] = {}
    mastery_updates: dict[str, float] = {}

    for concept, data in concept_cards.items():
        rating_score = average_flashcard_rating(data["ratings"])
        per_concept[concept] = rating_score

        coverage = compute_leaf_coverage(data["leaf_concepts"], data["total_leaf_concepts"])

        new_mastery = await _update_concept_mastery(
            session,
            submission.student_id,
            submission.course_id,
            concept,
            signal="flashcard",
            new_value=rating_score,
            coverage=coverage,
        )
        mastery_updates[concept] = new_mastery

    await session.commit()

    return FlashcardResult(
        per_concept=per_concept,
        mastery_updates=mastery_updates,
    )


async def _update_concept_mastery(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    core_concept: str,
    *,
    signal: str,
    new_value: float,
    coverage: float,
    passed: bool | None = None,
) -> float:
    """Upsert a StudentConceptProgressRow and recompute mastery.

    Args:
        session: DB session.
        student_id: Student identifier.
        course_id: Course identifier.
        core_concept: The core concept being updated.
        signal: Which signal is updating ("quiz", "flashcard", "exercise", "lecture").
        new_value: The new signal observation (0-1).
        coverage: Leaf coverage ratio for dampening.
        passed: For quiz signal, whether the concept was passed (score >= 0.7).

    Returns:
        New composite mastery score.
    """
    stmt = select(StudentConceptProgressRow).where(
        StudentConceptProgressRow.student_id == student_id,
        StudentConceptProgressRow.course_id == course_id,
        StudentConceptProgressRow.core_concept == core_concept,
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        row = StudentConceptProgressRow(
            student_id=student_id,
            course_id=course_id,
            core_concept=core_concept,
            mastery_score=0.0,
            exercises_completed=0,
            quizzes_taken=0,
            quizzes_passed=0,
            mastery_sources={},
        )
        session.add(row)

    sources = dict(row.mastery_sources) if row.mastery_sources else {}
    current_signal = sources.get(signal, 0.0)
    sources[signal] = update_signal_moving_average(current_signal, new_value, coverage)
    row.mastery_sources = sources

    if signal == "quiz":
        row.quizzes_taken += 1
        if passed:
            row.quizzes_passed += 1
    elif signal == "exercise":
        row.exercises_completed += 1

    has_activity = True
    row.mastery_score = compute_mastery_score(sources, row.manual_mastery, has_activity)
    row.last_activity = datetime.now(UTC)

    return row.mastery_score


async def get_course_progress(
    session: AsyncSession,
    student_id: str,
    course_id: str,
) -> dict[str, Any]:
    """Get progress for all concepts in a course.

    Args:
        session: DB session.
        student_id: Student identifier.
        course_id: Course identifier.

    Returns:
        Dict with overall_mastery and per-concept progress.
    """
    stmt = select(StudentConceptProgressRow).where(
        StudentConceptProgressRow.student_id == student_id,
        StudentConceptProgressRow.course_id == course_id,
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    concepts = []
    total_mastery = 0.0
    for row in rows:
        concepts.append({
            "core_concept": row.core_concept,
            "mastery_score": row.mastery_score,
            "mastery_sources": row.mastery_sources or {},
            "manual_mastery": row.manual_mastery,
            "quizzes_taken": row.quizzes_taken,
            "quizzes_passed": row.quizzes_passed,
            "exercises_completed": row.exercises_completed,
        })
        total_mastery += row.mastery_score

    overall = total_mastery / len(rows) if rows else 0.0

    return {
        "course_id": course_id,
        "overall_mastery": overall,
        "concepts": concepts,
    }


async def set_manual_mastery(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    core_concept: str,
    mastery: float,
) -> float:
    """Set a manual mastery override for a concept.

    Args:
        session: DB session.
        student_id: Student identifier.
        course_id: Course identifier.
        core_concept: The core concept.
        mastery: Student's self-assessment (0.0 to 1.0).

    Returns:
        New composite mastery score.
    """
    stmt = select(StudentConceptProgressRow).where(
        StudentConceptProgressRow.student_id == student_id,
        StudentConceptProgressRow.course_id == course_id,
        StudentConceptProgressRow.core_concept == core_concept,
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        row = StudentConceptProgressRow(
            student_id=student_id,
            course_id=course_id,
            core_concept=core_concept,
            mastery_score=mastery,
            exercises_completed=0,
            quizzes_taken=0,
            quizzes_passed=0,
            mastery_sources={},
            manual_mastery=mastery,
        )
        session.add(row)
    else:
        row.manual_mastery = mastery
        sources = dict(row.mastery_sources) if row.mastery_sources else {}
        sources["manual"] = mastery
        row.mastery_sources = sources
        row.mastery_score = compute_mastery_score(sources, mastery, has_activity_since_override=False)

    await session.commit()
    return row.mastery_score
```

- [ ] **Step 2: Verify the module loads**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.lib.quiz_serving import serve_quiz, score_quiz, get_course_progress; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/lib/quiz_serving.py
git commit -m "feat: add quiz/flashcard serving with personalization and mastery updates"
```

---

### Task 7: API Routes (`src/api/quiz.py`)

**Files:**
- Create: `src/api/quiz.py`
- Modify: `src/main.py`

- [ ] **Step 1: Create `src/api/quiz.py`**

```python
"""REST endpoints for quizzes, flashcards, summaries, and progress."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.lib.quiz_serving import (
    get_course_progress,
    score_flashcards,
    score_quiz,
    serve_flashcards,
    serve_quiz,
    set_manual_mastery,
)
from src.lib.s3 import download_file, list_objects
from src.models.learning import (
    FlashcardRequest,
    FlashcardSubmission,
    QuizRequest,
    QuizSubmission,
    SetMasteryRequest,
)
from src.storage.db import get_session

router = APIRouter(prefix="/learning", tags=["learning"])


@router.post("/quiz")
async def request_quiz(
    body: QuizRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Request a personalized quiz session."""
    result = await serve_quiz(
        session,
        student_id=body.student_id,
        course_id=body.course_id,
        num_questions=body.num_questions,
        core_concepts=body.core_concepts,
    )
    return result.model_dump()


@router.post("/quiz/submit")
async def submit_quiz(
    body: QuizSubmission,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit quiz answers and get scores + mastery updates."""
    result = await score_quiz(session, body)
    return result.model_dump()


@router.post("/flashcards")
async def request_flashcards(
    body: FlashcardRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Request a personalized flashcard session."""
    result = await serve_flashcards(
        session,
        student_id=body.student_id,
        course_id=body.course_id,
        num_cards=body.num_cards,
        core_concepts=body.core_concepts,
    )
    return result.model_dump()


@router.post("/flashcards/submit")
async def submit_flashcards(
    body: FlashcardSubmission,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit flashcard ratings and get mastery updates."""
    result = await score_flashcards(session, body)
    return result.model_dump()


@router.get("/progress/{student_id}/{course_id}")
async def get_progress(
    student_id: str,
    course_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get student progress for a course."""
    return await get_course_progress(session, student_id, course_id)


@router.post("/mastery")
async def set_mastery(
    body: SetMasteryRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Manually set mastery for a core concept."""
    new_score = await set_manual_mastery(
        session,
        student_id=body.student_id,
        course_id=body.course_id,
        core_concept=body.core_concept,
        mastery=body.mastery,
    )
    return {"core_concept": body.core_concept, "mastery_score": new_score}


@router.get("/summaries/{course_id}")
async def list_summaries(course_id: str) -> list[dict[str, Any]]:
    """List available lecture summaries for a course."""
    prefix = f"summaries/course_{course_id}/"
    objects = await list_objects(prefix)
    summaries = []
    for obj in objects:
        try:
            data = await download_file(obj["key"])
            summaries.append(json.loads(data))
        except Exception:
            continue
    return summaries
```

- [ ] **Step 2: Register the router in `src/main.py`**

In `src/main.py`, inside the `_register_routes` function, add after the pipeline router import:

```python
    from src.api.quiz import router as quiz_router
```

And add after the `pipeline_router` include:

```python
    application.include_router(quiz_router, prefix="/api")
```

- [ ] **Step 3: Verify the server starts**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.api.quiz import router; print('routes:', [r.path for r in router.routes])"`

Expected: routes list with `/quiz`, `/quiz/submit`, `/flashcards`, etc.

- [ ] **Step 4: Commit**

```bash
git add src/api/quiz.py src/main.py
git commit -m "feat: add REST endpoints for quiz, flashcard, summary, and progress"
```

---

### Task 8: Wire Cognify Hook (`src/lib/cognify.py`)

**Files:**
- Modify: `src/lib/cognify.py`

- [ ] **Step 1: Replace the quiz generation hook**

In `src/lib/cognify.py`, replace lines 98–109:

```python
        # Auto-generate quizzes after cognify completes
        try:
            from src.lib.quiz import generate_quizzes_for_course

            await generate_quizzes_for_course(course_id)
            logger.info("quiz_generation_after_cognify_done", course_id=course_id)
        except Exception:
            logger.warning(
                "quiz_generation_after_cognify_failed",
                course_id=course_id,
                exc_info=True,
            )
```

With:

```python
        # Auto-generate all learning content (quizzes, flashcards, summaries)
        # after cognify completes. All content is regenerated on every run.
        # Future: use a concept manifest to diff and only regenerate changed concepts.
        try:
            from src.lib.content_generator import generate_all_for_course

            gen_result = await generate_all_for_course(course_id)
            logger.info(
                "content_generation_after_cognify_done",
                course_id=course_id,
                quizzes=gen_result.quizzes_generated,
                flashcards=gen_result.flashcards_generated,
                summaries=gen_result.summaries_generated,
            )
        except Exception:
            logger.warning(
                "content_generation_after_cognify_failed",
                course_id=course_id,
                exc_info=True,
            )
```

- [ ] **Step 2: Verify cognify still loads**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.lib.cognify import trigger_cognify; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/lib/cognify.py
git commit -m "feat: wire cognify hook to full content generator"
```

---

### Task 9: Update Academic Agent Tools (`src/agents/academic/tools.py`)

**Files:**
- Modify: `src/agents/academic/tools.py`

Replace old `quiz.py` imports with new modules. Update the `get_progress` and `take_quiz` tools.

- [ ] **Step 1: Replace imports**

Remove these lines (top of file):

```python
from src.lib.quiz import list_available_quizzes as _list_quizzes
from src.lib.quiz import load_quiz as _load_quiz
```

Replace with:

```python
from src.lib.s3 import list_objects as _list_s3_objects
```

- [ ] **Step 2: Update `get_progress` tool**

Replace the existing `get_progress` tool (lines 89–106) with:

```python
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
        obj["key"].rsplit("/", 1)[-1].replace(".json", "").replace("_", " ")
        for obj in quiz_objects
    ]
    return {
        "course_id": course_id,
        "core_concepts": concepts,
        "available_quizzes": available_quizzes,
    }
```

- [ ] **Step 3: Update `take_quiz` tool**

Replace the existing `take_quiz` tool (lines 109–139) with:

```python
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
```

- [ ] **Step 4: Verify tools load**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.agents.academic.tools import take_quiz, get_progress; print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/agents/academic/tools.py
git commit -m "refactor: update academic tools to use S3-based quiz serving"
```

---

### Task 10: Delete Old Quiz Module

**Files:**
- Delete: `src/lib/quiz.py`

- [ ] **Step 1: Verify no remaining imports of `src.lib.quiz`**

Run: `cd /mnt/data/Hackathons/campus-copilot && grep -r "from src.lib.quiz" src/ --include="*.py"`

Expected: No output (all imports have been migrated in previous tasks). If any remain, update them first.

- [ ] **Step 2: Delete the file**

```bash
rm src/lib/quiz.py
```

- [ ] **Step 3: Verify the app still imports cleanly**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run python -c "from src.main import app; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add -u src/lib/quiz.py
git commit -m "chore: remove old quiz.py, superseded by content_generator + quiz_serving"
```

---

### Task 11: Lint, Type-Check, and Final Verification

**Files:**
- All modified/created files

- [ ] **Step 1: Format**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run ruff format .`

Fix any formatting issues.

- [ ] **Step 2: Lint**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run ruff check --fix .`

Fix any remaining lint issues.

- [ ] **Step 3: Type check**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run mypy src/`

Fix any type errors. Expected: zero errors in `src/`.

- [ ] **Step 4: Run tests**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run pytest`

Fix any failures.

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address lint, type-check, and test issues"
```

- [ ] **Step 6: Verify full end-to-end check**

Run: `cd /mnt/data/Hackathons/campus-copilot && uv run ruff check . && uv run mypy src/ && uv run pytest`

Expected: All pass with zero errors.