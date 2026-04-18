"""Pure-function tools for the Career agent.

Tools are the hands — they do I/O. No LLM calls inside.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from src.integrations.jobs import search_jobs as _search_jobs
from src.integrations.tumonline import (
    get_grades as _get_grades,
    get_identity as _get_identity,
    get_lectures as _get_lectures,
)
from src.lib.skill_inference import infer_skills, is_noise_lecture

MOCK_CV_SECTIONS = [
    "education",
    "experience",
    "skills",
    "projects",
    "languages",
    "certifications",
]


@tool
async def get_student_profile() -> dict[str, Any]:
    """Fetch the student's full academic profile from TUMonline.

    Returns identity, program, grades, current lectures, and inferred skills.
    Use this when the student asks about their profile, skills, courses, or grades.
    """
    identity = await _get_identity()
    grades = await _get_grades()
    lectures = await _get_lectures()
    skills = await infer_skills(grades, lectures)

    program = ""
    degree = ""
    if grades:
        program = grades[0].get("program", "")
        degree = grades[0].get("degree", "")

    passed = [g for g in grades if g.get("grade_float") is not None and g["grade_float"] <= 4.0]
    gpa = None
    if passed:
        total_credits = sum(g["credits"] for g in passed)
        if total_credits > 0:
            weighted = sum(g["grade_float"] * g["credits"] for g in passed)
            gpa = round(weighted / total_credits, 2)

    all_sem_ids = [lec.get("semester_id", "") for lec in lectures if lec.get("semester_id")]
    current_sem = max(all_sem_ids) if all_sem_ids else ""

    current_lectures = [
        {"title": lec["title"], "code": lec["code"], "type": lec["type"], "chair": lec["chair"]}
        for lec in lectures
        if lec.get("type_short") in ("VO", "SE")
        and not is_noise_lecture(lec.get("title", ""))
        and lec.get("semester_id", "") == current_sem
    ]

    return {
        "identity": {
            "first_name": identity.get("first_name", ""),
            "last_name": identity.get("last_name", ""),
            "username": identity.get("username", ""),
        },
        "program": program,
        "degree": degree,
        "gpa": gpa,
        "grades": [
            {
                "course_code": g["course_code"],
                "title": g["title"],
                "grade": g["grade"],
                "credits": g["credits"],
                "semester": g["semester"],
            }
            for g in grades
        ],
        "current_lectures": current_lectures,
        "skills": skills,
    }


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
