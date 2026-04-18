"""Content generation module for quizzes, flashcards, and summaries.

This module runs after cognify to generate learning content from knowledge graph data.
Queries Cognee for concept/lecture data, calls Bedrock LLMs to generate content,
and uploads JSON files to S3.

NOTE: Currently regenerates all content on every cognify run (full S3 overwrite).
Future direction: use a concept manifest to enable incremental generation of only
changed concepts, reducing generation time and LLM costs.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from src.lib.bedrock import get_haiku_model_id, get_sonnet_model_id, invoke_model
from src.lib.memory import get_core_concepts, get_quiz_material, query_course_knowledge
from src.lib.s3 import upload_file
from src.models.learning import GenerationResult

logger = structlog.get_logger(__name__)

# ============================================================================
# LLM Prompts
# ============================================================================

QUIZ_SYSTEM_PROMPT = """You are an expert quiz question generator for university courses.

Your task:
- Generate 3-5 multiple-choice questions for the given core concept
- Each question must have exactly 4 options labeled A, B, C, D
- Exactly one option is correct
- Include plausible distractors (wrong answers that sound reasonable)
- Vary difficulty levels: easy, medium, hard
- Each question can test multiple leaf concepts from the provided material
- Provide a clear explanation for why the correct answer is right
- Focus on exam-relevant material and conceptual understanding

Output format:
Return ONLY a valid JSON array of question objects. No markdown, no code blocks, no extra text.
Each question object must have these exact fields:
{
  "core_concept": "string",
  "leaf_concepts": ["string"],
  "question": "string",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct": "A" | "B" | "C" | "D",
  "difficulty": "easy" | "medium" | "hard",
  "explanation": "string"
}"""

FLASHCARD_SYSTEM_PROMPT = """You are an expert flashcard creator for university courses.

Your task:
- Generate flashcards for the most important and exam-relevant leaf concepts
- Focus on concepts that form prerequisites for other topics
- Each flashcard has a front (question/prompt) and back (answer/explanation)
- Keep front concise and focused on a single idea
- Back should be clear and complete but not overly long
- Vary difficulty levels: easy, medium, hard
- Each card can cover multiple related leaf concepts

Output format:
Return ONLY a valid JSON array of flashcard objects. No markdown, no code blocks, no extra text.
Each flashcard object must have these exact fields:
{
  "core_concept": "string",
  "leaf_concepts": ["string"],
  "front": "string",
  "back": "string",
  "difficulty": "easy" | "medium" | "hard"
}"""

SUMMARY_SYSTEM_PROMPT = """You are an expert at creating concise lecture summaries \
for university students.

Your task:
- Write exactly 3 sentences that capture the essence of the lecture
- Extract 3-5 key takeaways (important facts, formulas, or concepts)
- Focus on what students need to remember for exams
- Be precise and technical where needed, but clear and readable

Output format:
Return ONLY a valid JSON object. No markdown, no code blocks, no extra text.
The object must have these exact fields:
{
  "summary": "string (exactly 3 sentences)",
  "key_takeaways": ["string", "string", ...]
}"""


# ============================================================================
# Helper Functions
# ============================================================================


def _safe_filename(name: str) -> str:
    """Convert a concept/lecture name to a safe S3 key component.

    Args:
        name: Original concept or lecture name.

    Returns:
        Alphanumeric string with hyphens/underscores, max 80 chars.
    """
    # Replace spaces and special chars with hyphens
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "-", name)
    # Collapse multiple hyphens
    safe = re.sub(r"-+", "-", safe)
    # Remove leading/trailing hyphens
    safe = safe.strip("-")
    # Truncate to 80 chars
    return safe[:80] if safe else "unnamed"


def _extract_json_from_llm_output(raw_output: str) -> str:
    """Extract JSON from LLM output that might contain markdown code blocks.

    Args:
        raw_output: Raw LLM output text.

    Returns:
        Cleaned JSON string.
    """
    # Remove markdown code blocks if present
    if "```json" in raw_output:
        match = re.search(r"```json\s*\n(.*?)\n```", raw_output, re.DOTALL)
        if match:
            return match.group(1).strip()
    elif "```" in raw_output:
        match = re.search(r"```\s*\n(.*?)\n```", raw_output, re.DOTALL)
        if match:
            return match.group(1).strip()
    return raw_output.strip()


async def _generate_quizzes_for_concept(
    course_id: str,
    core_concept: str,
    concept_data: dict[str, Any],
) -> str | None:
    """Generate quiz questions for a single core concept and upload to S3.

    Args:
        course_id: Course identifier.
        core_concept: Name of the core concept.
        concept_data: Raw concept data from Cognee.

    Returns:
        S3 key if successful, None if generation failed.
    """
    logger.info("generating_quiz", course_id=course_id, concept=core_concept)

    try:
        # Get quiz material from Cognee
        material = await get_quiz_material(course_id, core_concept)
        if not material:
            logger.warning("no_quiz_material", course_id=course_id, concept=core_concept)
            return None

        # Build user message with material
        material_text = "\n\n".join(material[:10])  # Limit to top 10 results
        user_message = f"""Core concept: {core_concept}

Leaf concepts and definitions:
{material_text}

Generate 3-5 multiple-choice questions for this core concept."""

        # Call Sonnet for quiz generation
        response = await invoke_model(
            model_id=get_sonnet_model_id(),
            messages=[{"role": "user", "content": user_message}],
            system=QUIZ_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.7,
        )

        # Extract and parse JSON
        raw_output = response["content"][0]["text"]
        json_str = _extract_json_from_llm_output(raw_output)
        questions = json.loads(json_str)

        # Add UUIDs to questions
        for q in questions:
            q["id"] = str(uuid4())
            q["type"] = "multiple_choice"
            # Ensure core_concept is set
            if "core_concept" not in q or not q["core_concept"]:
                q["core_concept"] = core_concept

        # Build quiz file
        quiz_file = {
            "core_concept": core_concept,
            "total_leaf_concepts": len(material),
            "questions": questions,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # Upload to S3
        safe_name = _safe_filename(core_concept)
        s3_key = f"quizzes/course_{course_id}/{safe_name}.json"
        json_bytes = json.dumps(quiz_file, indent=2).encode("utf-8")
        await upload_file(s3_key, json_bytes, "application/json")

        logger.info(
            "quiz_generated",
            course_id=course_id,
            concept=core_concept,
            questions=len(questions),
            s3_key=s3_key,
        )
        return s3_key

    except json.JSONDecodeError:
        logger.error(
            "quiz_json_parse_failed",
            course_id=course_id,
            concept=core_concept,
            exc_info=True,
        )
        return None
    except Exception:
        logger.error(
            "quiz_generation_failed",
            course_id=course_id,
            concept=core_concept,
            exc_info=True,
        )
        return None


async def _generate_flashcards_for_concept(
    course_id: str,
    core_concept: str,
    concept_data: dict[str, Any],
) -> str | None:
    """Generate flashcards for a single core concept and upload to S3.

    Args:
        course_id: Course identifier.
        core_concept: Name of the core concept.
        concept_data: Raw concept data from Cognee.

    Returns:
        S3 key if successful, None if generation failed.
    """
    logger.info("generating_flashcards", course_id=course_id, concept=core_concept)

    try:
        # Get quiz material (same source as quizzes)
        material = await get_quiz_material(course_id, core_concept)
        if not material:
            logger.warning("no_flashcard_material", course_id=course_id, concept=core_concept)
            return None

        # Build user message with material
        material_text = "\n\n".join(material[:10])  # Limit to top 10 results
        user_message = f"""Core concept: {core_concept}

Leaf concepts and definitions:
{material_text}

Generate flashcards for the most important and exam-relevant leaf concepts."""

        # Call Haiku for flashcard generation (speed matters)
        response = await invoke_model(
            model_id=get_haiku_model_id(),
            messages=[{"role": "user", "content": user_message}],
            system=FLASHCARD_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.7,
        )

        # Extract and parse JSON
        raw_output = response["content"][0]["text"]
        json_str = _extract_json_from_llm_output(raw_output)
        cards = json.loads(json_str)

        # Add UUIDs to cards
        for card in cards:
            card["id"] = str(uuid4())
            # Ensure core_concept is set
            if "core_concept" not in card or not card["core_concept"]:
                card["core_concept"] = core_concept

        # Build flashcard file
        flashcard_file = {
            "core_concept": core_concept,
            "total_leaf_concepts": len(material),
            "cards": cards,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # Upload to S3
        safe_name = _safe_filename(core_concept)
        s3_key = f"flashcards/course_{course_id}/{safe_name}.json"
        json_bytes = json.dumps(flashcard_file, indent=2).encode("utf-8")
        await upload_file(s3_key, json_bytes, "application/json")

        logger.info(
            "flashcards_generated",
            course_id=course_id,
            concept=core_concept,
            cards=len(cards),
            s3_key=s3_key,
        )
        return s3_key

    except json.JSONDecodeError:
        logger.error(
            "flashcard_json_parse_failed",
            course_id=course_id,
            concept=core_concept,
            exc_info=True,
        )
        return None
    except Exception:
        logger.error(
            "flashcard_generation_failed",
            course_id=course_id,
            concept=core_concept,
            exc_info=True,
        )
        return None


async def _generate_summary_for_lecture(
    course_id: str,
    lecture_name: str,
) -> str | None:
    """Generate a summary for a single lecture and upload to S3.

    Args:
        course_id: Course identifier.
        lecture_name: Name or identifier of the lecture.

    Returns:
        S3 key if successful, None if generation failed.
    """
    logger.info("generating_summary", course_id=course_id, lecture=lecture_name)

    try:
        # Query Cognee for lecture content
        query = (
            f"Summarize the content covered in lecture '{lecture_name}'. "
            f"Include key concepts, definitions, and formulas."
        )
        results = await query_course_knowledge(course_id, query)

        if not results:
            logger.warning("no_lecture_content", course_id=course_id, lecture=lecture_name)
            return None

        # Build user message with lecture content
        content_text = "\n\n".join(results[:5])  # Limit to top 5 results
        user_message = f"""Lecture: {lecture_name}

Content:
{content_text}

Generate a concise summary with exactly 3 sentences and 3-5 key takeaways."""

        # Call Sonnet for summary generation
        response = await invoke_model(
            model_id=get_sonnet_model_id(),
            messages=[{"role": "user", "content": user_message}],
            system=SUMMARY_SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.5,
        )

        # Extract and parse JSON
        raw_output = response["content"][0]["text"]
        json_str = _extract_json_from_llm_output(raw_output)
        summary_data = json.loads(json_str)

        # Build summary file
        summary_file = {
            "lecture": lecture_name,
            "summary": summary_data["summary"],
            "key_takeaways": summary_data["key_takeaways"],
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # Upload to S3
        safe_name = _safe_filename(lecture_name)
        s3_key = f"summaries/course_{course_id}/{safe_name}.json"
        json_bytes = json.dumps(summary_file, indent=2).encode("utf-8")
        await upload_file(s3_key, json_bytes, "application/json")

        logger.info(
            "summary_generated",
            course_id=course_id,
            lecture=lecture_name,
            s3_key=s3_key,
        )
        return s3_key

    except json.JSONDecodeError:
        logger.error(
            "summary_json_parse_failed",
            course_id=course_id,
            lecture=lecture_name,
            exc_info=True,
        )
        return None
    except Exception:
        logger.error(
            "summary_generation_failed",
            course_id=course_id,
            lecture=lecture_name,
            exc_info=True,
        )
        return None


# ============================================================================
# Public API
# ============================================================================


async def generate_all_for_course(course_id: str) -> GenerationResult:
    """Generate all learning content (quizzes, flashcards, summaries) for a course.

    This is the main entry point called after cognify completes. It queries Cognee
    for concept and lecture data, generates content using Bedrock LLMs, and uploads
    JSON files to S3.

    Args:
        course_id: Course identifier.

    Returns:
        GenerationResult with counts of generated content and any errors.
    """
    logger.info("content_generation_start", course_id=course_id)

    errors: list[str] = []
    quizzes_generated = 0
    flashcards_generated = 0
    summaries_generated = 0

    try:
        # Phase 1: Get core concepts from Cognee
        concepts = await get_core_concepts(course_id)
        logger.info("concepts_retrieved", course_id=course_id, count=len(concepts))

        if not concepts:
            errors.append("No core concepts found in knowledge graph")
            return GenerationResult(
                course_id=course_id,
                quizzes_generated=0,
                flashcards_generated=0,
                summaries_generated=0,
                errors=errors,
            )

        # Phase 2: Generate quizzes and flashcards for each core concept
        for concept_data in concepts:
            concept_name = concept_data["name"]

            # Generate quiz
            quiz_key = await _generate_quizzes_for_concept(course_id, concept_name, concept_data)
            if quiz_key:
                quizzes_generated += 1
            else:
                errors.append(f"Failed to generate quiz for concept: {concept_name}")

            # Generate flashcards
            flashcard_key = await _generate_flashcards_for_concept(
                course_id, concept_name, concept_data
            )
            if flashcard_key:
                flashcards_generated += 1
            else:
                errors.append(f"Failed to generate flashcards for concept: {concept_name}")

        # Phase 3: Generate summaries for lectures
        # Query Cognee for lecture list
        lecture_query = (
            "List all lectures or chapters covered in this course. "
            "Return just the lecture names or chapter numbers."
        )
        lecture_results = await query_course_knowledge(course_id, lecture_query)

        if lecture_results:
            # Extract lecture names (simple heuristic: take first 200 chars of each result)
            lecture_names = [r[:200].strip() for r in lecture_results[:10]]

            for lecture_name in lecture_names:
                if not lecture_name or len(lecture_name) < 5:
                    continue

                summary_key = await _generate_summary_for_lecture(course_id, lecture_name)
                if summary_key:
                    summaries_generated += 1
                else:
                    errors.append(f"Failed to generate summary for lecture: {lecture_name}")
        else:
            logger.warning("no_lectures_found", course_id=course_id)
            errors.append("No lectures found for summary generation")

    except Exception as exc:
        logger.error("content_generation_failed", course_id=course_id, exc_info=True)
        errors.append(f"Content generation failed: {exc}")

    result = GenerationResult(
        course_id=course_id,
        quizzes_generated=quizzes_generated,
        flashcards_generated=flashcards_generated,
        summaries_generated=summaries_generated,
        errors=errors,
    )

    logger.info(
        "content_generation_complete",
        course_id=course_id,
        quizzes=quizzes_generated,
        flashcards=flashcards_generated,
        summaries=summaries_generated,
        errors=len(errors),
    )

    return result
