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
