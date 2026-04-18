"""Quiz generation pipeline — generates MCQs from Cognee knowledge graph, stores as local JSON."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from src.config import get_settings
from src.lib.bedrock import get_sonnet_model_id, invoke_model
from src.lib.memory import get_core_concepts, get_quiz_material

logger = structlog.get_logger(__name__)

QUIZ_GENERATION_SYSTEM = """\
You are a quiz generator for university courses. Given leaf concepts with definitions, \
generate multiple-choice questions that test understanding.

Rules:
- 3-5 questions per leaf concept
- Each question has exactly 4 options (A, B, C, D)
- Exactly one correct answer
- Vary difficulty: easy, medium, hard
- Include a brief explanation for the correct answer
- Questions should test understanding, not just memorization

Respond with valid JSON only. No markdown, no code fences. Use this exact format:
[
  {
    "leaf_concept": "concept name",
    "question": "the question text",
    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
    "correct": "A",
    "difficulty": "medium",
    "explanation": "brief explanation"
  }
]
"""


def _quiz_dir(course_id: str) -> Path:
    """Get the local quiz storage directory for a course."""
    settings = get_settings()
    base = Path(settings.quiz_storage_dir)
    course_dir = base / f"course_{course_id}"
    course_dir.mkdir(parents=True, exist_ok=True)
    return course_dir


async def generate_quiz_for_concept(
    course_id: str,
    core_concept: str,
) -> dict[str, Any]:
    """Generate quiz questions for a single core concept.

    Args:
        course_id: Course identifier.
        core_concept: The core concept to generate questions for.

    Returns:
        Quiz data dict matching the schema from COGNEE_REQUIREMENTS.md.
    """
    logger.info("quiz_generate_start", course_id=course_id, concept=core_concept)

    leaf_materials = await get_quiz_material(course_id, core_concept)

    if not leaf_materials:
        logger.warning("quiz_no_material", course_id=course_id, concept=core_concept)
        return {"core_concept": core_concept, "questions": [], "error": "No material found"}

    material_text = "\n\n".join(leaf_materials)
    prompt = (
        f"Core concept: {core_concept}\n\n"
        f"Leaf concepts and definitions:\n{material_text}\n\n"
        f"Generate quiz questions for these leaf concepts."
    )

    response = await invoke_model(
        model_id=get_sonnet_model_id(),
        messages=[{"role": "user", "content": prompt}],
        system=QUIZ_GENERATION_SYSTEM,
        max_tokens=4096,
        temperature=0.5,
    )

    raw_text = response.get("content", [{}])[0].get("text", "[]")
    try:
        questions_raw = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.error("quiz_json_parse_failed", course_id=course_id, concept=core_concept)
        questions_raw = []

    questions = []
    for q in questions_raw:
        questions.append(
            {
                "id": str(uuid4()),
                "leaf_concept": q.get("leaf_concept", ""),
                "question": q.get("question", ""),
                "type": "multiple_choice",
                "options": q.get("options", []),
                "correct": q.get("correct", ""),
                "difficulty": q.get("difficulty", "medium"),
                "explanation": q.get("explanation", ""),
            }
        )

    quiz_data: dict[str, Any] = {
        "core_concept": core_concept,
        "questions": questions,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_lectures": [],
    }

    quiz_path = _quiz_dir(course_id) / f"{_safe_filename(core_concept)}.json"
    quiz_path.write_text(json.dumps(quiz_data, indent=2))
    logger.info(
        "quiz_generated",
        course_id=course_id,
        concept=core_concept,
        question_count=len(questions),
        path=str(quiz_path),
    )

    return quiz_data


def _safe_filename(name: str) -> str:
    """Convert a concept name to a safe filename."""
    return "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip().replace(" ", "_")


async def generate_quizzes_for_course(course_id: str) -> list[dict[str, Any]]:
    """Generate quizzes for all core concepts in a course.

    Args:
        course_id: Course identifier.

    Returns:
        List of quiz data dicts, one per core concept.
    """
    logger.info("quiz_generate_all_start", course_id=course_id)
    concepts = await get_core_concepts(course_id)

    results: list[dict[str, Any]] = []
    for concept in concepts:
        concept_name = concept.get("name", "")
        if not concept_name:
            continue
        try:
            quiz = await generate_quiz_for_concept(course_id, concept_name)
            results.append(quiz)
        except Exception:
            logger.warning(
                "quiz_generate_concept_failed",
                course_id=course_id,
                concept=concept_name,
                exc_info=True,
            )

    logger.info(
        "quiz_generate_all_done",
        course_id=course_id,
        total=len(results),
    )
    return results


def load_quiz(course_id: str, core_concept: str) -> dict[str, Any] | None:
    """Load a stored quiz from local JSON.

    Args:
        course_id: Course identifier.
        core_concept: The core concept name.

    Returns:
        Quiz data dict or None if not found.
    """
    quiz_path = _quiz_dir(course_id) / f"{_safe_filename(core_concept)}.json"
    if not quiz_path.exists():
        return None
    return json.loads(quiz_path.read_text())  # type: ignore[no-any-return]


def list_available_quizzes(course_id: str) -> list[str]:
    """List all available quiz topics for a course.

    Args:
        course_id: Course identifier.

    Returns:
        List of core concept names with generated quizzes.
    """
    quiz_dir = _quiz_dir(course_id)
    return [p.stem.replace("_", " ") for p in quiz_dir.glob("*.json")]
