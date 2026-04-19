"""Quiz and flashcard serving with personalization and mastery updates.

This module reads quiz/flashcard content from S3, assembles personalized sessions
based on student progress, scores submissions, and updates mastery scores in Postgres.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from src.exceptions import QuizNotFoundError
from src.lib.content_generator import _safe_filename
from src.lib.mastery import (
    average_flashcard_rating,
    compute_leaf_coverage,
    compute_mastery_score,
    update_signal_moving_average,
)
from src.lib.s3 import download_file, list_objects
from src.models.learning import (
    FlashcardFile,
    FlashcardItem,
    FlashcardResult,
    FlashcardSession,
    FlashcardSubmission,
    QuizFile,
    QuizQuestion,
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

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ============================================================================
# S3 Helpers (Private)
# ============================================================================


async def _load_quiz_file(course_id: str, concept: str) -> QuizFile | None:
    """Download and parse quiz JSON from S3.

    Args:
        course_id: Course identifier.
        concept: Core concept name.

    Returns:
        Parsed QuizFile if found, None otherwise.
    """
    try:
        safe_name = _safe_filename(concept)
        s3_key = f"quizzes/course_{course_id}/{safe_name}.json"
        data = await download_file(s3_key)
        quiz_dict = json.loads(data.decode("utf-8"))
        return QuizFile(**quiz_dict)
    except Exception:
        logger.warning("quiz_file_not_found", course_id=course_id, concept=concept)
        return None


async def _load_flashcard_file(course_id: str, concept: str) -> FlashcardFile | None:
    """Download and parse flashcard JSON from S3.

    Args:
        course_id: Course identifier.
        concept: Core concept name.

    Returns:
        Parsed FlashcardFile if found, None otherwise.
    """
    try:
        safe_name = _safe_filename(concept)
        s3_key = f"flashcards/course_{course_id}/{safe_name}.json"
        data = await download_file(s3_key)
        flashcard_dict = json.loads(data.decode("utf-8"))
        return FlashcardFile(**flashcard_dict)
    except Exception:
        logger.warning("flashcard_file_not_found", course_id=course_id, concept=concept)
        return None


async def _list_available_concepts(course_id: str, content_type: str) -> list[str]:
    """List concepts with generated content on S3.

    Args:
        course_id: Course identifier.
        content_type: "quizzes" or "flashcards".

    Returns:
        List of core concept names that have content available.
    """
    try:
        prefix = f"{content_type}/course_{course_id}/"
        objects = await list_objects(prefix)

        concepts: list[str] = []
        for obj in objects:
            # Extract concept from key: "quizzes/course_123/concept-name.json"
            key = obj["key"]
            if key.endswith(".json"):
                filename = key.split("/")[-1][:-5]  # Remove .json
                concepts.append(filename)

        logger.info(
            "concepts_listed",
            course_id=course_id,
            content_type=content_type,
            count=len(concepts),
        )
        return concepts
    except Exception:
        logger.error(
            "list_concepts_failed",
            course_id=course_id,
            content_type=content_type,
            exc_info=True,
        )
        return []


async def _get_seen_question_ids(
    session: AsyncSession,
    student_id: str,
    course_id: str,
) -> set[str]:
    """Query QuizAttemptRow for already-seen question IDs.

    Args:
        session: SQLAlchemy async session.
        student_id: Student identifier.
        course_id: Course identifier.

    Returns:
        Set of question IDs the student has already attempted.
    """
    result = await session.execute(
        select(QuizAttemptRow.question_ids).where(
            QuizAttemptRow.student_id == student_id,
            QuizAttemptRow.course_id == course_id,
        )
    )
    rows = result.scalars().all()

    seen_ids: set[str] = set()
    for question_ids in rows:
        seen_ids.update(question_ids)

    return seen_ids


async def _get_seen_card_ids(
    session: AsyncSession,
    student_id: str,
    course_id: str,
) -> set[str]:
    """Query FlashcardAttemptRow for already-seen card IDs.

    Args:
        session: SQLAlchemy async session.
        student_id: Student identifier.
        course_id: Course identifier.

    Returns:
        Set of card IDs the student has already reviewed.
    """
    result = await session.execute(
        select(FlashcardAttemptRow.card_ratings).where(
            FlashcardAttemptRow.student_id == student_id,
            FlashcardAttemptRow.course_id == course_id,
        )
    )
    rows = result.scalars().all()

    seen_ids: set[str] = set()
    for card_ratings in rows:
        seen_ids.update(card_ratings.keys())

    return seen_ids


async def _pick_weakest_concepts(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    available: list[str],
    limit: int,
) -> list[str]:
    """Pick concepts with lowest mastery scores.

    Args:
        session: SQLAlchemy async session.
        student_id: Student identifier.
        course_id: Course identifier.
        available: List of available concept names (safe filenames).
        limit: Maximum number of concepts to pick.

    Returns:
        List of up to `limit` concept names, sorted by ascending mastery.
    """
    if not available:
        return []

    result = await session.execute(
        select(StudentConceptProgressRow).where(
            StudentConceptProgressRow.student_id == student_id,
            StudentConceptProgressRow.course_id == course_id,
        )
    )
    progress_rows = result.scalars().all()

    # Build mapping from safe filename to mastery score
    concept_scores: dict[str, float] = {}
    for row in progress_rows:
        safe_name = _safe_filename(row.core_concept)
        if safe_name in available:
            concept_scores[safe_name] = row.mastery_score

    # Assign default score 0.0 to concepts with no progress
    for concept in available:
        if concept not in concept_scores:
            concept_scores[concept] = 0.0

    # Sort by mastery ascending and take top `limit`
    sorted_concepts = sorted(concept_scores.items(), key=lambda x: x[1])
    weakest = [concept for concept, _ in sorted_concepts[:limit]]

    logger.info(
        "weakest_concepts_picked",
        student_id=student_id,
        course_id=course_id,
        weakest=weakest,
    )
    return weakest


# ============================================================================
# Serving (Public)
# ============================================================================


async def serve_quiz(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    num_questions: int,
    core_concepts: list[str],
) -> QuizSession:
    """Assemble a personalized quiz session for the student.

    Args:
        session: SQLAlchemy async session.
        student_id: Student identifier.
        course_id: Course identifier.
        num_questions: Number of questions to serve.
        core_concepts: List of core concept names (empty for auto-pick).

    Returns:
        QuizSession with personalized questions (no correct answers).

    Raises:
        QuizNotFoundError: If no quiz content is available.
    """
    logger.info(
        "serve_quiz_start",
        student_id=student_id,
        course_id=course_id,
        num_questions=num_questions,
        requested_concepts=len(core_concepts),
    )

    # If no concepts specified, load ALL available concepts for max diversity
    if not core_concepts:
        available = await _list_available_concepts(course_id, "quizzes")
        random.shuffle(available)
        core_concepts_safe = available
    else:
        core_concepts_safe = [_safe_filename(c) for c in core_concepts]

    if not core_concepts_safe:
        raise QuizNotFoundError(f"No quiz content available for course {course_id}")

    # Load quiz files from S3 — gather from ALL concepts for diversity
    all_questions: list[tuple[str, QuizFile, QuizQuestion]] = []
    for safe_concept in core_concepts_safe:
        quiz_file = await _load_quiz_file(course_id, safe_concept)
        if quiz_file:
            for question in quiz_file.questions:
                all_questions.append((safe_concept, quiz_file, question))

    if not all_questions:
        raise QuizNotFoundError(f"Failed to load quiz content for course {course_id}")

    # Get seen question IDs
    seen_ids = await _get_seen_question_ids(session, student_id, course_id)

    # Filter out seen questions
    unseen_questions = [
        (safe_concept, quiz_file, q)
        for safe_concept, quiz_file, q in all_questions
        if q.id not in seen_ids
    ]

    # If all filtered out, allow re-attempts
    if not unseen_questions:
        logger.info(
            "all_questions_seen",
            student_id=student_id,
            course_id=course_id,
            total=len(all_questions),
        )
        unseen_questions = all_questions

    # Shuffle and slice to num_questions
    random.shuffle(unseen_questions)
    selected = unseen_questions[:num_questions]

    questions_served: list[QuizQuestionServed] = []
    for _, _, question in selected:
        questions_served.append(
            QuizQuestionServed(
                id=question.id,
                core_concept=question.core_concept,
                leaf_concepts=question.leaf_concepts,
                question=question.question,
                options=question.options,
                difficulty=question.difficulty,
                correct=question.correct,
                explanation=question.explanation,
            )
        )

    # Extract unique core concepts from selected questions
    selected_concepts = list({q.core_concept for _, _, q in selected})

    logger.info(
        "serve_quiz_complete",
        student_id=student_id,
        course_id=course_id,
        served=len(questions_served),
        total_available=len(all_questions),
    )

    return QuizSession(
        course_id=course_id,
        core_concepts=selected_concepts,
        questions=questions_served,
        total_available=len(all_questions),
    )


async def serve_flashcards(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    num_cards: int,
    core_concepts: list[str],
) -> FlashcardSession:
    """Assemble a personalized flashcard session for the student.

    Args:
        session: SQLAlchemy async session.
        student_id: Student identifier.
        course_id: Course identifier.
        num_cards: Number of cards to serve.
        core_concepts: List of core concept names (empty for auto-pick).

    Returns:
        FlashcardSession with personalized cards.

    Raises:
        QuizNotFoundError: If no flashcard content is available.
    """
    logger.info(
        "serve_flashcards_start",
        student_id=student_id,
        course_id=course_id,
        num_cards=num_cards,
        requested_concepts=len(core_concepts),
    )

    # If no concepts specified, load ALL for max diversity
    if not core_concepts:
        available = await _list_available_concepts(course_id, "flashcards")
        random.shuffle(available)
        core_concepts_safe = available
    else:
        core_concepts_safe = [_safe_filename(c) for c in core_concepts]

    if not core_concepts_safe:
        raise QuizNotFoundError(f"No flashcard content available for course {course_id}")

    # Load flashcard files from S3
    all_cards: list[tuple[str, FlashcardFile, FlashcardItem]] = []
    for safe_concept in core_concepts_safe:
        flashcard_file = await _load_flashcard_file(course_id, safe_concept)
        if flashcard_file:
            for card in flashcard_file.cards:
                all_cards.append((safe_concept, flashcard_file, card))

    if not all_cards:
        raise QuizNotFoundError(f"Failed to load flashcard content for course {course_id}")

    # Get seen card IDs
    seen_ids = await _get_seen_card_ids(session, student_id, course_id)

    # Filter out seen cards
    unseen_cards = [
        (safe_concept, flashcard_file, card)
        for safe_concept, flashcard_file, card in all_cards
        if card.id not in seen_ids
    ]

    # If all filtered out, allow re-attempts
    if not unseen_cards:
        logger.info(
            "all_cards_seen",
            student_id=student_id,
            course_id=course_id,
            total=len(all_cards),
        )
        unseen_cards = all_cards

    # Shuffle and slice to num_cards
    random.shuffle(unseen_cards)
    selected = unseen_cards[:num_cards]

    # Build card list
    cards_served: list[FlashcardItem] = [card for _, _, card in selected]

    # Extract unique core concepts from selected cards
    selected_concepts = list({card.core_concept for _, _, card in selected})

    logger.info(
        "serve_flashcards_complete",
        student_id=student_id,
        course_id=course_id,
        served=len(cards_served),
        total_available=len(all_cards),
    )

    return FlashcardSession(
        course_id=course_id,
        core_concepts=selected_concepts,
        cards=cards_served,
        total_available=len(all_cards),
    )


# ============================================================================
# Scoring (Public)
# ============================================================================


async def score_quiz(
    session: AsyncSession,
    submission: QuizSubmission,
) -> QuizResult:
    """Score a quiz submission and update mastery.

    Args:
        session: SQLAlchemy async session.
        submission: Student's quiz submission with answers.

    Returns:
        QuizResult with scores and mastery updates.
    """
    student_id = submission.student_id
    course_id = submission.course_id

    logger.info(
        "score_quiz_start",
        student_id=student_id,
        course_id=course_id,
        answers=len(submission.answers),
    )

    # Build mapping from question_id to selected answer
    answer_map = {ans.question_id: ans.selected for ans in submission.answers}

    # Load quiz files to look up correct answers
    # Group answers by core concept first
    question_map: dict[str, dict[str, Any]] = {}  # qid -> {correct, concept, leaf_concepts}
    concept_questions: dict[str, list[str]] = {}  # concept -> [qids]
    concept_leaf_concepts: dict[str, list[str]] = {}  # concept -> [leaf concepts]
    concept_total_leaf: dict[str, int] = {}  # concept -> total leaf count

    # We need to load quiz files to get correct answers
    # Try to infer concepts from question IDs by loading available quiz files
    available_concepts = await _list_available_concepts(course_id, "quizzes")

    for safe_concept in available_concepts:
        quiz_file = await _load_quiz_file(course_id, safe_concept)
        if not quiz_file:
            continue

        for question in quiz_file.questions:
            if question.id in answer_map:
                question_map[question.id] = {
                    "correct": question.correct,
                    "core_concept": question.core_concept,
                    "leaf_concepts": question.leaf_concepts,
                }

                concept = question.core_concept
                if concept not in concept_questions:
                    concept_questions[concept] = []
                    concept_leaf_concepts[concept] = []
                    concept_total_leaf[concept] = quiz_file.total_leaf_concepts

                concept_questions[concept].append(question.id)
                concept_leaf_concepts[concept].extend(question.leaf_concepts)

    # Score each answer
    correct_count = 0
    total_count = len(submission.answers)
    per_concept: dict[str, float] = {}

    for qid, selected in answer_map.items():
        if qid not in question_map:
            logger.warning("question_not_found", question_id=qid)
            continue

        correct_answer = question_map[qid]["correct"]
        if selected == correct_answer:
            correct_count += 1

    # Compute per-concept scores
    for concept, qids in concept_questions.items():
        concept_correct = sum(
            1 for qid in qids if answer_map.get(qid) == question_map.get(qid, {}).get("correct")
        )
        concept_total = len(qids)
        per_concept[concept] = concept_correct / concept_total if concept_total > 0 else 0.0

    overall_score = correct_count / total_count if total_count > 0 else 0.0

    # Write QuizAttemptRow
    attempt = QuizAttemptRow(
        student_id=student_id,
        course_id=course_id,
        core_concepts=list(concept_questions.keys()),
        question_ids=list(answer_map.keys()),
        answers={
            qid: {
                "selected": selected,
                "correct": question_map.get(qid, {}).get("correct", ""),
                "is_correct": str(selected == question_map.get(qid, {}).get("correct")),
            }
            for qid, selected in answer_map.items()
        },
        score=overall_score,
    )
    session.add(attempt)

    # Update mastery for each concept
    mastery_updates: dict[str, float] = {}
    for concept, score in per_concept.items():
        # Compute leaf coverage
        served_leaf = concept_leaf_concepts.get(concept, [])
        total_leaf = concept_total_leaf.get(concept, 0)
        coverage = compute_leaf_coverage(served_leaf, total_leaf)

        # Update mastery
        new_mastery = await _update_concept_mastery(
            session,
            student_id,
            course_id,
            concept,
            signal="quiz",
            new_value=score,
            coverage=coverage,
            passed=score >= 0.6,
        )
        mastery_updates[concept] = new_mastery

    # Commit transaction
    await session.commit()

    logger.info(
        "score_quiz_complete",
        student_id=student_id,
        course_id=course_id,
        score=overall_score,
        correct=correct_count,
        total=total_count,
    )

    return QuizResult(
        score=overall_score,
        total=total_count,
        correct=correct_count,
        per_concept=per_concept,
        mastery_updates=mastery_updates,
    )


async def score_flashcards(
    session: AsyncSession,
    submission: FlashcardSubmission,
) -> FlashcardResult:
    """Score a flashcard submission and update mastery.

    Args:
        session: SQLAlchemy async session.
        submission: Student's flashcard ratings.

    Returns:
        FlashcardResult with mastery updates.
    """
    student_id = submission.student_id
    course_id = submission.course_id

    logger.info(
        "score_flashcards_start",
        student_id=student_id,
        course_id=course_id,
        ratings=len(submission.ratings),
    )

    # Build mapping from card_id to rating
    rating_map = {rating.card_id: rating.rating for rating in submission.ratings}

    # Load flashcard files to group by concept
    card_map: dict[str, dict[str, object]] = {}  # card_id -> {concept, leaf_concepts}
    concept_cards: dict[str, list[str]] = {}  # concept -> [card_ids]
    concept_leaf_concepts: dict[str, list[str]] = {}  # concept -> [leaf concepts]
    concept_total_leaf: dict[str, int] = {}  # concept -> total leaf count

    available_concepts = await _list_available_concepts(course_id, "flashcards")

    for safe_concept in available_concepts:
        flashcard_file = await _load_flashcard_file(course_id, safe_concept)
        if not flashcard_file:
            continue

        for card in flashcard_file.cards:
            if card.id in rating_map:
                card_map[card.id] = {
                    "core_concept": card.core_concept,
                    "leaf_concepts": card.leaf_concepts,
                }

                concept = card.core_concept
                if concept not in concept_cards:
                    concept_cards[concept] = []
                    concept_leaf_concepts[concept] = []
                    concept_total_leaf[concept] = flashcard_file.total_leaf_concepts

                concept_cards[concept].append(card.id)
                concept_leaf_concepts[concept].extend(card.leaf_concepts)

    # Group ratings by concept
    concept_ratings: dict[str, dict[str, str]] = {}
    for card_id, rating in rating_map.items():
        if card_id not in card_map:
            logger.warning("card_not_found", card_id=card_id)
            continue

        rated_concept = str(card_map[card_id]["core_concept"])
        if rated_concept not in concept_ratings:
            concept_ratings[rated_concept] = {}
        concept_ratings[rated_concept][card_id] = rating

    # Write FlashcardAttemptRow
    attempt = FlashcardAttemptRow(
        student_id=student_id,
        course_id=course_id,
        core_concepts=list(concept_cards.keys()),
        card_ratings=rating_map,
    )
    session.add(attempt)

    # Compute per-concept scores and update mastery
    per_concept: dict[str, float] = {}
    mastery_updates: dict[str, float] = {}

    for concept, ratings in concept_ratings.items():
        # Average flashcard ratings
        score = average_flashcard_rating(ratings)
        per_concept[concept] = score

        # Compute leaf coverage
        served_leaf = concept_leaf_concepts.get(concept, [])
        total_leaf = concept_total_leaf.get(concept, 0)
        coverage = compute_leaf_coverage(served_leaf, total_leaf)

        # Update mastery
        new_mastery = await _update_concept_mastery(
            session,
            student_id,
            course_id,
            concept,
            signal="flashcard",
            new_value=score,
            coverage=coverage,
        )
        mastery_updates[concept] = new_mastery

    # Commit transaction
    await session.commit()

    logger.info(
        "score_flashcards_complete",
        student_id=student_id,
        course_id=course_id,
        concepts=len(mastery_updates),
    )

    return FlashcardResult(
        per_concept=per_concept,
        mastery_updates=mastery_updates,
    )


# ============================================================================
# Mastery (Public)
# ============================================================================


async def _update_concept_mastery(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    core_concept: str,
    signal: str,
    new_value: float,
    coverage: float,
    passed: bool | None = None,
) -> float:
    """Upsert StudentConceptProgressRow and update mastery score.

    Args:
        session: SQLAlchemy async session.
        student_id: Student identifier.
        course_id: Course identifier.
        core_concept: Core concept name.
        signal: Mastery signal name ("quiz", "flashcard", etc.).
        new_value: New signal value [0.0, 1.0].
        coverage: Leaf concept coverage ratio.
        passed: Whether the quiz was passed (score >= 0.6), if applicable.

    Returns:
        Updated mastery score.
    """
    # Find or create progress row
    result = await session.execute(
        select(StudentConceptProgressRow).where(
            StudentConceptProgressRow.student_id == student_id,
            StudentConceptProgressRow.course_id == course_id,
            StudentConceptProgressRow.core_concept == core_concept,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        # Create new row
        row = StudentConceptProgressRow(
            student_id=student_id,
            course_id=course_id,
            core_concept=core_concept,
            mastery_score=0.0,
            mastery_sources={},
            exercises_completed=0,
            quizzes_taken=0,
            quizzes_passed=0,
            last_activity=None,
            manual_mastery=None,
        )
        session.add(row)

    # Update signal in mastery_sources
    current_signal_value = row.mastery_sources.get(signal, 0.0)
    updated_signal = update_signal_moving_average(
        current_signal_value,
        new_value,
        coverage,
    )
    row.mastery_sources[signal] = updated_signal

    # Increment counters
    if signal == "quiz":
        row.quizzes_taken += 1
        if passed:
            row.quizzes_passed += 1
    elif signal == "exercise":
        row.exercises_completed += 1

    # Update last activity timestamp
    row.last_activity = datetime.now(UTC)

    # Check if there was activity since manual override
    has_activity_since_override = row.manual_mastery is not None

    # Recompute mastery score
    row.mastery_score = compute_mastery_score(
        row.mastery_sources,
        row.manual_mastery,
        has_activity_since_override,
    )

    logger.info(
        "mastery_updated",
        student_id=student_id,
        course_id=course_id,
        concept=core_concept,
        signal=signal,
        new_value=new_value,
        coverage=coverage,
        mastery_score=row.mastery_score,
    )

    return row.mastery_score


async def get_course_progress(
    session: AsyncSession,
    student_id: str,
    course_id: str,
) -> dict[str, object]:
    """Get all concept progress and overall mastery for a course.

    Args:
        session: SQLAlchemy async session.
        student_id: Student identifier.
        course_id: Course identifier.

    Returns:
        Dict with course_id, overall_mastery, and list of concept progress.
    """
    result = await session.execute(
        select(StudentConceptProgressRow).where(
            StudentConceptProgressRow.student_id == student_id,
            StudentConceptProgressRow.course_id == course_id,
        )
    )
    rows = result.scalars().all()

    concepts = [
        {
            "core_concept": row.core_concept,
            "mastery_score": row.mastery_score,
            "mastery_sources": row.mastery_sources,
            "manual_mastery": row.manual_mastery,
            "quizzes_taken": row.quizzes_taken,
            "quizzes_passed": row.quizzes_passed,
            "exercises_completed": row.exercises_completed,
        }
        for row in rows
    ]

    # Compute overall mastery as average of all concepts
    mastery_scores = [row.mastery_score for row in rows]
    overall_mastery = sum(mastery_scores) / len(mastery_scores) if mastery_scores else 0.0

    return {
        "course_id": course_id,
        "overall_mastery": overall_mastery,
        "concepts": concepts,
    }


async def set_manual_mastery(
    session: AsyncSession,
    student_id: str,
    course_id: str,
    core_concept: str,
    mastery: float,
) -> float:
    """Manually set mastery score for a concept.

    Args:
        session: SQLAlchemy async session.
        student_id: Student identifier.
        course_id: Course identifier.
        core_concept: Core concept name.
        mastery: Manual mastery score [0.0, 1.0].

    Returns:
        Updated mastery score.
    """
    result = await session.execute(
        select(StudentConceptProgressRow).where(
            StudentConceptProgressRow.student_id == student_id,
            StudentConceptProgressRow.course_id == course_id,
            StudentConceptProgressRow.core_concept == core_concept,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        # Create new row with manual mastery
        row = StudentConceptProgressRow(
            student_id=student_id,
            course_id=course_id,
            core_concept=core_concept,
            mastery_score=mastery,
            mastery_sources={},
            manual_mastery=mastery,
            exercises_completed=0,
            quizzes_taken=0,
            quizzes_passed=0,
            last_activity=datetime.now(UTC),
        )
        session.add(row)
    else:
        # Update manual mastery and recompute score
        row.manual_mastery = mastery
        row.last_activity = datetime.now(UTC)

        # Recompute mastery score (manual takes effect immediately)
        row.mastery_score = compute_mastery_score(
            row.mastery_sources,
            row.manual_mastery,
            has_activity_since_override=False,
        )

    await session.commit()

    logger.info(
        "manual_mastery_set",
        student_id=student_id,
        course_id=course_id,
        concept=core_concept,
        mastery=mastery,
    )

    return row.mastery_score
