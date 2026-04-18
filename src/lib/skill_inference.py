"""Infer skills from TUMonline courses and grades.

Uses a static map for known course codes. For unknown courses, fetches
the course description from TUMonline's NAT API and uses Haiku to extract skills.
Results are cached in memory so each course is only processed once per server lifetime.
"""

from __future__ import annotations

import json
from typing import Any

from src.lib.logging import get_logger

logger = get_logger(__name__)

SKILL_MAP: dict[str, list[str]] = {
    "IN2346": ["Deep Learning", "Python", "PyTorch"],
    "IN2081": ["Software Engineering", "Design Patterns"],
    "CITHN2014": ["Generative AI", "LLMs", "Python"],
    "IN2392": ["3D Computer Vision", "Machine Learning", "Python"],
    "IN0024": ["Operations Research", "Optimization"],
    "IN2322": ["Bioinformatics", "Protein Prediction", "Python"],
    "IN2064": ["Machine Learning", "Python"],
    "IN2086": ["Distributed Systems", "Networking"],
    "IN0007": ["Algorithms", "Data Structures"],
    "MA0901": ["Linear Algebra", "Mathematics"],
    "IN2354": ["3D Scanning", "Computer Vision"],
    "IN2309": ["Software Engineering"],
    "IN2126": ["Software Engineering"],
    "CIT423002": ["AI Testing", "Software Testing"],
}

_LLM_CACHE: dict[str, list[str]] = {}

NOISE_TITLES = frozenset([
    "fachschaftsvollversammlung",
    "vollversammlung",
    "studentische vertretung",
])

EXTRACT_SKILLS_PROMPT = """Extract exactly 3 broad, industry-recognized technical skills from this university course.
Use short, standard skill names that appear on LinkedIn or job postings (e.g. "Machine Learning", "Python", "Computer Vision").
Do NOT use course-specific jargon or overly narrow terms.

Course: {title}
Topics covered: {description}

Return ONLY a JSON array of 3 skill names. Example: ["Machine Learning", "Python", "Computer Vision"]"""


def is_noise_lecture(title: str) -> bool:
    """Return True for non-academic entries (student council, assemblies)."""
    lower = title.lower()
    return any(n in lower for n in NOISE_TITLES)


async def _extract_skills_with_llm(
    title: str,
    description: str,
    course_code: str,
) -> list[str]:
    """Use Haiku to extract skills from a course title + description."""
    if course_code in _LLM_CACHE:
        return _LLM_CACHE[course_code]

    if not description or len(description) < 10:
        _LLM_CACHE[course_code] = []
        return []

    try:
        from src.lib.bedrock import get_haiku_model_id, invoke_model

        prompt = EXTRACT_SKILLS_PROMPT.format(title=title, description=description)
        result = await invoke_model(
            model_id=get_haiku_model_id(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.0,
        )
        text = result.get("content", [{}])[0].get("text", "[]")
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            skills = json.loads(text[start:end])
            if isinstance(skills, list):
                skills = [s for s in skills if isinstance(s, str)][:3]
                _LLM_CACHE[course_code] = skills
                logger.info("skill_llm_extracted", course_code=course_code, skills=skills)
                return skills
    except Exception:
        logger.warning("skill_llm_failed", course_code=course_code, exc_info=True)

    _LLM_CACHE[course_code] = []
    return []


async def _get_skills_for_course(
    course_code: str,
    title: str,
    course_id: int | str | None = None,
) -> list[str]:
    """Get skills for a course: static map first, then LLM with course description."""
    if course_code in SKILL_MAP:
        return SKILL_MAP[course_code]

    if course_code in _LLM_CACHE:
        return _LLM_CACHE[course_code]

    if course_id:
        try:
            from src.integrations.tumonline import get_course_description

            details = await get_course_description(course_id)
            if details:
                desc = details.get("description_en") or details.get("description") or ""
                return await _extract_skills_with_llm(title, desc, course_code)
        except Exception:
            logger.warning("skill_course_desc_failed", course_code=course_code, exc_info=True)

    return await _extract_skills_with_llm(title, title, course_code)


async def infer_skills(
    grades: list[dict[str, Any]],
    lectures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive skills with proficiency levels from grades and current courses.

    Grading scale (German): 1.0 = best, 4.0 = passed, 5.0 = failed.
    Failed courses (>= 5.0) are excluded entirely.

    Proficiency formula for passed courses:
      level = 100 - (grade - 1.0) * 20
      Clamped to [40, 100]. So: 1.0 -> 100%, 1.7 -> 86%, 2.7 -> 66%, 4.0 -> 40%.

    In-progress courses get a baseline of 35%.
    """
    skill_scores: dict[str, dict[str, Any]] = {}

    for g in grades:
        grade_f = g.get("grade_float")
        if grade_f is None or grade_f >= 5.0:
            continue

        code = g.get("course_code", "")
        title = g.get("title", "")
        mapped = await _get_skills_for_course(code, title)
        proficiency = max(40, min(100, int(100 - (grade_f - 1.0) * 20)))

        for skill_name in mapped:
            existing = skill_scores.get(skill_name)
            if existing is None or proficiency > existing["level"]:
                skill_scores[skill_name] = {
                    "name": skill_name,
                    "level": proficiency,
                    "source": f"{code} ({g.get('grade', '')})",
                }

    for lec in lectures:
        code = lec.get("code", "")
        title = lec.get("title", lec.get("full_title", ""))
        if is_noise_lecture(title) or not code or code == "IN":
            continue
        course_id = lec.get("stp_sp_nr") or lec.get("course_id")
        mapped = await _get_skills_for_course(code, title, course_id)
        for skill_name in mapped:
            if skill_name not in skill_scores:
                skill_scores[skill_name] = {
                    "name": skill_name,
                    "level": 35,
                    "source": f"{code} (in progress)",
                }

    return sorted(skill_scores.values(), key=lambda s: s["level"], reverse=True)
