"""REST endpoints for the Career tab — profile, jobs, CV audit."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from src.integrations.jobs import search_jobs
from src.integrations.luma import fetch_munich_events
from src.integrations.tumonline import get_grades, get_identity, get_lectures
from src.lib.bedrock import get_haiku_model_id, get_sonnet_model_id, invoke_model
from src.lib.logging import get_logger
from src.lib.skill_inference import infer_skills, is_noise_lecture

logger = get_logger(__name__)

router = APIRouter(prefix="/career", tags=["career"])

CV_AUDIT_PROMPT = """You are a career advisor at TUM (Technical University of Munich).
A student has uploaded their CV. Analyze it against their real academic record and produce structured feedback.

## Student's Real Academic Record (from TUMonline)
{profile_context}

## Student's CV Text
{cv_text}

## Your Task
Cross-reference the CV against the academic record. Return a JSON object with:

1. "flags": EXACTLY 6 findings — the 2 most critical issues, 2 warnings, and 2 positives.
   Each: {{"level": "critical"|"warning"|"good", "text": "one sentence"}}

2. "suggestions": EXACTLY 4 concrete text changes — the 4 highest-impact improvements.
   Each: {{"label": "short title (under 8 words)", "original": "brief quote from CV", "suggested": "replacement text (keep concise, under 40 words)"}}

Prioritize:
- Missing strong grades or relevant coursework
- Skills mismatch (listed vs. evidenced by courses)
- Missing sections or structural improvements

Keep suggestions SHORT. Quote only the minimum necessary from the original.
Return ONLY valid JSON. No markdown fences, no explanation."""


@router.get("/profile")
async def get_profile() -> dict[str, Any]:
    """Fetch the student's academic profile from TUMonline."""
    try:
        identity = await get_identity()
        grades = await get_grades()
        lectures = await get_lectures()
    except Exception as exc:
        logger.error("career_profile_fetch_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"TUMonline unavailable: {exc}") from exc

    skills = await infer_skills(grades, lectures)

    program = grades[0].get("program", "") if grades else ""
    degree = grades[0].get("degree", "") if grades else ""

    passed = [g for g in grades if g.get("grade_float") is not None and g["grade_float"] <= 4.0]
    gpa = None
    if passed:
        total_credits = sum(g["credits"] for g in passed)
        if total_credits > 0:
            weighted = sum(g["grade_float"] * g["credits"] for g in passed)
            gpa = round(weighted / total_credits, 2)

    headline = f"{degree} {program}" if degree and program else program
    name = f"{identity.get('first_name', '')} {identity.get('last_name', '')}".strip()
    summary = (
        f"{name} is a {degree} student in {program} at TUM."
        if program
        else f"{name} — TUM student."
    )

    all_sem_ids = [lec.get("semester_id", "") for lec in lectures if lec.get("semester_id")]
    current_sem = max(all_sem_ids) if all_sem_ids else ""

    current_lectures = [
        {
            "title": lec["title"],
            "code": lec["code"],
            "type": lec["type"],
            "chair": lec["chair"],
        }
        for lec in lectures
        if lec.get("type_short") in ("VO", "SE")
        and not is_noise_lecture(lec.get("title", ""))
        and lec.get("semester_id", "") == current_sem
    ]

    return {
        "name": name,
        "username": identity.get("username", ""),
        "headline": headline,
        "summary": summary,
        "program": program,
        "degree": degree,
        "gpa": gpa,
        "skills": skills,
        "grades": [
            {
                "course_code": g["course_code"],
                "title": g["title"],
                "grade": g["grade"],
                "credits": g["credits"],
                "semester": g["semester"],
                "examiner": g["examiner"],
            }
            for g in grades
        ],
        "current_lectures": current_lectures,
    }


@router.get("/jobs")
async def list_jobs(
    kind: str | None = None,
    keywords: str | None = None,
    company: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Search job listings."""
    kw_list = keywords.split(",") if keywords else None
    return await search_jobs(kind=kind, keywords=kw_list, company=company, location=location)


def _extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF using PyMuPDF."""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


def _build_profile_context(
    grades: list[dict[str, Any]],
    lectures: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    identity: dict[str, Any],
    gpa: float | None,
) -> str:
    """Build a text summary of the student's profile for the LLM prompt."""
    lines: list[str] = []
    name = f"{identity.get('first_name', '')} {identity.get('last_name', '')}".strip()
    lines.append(f"Name: {name}")
    lines.append(f"Email: {identity.get('email', 'samet.degirmenci@tum.de')}")
    if gpa:
        lines.append(f"GPA: {gpa}")

    if grades:
        lines.append(f"Program: {grades[0].get('program', '')} ({grades[0].get('degree', '')})")
        lines.append("\nCompleted courses:")
        for g in grades:
            lines.append(f"  {g['course_code']} — {g['title']} — Grade: {g['grade']} — {g['credits']} ECTS")

    if lectures:
        lines.append("\nCurrently enrolled (SS 2026):")
        for lec in lectures:
            if lec.get("type_short") in ("VO", "SE") and not is_noise_lecture(lec.get("title", "")):
                lines.append(f"  {lec.get('code', '')} — {lec['title']}")

    if skills:
        top_skills = [s["name"] for s in skills[:10]]
        lines.append(f"\nTop skills (from coursework): {', '.join(top_skills)}")

    return "\n".join(lines)


@router.post("/cv/audit")
async def audit_cv(file: UploadFile) -> dict[str, Any]:
    """Upload a CV PDF and get AI-powered audit against real academic record."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    logger.info("cv_audit_start", filename=file.filename, size=len(data))

    try:
        cv_text = _extract_pdf_text(data)
    except Exception as exc:
        logger.error("cv_audit_pdf_extract_failed", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}") from exc

    if len(cv_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="PDF appears empty or unreadable")

    try:
        identity = await get_identity()
        grades = await get_grades()
        lectures = await get_lectures()
        skills = await infer_skills(grades, lectures)
    except Exception as exc:
        logger.error("cv_audit_profile_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"TUMonline unavailable: {exc}") from exc

    passed = [g for g in grades if g.get("grade_float") is not None and g["grade_float"] <= 4.0]
    gpa = None
    if passed:
        total_credits = sum(g["credits"] for g in passed)
        if total_credits > 0:
            gpa = round(sum(g["grade_float"] * g["credits"] for g in passed) / total_credits, 2)

    profile_context = _build_profile_context(grades, lectures, skills, identity, gpa)
    prompt = CV_AUDIT_PROMPT.format(profile_context=profile_context, cv_text=cv_text[:8000])

    try:
        result = await invoke_model(
            model_id=get_sonnet_model_id(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.2,
        )
        text = result.get("content", [{}])[0].get("text", "{}")
        # Strip markdown fences if present
        if "```" in text:
            text = text.split("```json")[-1] if "```json" in text else text.split("```")[-2]
            text = text.split("```")[0]
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            audit = json.loads(text[start:end])
        else:
            raise ValueError("No JSON in response")
    except json.JSONDecodeError as exc:
        logger.error("cv_audit_json_parse_failed", response_text=text[:500], exc_info=True)
        raise HTTPException(status_code=502, detail="AI returned invalid response") from exc
    except Exception as exc:
        logger.error("cv_audit_llm_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}") from exc

    logger.info(
        "cv_audit_complete",
        filename=file.filename,
        flags=len(audit.get("flags", [])),
        suggestions=len(audit.get("suggestions", [])),
    )

    return {
        "filename": file.filename,
        "flags": audit.get("flags", []),
        "suggestions": audit.get("suggestions", []),
    }


EVENTS_SCORE_PROMPT = """Rate each event's relevance (0-100) for this student. Return ONLY a JSON array of objects.

Student profile: {profile}

Events:
{events}

For each event return: {{"title": "...", "score": 0-100, "reason": "one sentence why"}}
Score high if the event relates to: AI, ML, deep learning, 3D vision, software engineering, career fairs, tech networking.
Score low for: unrelated social events, wellness, sports runs, sales dinners.
Return ONLY the JSON array."""


_scored_events_cache: list[dict[str, Any]] | None = None  # cleared on server restart


@router.get("/events")
async def list_events() -> list[dict[str, Any]]:
    """Fetch Munich career events from Luma, scored by profile relevance."""
    global _scored_events_cache  # noqa: PLW0603
    if _scored_events_cache is not None:
        return _scored_events_cache

    events = await fetch_munich_events()

    try:
        skills = []
        grades = await get_grades()
        lectures = await get_lectures()
        skill_list = await infer_skills(grades, lectures)
        skills = [s["name"] for s in skill_list[:8]]
    except Exception:
        logger.warning("events_profile_fetch_failed", exc_info=True)
        skills = ["AI", "Machine Learning", "Software Engineering"]

    profile_summary = f"M.Sc. Informatik student at TUM. Skills: {', '.join(skills)}"

    events_text = "\n".join(
        f"- {e['title']} ({e.get('date', '')}, {e.get('location', '')})"
        for e in events[:15]
    )

    try:
        result = await invoke_model(
            model_id=get_haiku_model_id(),
            messages=[{"role": "user", "content": EVENTS_SCORE_PROMPT.format(
                profile=profile_summary, events=events_text
            )}],
            max_tokens=1500,
            temperature=0.0,
        )
        text = result.get("content", [{}])[0].get("text", "[]")
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            scores = json.loads(text[start:end])
        else:
            scores = []
    except Exception:
        logger.warning("events_scoring_failed", exc_info=True)
        scores = []

    score_map: dict[str, dict[str, Any]] = {}
    for s in scores:
        if isinstance(s, dict) and "title" in s:
            score_map[s["title"]] = s

    scored_events: list[dict[str, Any]] = []
    for e in events[:15]:
        match = score_map.get(e["title"], {})
        scored_events.append({
            **e,
            "fit_score": match.get("score", 50),
            "reason": match.get("reason", ""),
        })

    scored_events.sort(key=lambda x: x["fit_score"], reverse=True)
    _scored_events_cache = scored_events
    return scored_events
