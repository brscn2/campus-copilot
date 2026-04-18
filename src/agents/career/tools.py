"""Pure-function tools for the Career agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.integrations.jobs import search_jobs as _search_jobs

MOCK_CV_SECTIONS = [
    "education",
    "experience",
    "skills",
    "projects",
    "languages",
    "certifications",
]


@tool
async def search_jobs(
    kind: str | None = None,
    keywords: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Search for job listings — working student, internship, or new grad roles.

    Args:
        kind: Type filter — 'working_student', 'internship', or 'new_grad'.
        keywords: Keywords to match against title/description (e.g. ['machine learning']).
        company: Company name filter (e.g. 'BMW').
        location: Location filter (e.g. 'Munich').
    """
    return await _search_jobs(
        kind=kind,
        keywords=keywords,
        company=company,
        location=location,
    )


@tool
async def audit_cv(
    sections_present: list[str],
    target_role: str = "working_student",
) -> dict[str, Any]:
    """Audit a student's CV and return structured feedback.

    The student describes which sections their CV has, and this tool returns
    a checklist of what's good, what's missing, and targeted advice.

    Args:
        sections_present: List of CV sections the student has
            (e.g. ['education', 'experience', 'skills']).
        target_role: The type of role they're targeting
            ('working_student', 'internship', 'new_grad').
    """
    present = {s.lower() for s in sections_present}
    missing = [s for s in MOCK_CV_SECTIONS if s not in present]

    tips: list[str] = []
    if "projects" not in present:
        tips.append("Add a Projects section — it's the #1 differentiator for student CVs.")
    if "skills" not in present:
        tips.append("Add a Skills section with programming languages and frameworks.")
    if target_role == "working_student" and "experience" not in present:
        tips.append("Even part-time jobs or tutoring count as experience — include them.")
    if target_role == "new_grad" and "certifications" not in present:
        tips.append("Certifications (AWS, GCP, etc.) strengthen new-grad applications.")
    if "languages" not in present:
        tips.append("Munich companies value multilingual candidates — list your languages.")

    score = round(len(present) / len(MOCK_CV_SECTIONS) * 100)

    return {
        "completeness_score": score,
        "sections_present": sorted(present),
        "sections_missing": missing,
        "tips": tips,
        "target_role": target_role,
    }
