"""API routes for the Moodle → Cognee content pipeline."""

from __future__ import annotations

# ruff: noqa: B008
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.lib.logging import get_logger
from src.storage.db import get_session
from src.storage.repositories import course_overrides as overrides_repo

logger = get_logger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


class PipelineRequest(BaseModel):
    """Request to run the content pipeline."""

    semester: str | None = None


class ExtractResponse(BaseModel):
    """Response from zip extraction."""

    courses: list[dict[str, Any]]


class IngestResponse(BaseModel):
    """Response from ingestion."""

    results: list[dict[str, Any]]


class FullPipelineResponse(BaseModel):
    """Response from the full pipeline run."""

    downloads: list[dict[str, Any]]
    extractions: list[dict[str, Any]]
    ingestions: list[dict[str, Any]]


class CoursesResponse(BaseModel):
    """Response listing Moodle courses."""

    courses: list[dict[str, Any]]


@router.get("/courses", response_model=CoursesResponse)
async def list_courses(semester: str | None = None) -> CoursesResponse:
    """Fetch courses from Moodle dashboard."""
    from src.integrations.moodle import get_courses

    logger.info("pipeline_list_courses", semester=semester)
    courses = await get_courses(semester=semester)
    return CoursesResponse(courses=courses)


@router.post("/download", response_model=IngestResponse)
async def download_courses(request: PipelineRequest) -> IngestResponse:
    """Download all course materials from Moodle."""
    from src.integrations.moodle import download_all_courses

    logger.info("pipeline_download_all", semester=request.semester)
    results = await download_all_courses(semester=request.semester)
    return IngestResponse(results=results)


@router.post("/extract", response_model=ExtractResponse)
async def extract_zips() -> ExtractResponse:
    """Extract all downloaded course zips."""
    from src.integrations.content_pipeline import extract_all_zips

    logger.info("pipeline_extract_all")
    courses = extract_all_zips()
    return ExtractResponse(courses=courses)


@router.post("/ingest", response_model=IngestResponse)
async def ingest_courses() -> IngestResponse:
    """Extract zips, upload PDFs to Cognee, and trigger cognify."""
    from src.integrations.content_pipeline import ingest_all_courses

    logger.info("pipeline_ingest_all")
    results = await ingest_all_courses()
    return IngestResponse(results=results)


@router.post("/run", response_model=FullPipelineResponse)
async def run_full(request: PipelineRequest) -> FullPipelineResponse:
    """Run the complete pipeline: download → extract → upload → cognify."""
    from src.integrations.content_pipeline import run_full_pipeline

    logger.info("pipeline_run_full", semester=request.semester)
    result = await run_full_pipeline(semester=request.semester)
    return FullPipelineResponse(**result)


class SyncedCourse(BaseModel):
    """A course synced from Moodle with S3 file info."""

    dataset_name: str
    display_name: str
    course_code: str
    semester: str
    pdf_count: int
    s3_prefix: str


class SyncedCoursesResponse(BaseModel):
    """Response listing synced courses."""

    courses: list[SyncedCourse]


_CODE_RE = re.compile(r"[_( ]\s*((?:IN|MA|CIT|CITHN)\d{3,6})\s*[_) ]?", re.IGNORECASE)
_SEM_RE = re.compile(r"((?:SoSe|WiSe|sose|wise)[_ ]*\d{4}(?:[_/ ]\d{2,4})?)", re.IGNORECASE)
_TRUNCATED_SEM_RE = re.compile(r"[_\s](wi(?:se)?|so(?:se)?)$", re.IGNORECASE)
_FACULTY_RE = re.compile(
    r"\s*[_\-]\s*(?:Computation|Studentische|TUM Global|Alumni Office).*",
    re.IGNORECASE,
)


def _parse_download_folder(raw_name: str) -> tuple[str, str, str]:
    """Extract display name, course code, and semester from a Moodle download folder name."""
    codes = _CODE_RE.findall(raw_name)
    code = codes[0].upper() if codes else ""

    sem_match = _SEM_RE.search(raw_name)
    if sem_match:
        raw_sem = sem_match.group(1).replace("_", " ").strip()
        if raw_sem[:4].lower() == "wise":
            semester = "WiSe " + raw_sem[4:].strip().replace(" ", "/")
        elif raw_sem[:4].lower() == "sose":
            semester = "SoSe " + raw_sem[4:].strip()
        else:
            semester = raw_sem
    else:
        semester = ""

    name = raw_name
    name = _FACULTY_RE.sub("", name)
    while _CODE_RE.search(name):
        name = _CODE_RE.sub(" ", name, count=1)
    name = _SEM_RE.sub("", name)
    name = _TRUNCATED_SEM_RE.sub("", name)
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" .,_-")
    name = name.title() if name == name.lower() else name

    return name or raw_name, code, semester


def _build_download_to_extract_map(download_dir: Path) -> dict[str, str]:
    """Map extracted folder names back to their original download folder names."""
    from src.integrations.content_pipeline import _safe_dataset_name

    mapping: dict[str, str] = {}
    if download_dir.exists():
        for dl_dir in download_dir.iterdir():
            if dl_dir.is_dir():
                sanitized = _safe_dataset_name(dl_dir.name)
                mapping[sanitized] = dl_dir.name
    return mapping


@router.get("/synced", response_model=SyncedCoursesResponse)
async def list_synced_courses(
    student_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> SyncedCoursesResponse:
    """List courses that have been synced — reads from S3 slides/ prefix.

    The ``semester`` field returned to the client is the regex-derived value
    from the Moodle download folder, unless the student has applied an
    override via :func:`upsert_course_override`.  ``dataset_name`` is never
    overridden because S3 / Cognee / quiz history all key on it.
    """
    from src.lib.s3 import list_objects

    objects = await list_objects("slides/")
    course_files: dict[str, int] = {}
    for obj in objects:
        parts = obj["key"].split("/")
        if len(parts) >= 3 and parts[1]:
            dataset = parts[1]
            course_files[dataset] = course_files.get(dataset, 0) + 1

    overrides = await overrides_repo.get_overrides(session, student_id)

    from src.integrations.tumonline import get_lectures

    _SEM_NORM: dict[str, str] = {}
    try:
        lectures = await get_lectures()
        for lec in lectures:
            raw_code = lec.get("code", "")
            raw_sem = lec.get("semester", "")
            if not raw_code or not raw_sem:
                continue
            sem = raw_sem.replace("Sommersemester ", "SoSe ").replace(
                "Wintersemester ", "WiSe "
            ).replace("/26", "/2026")
            for c in raw_code.split(","):
                _SEM_NORM[c.strip().upper()] = sem
    except Exception:
        logger.warning("tumonline_lectures_unavailable_for_semester", exc_info=True)

    courses: list[SyncedCourse] = []
    for dataset, pdf_count in sorted(course_files.items()):
        display_name, code, semester = _parse_download_folder(dataset)
        if not semester and code:
            for sub in code.split(","):
                sub = sub.strip().upper()
                if sub in _SEM_NORM:
                    semester = _SEM_NORM[sub]
                    break
        override = overrides.get(dataset, {})
        if override.get("semester"):
            semester = override["semester"]
        courses.append(
            SyncedCourse(
                dataset_name=dataset,
                display_name=display_name,
                course_code=code,
                semester=semester,
                pdf_count=pdf_count,
                s3_prefix=f"slides/{dataset}/",
            )
        )

    return SyncedCoursesResponse(courses=courses)


# ---------------------------------------------------------------------------
# Course-metadata override endpoints
# ---------------------------------------------------------------------------


class CourseOverridesResponse(BaseModel):
    """Map of dataset_name → override fields (currently just ``semester``)."""

    overrides: dict[str, dict[str, str]]


class CourseOverrideUpsert(BaseModel):
    """Body for setting a single course's semester override."""

    student_id: str = "demo"
    semester: str


@router.get("/synced/overrides", response_model=CourseOverridesResponse)
async def list_course_overrides(
    student_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> CourseOverridesResponse:
    """Return all per-course metadata overrides for ``student_id``."""
    overrides = await overrides_repo.get_overrides(session, student_id)
    return CourseOverridesResponse(overrides=overrides)


@router.put("/synced/overrides/{dataset_name}", response_model=CourseOverridesResponse)
async def upsert_course_override(
    dataset_name: str,
    body: CourseOverrideUpsert,
    session: AsyncSession = Depends(get_session),
) -> CourseOverridesResponse:
    """Set the semester override for a single Cognee dataset."""
    semester = body.semester.strip()
    if not semester:
        raise HTTPException(status_code=400, detail="semester must not be empty")
    overrides = await overrides_repo.set_override(
        session,
        student_id=body.student_id,
        dataset_name=dataset_name,
        semester=semester,
    )
    return CourseOverridesResponse(overrides=overrides)


@router.delete("/synced/overrides/{dataset_name}", response_model=CourseOverridesResponse)
async def delete_course_override(
    dataset_name: str,
    student_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> CourseOverridesResponse:
    """Drop the semester override for one dataset, restoring the regex value."""
    overrides = await overrides_repo.delete_override(
        session,
        student_id=student_id,
        dataset_name=dataset_name,
    )
    return CourseOverridesResponse(overrides=overrides)


@router.delete("/synced/overrides", response_model=CourseOverridesResponse)
async def clear_course_overrides(
    student_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> CourseOverridesResponse:
    """Drop all overrides for ``student_id`` — used by the UI's *Reset* button."""
    await overrides_repo.clear_overrides(session, student_id)
    return CourseOverridesResponse(overrides={})


class FileListResponse(BaseModel):
    """Response listing files in S3."""

    files: list[dict[str, Any]]


class PresignedUrlResponse(BaseModel):
    """Response with a presigned download URL."""

    url: str
    key: str


@router.get("/files/{course_id}", response_model=FileListResponse)
async def list_course_files(course_id: str) -> FileListResponse:
    """List all files uploaded to S3 for a course."""
    from src.lib.s3 import list_objects

    prefix = f"slides/{course_id}/"
    logger.info("pipeline_list_files", course_id=course_id, prefix=prefix)
    files = await list_objects(prefix)
    return FileListResponse(files=files)


@router.get("/files/{course_id}/{filename}/url", response_model=PresignedUrlResponse)
async def get_file_url(course_id: str, filename: str) -> PresignedUrlResponse:
    """Get a presigned URL to download a course file."""
    from src.lib.s3 import generate_presigned_url

    key = f"slides/{course_id}/{filename}"
    logger.info("pipeline_presigned_url", key=key)
    url = await generate_presigned_url(key)
    return PresignedUrlResponse(url=url, key=key)


# ---------------------------------------------------------------------------
# Course files with progress + mastery (per spec)
# ---------------------------------------------------------------------------

from src.storage.repositories import course_files as cf_repo


@router.get("/synced/{dataset_name}/files")
async def list_files_with_progress(
    dataset_name: str,
    student_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List course files with per-student completion status."""
    files = await cf_repo.get_files_with_progress(session, student_id, dataset_name)
    lectures = [f for f in files if f["category"] == "lecture"]
    exercises = [f for f in files if f["category"] == "exercise"]
    return {
        "files": files,
        "summary": {
            "total": len(files),
            "completed": sum(1 for f in files if f["completed"]),
            "lectures": {
                "total": len(lectures),
                "completed": sum(1 for f in lectures if f["completed"]),
            },
            "exercises": {
                "total": len(exercises),
                "completed": sum(1 for f in exercises if f["completed"]),
            },
        },
    }


class ProgressToggle(BaseModel):
    student_id: str = "demo"
    completed: bool


@router.put("/synced/{dataset_name}/files/{file_id}/progress")
async def toggle_progress(
    dataset_name: str,
    file_id: str,
    body: ProgressToggle,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Toggle file completion for a student."""
    return await cf_repo.toggle_file_progress(
        session, body.student_id, file_id, completed=body.completed
    )


@router.get("/synced/{dataset_name}/concepts")
async def list_concepts(
    dataset_name: str,
    student_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List concepts with per-signal mastery breakdown."""
    concepts = await cf_repo.compute_concept_mastery(session, student_id, dataset_name)
    return {
        "concepts": [
            {
                "name": c.concept,
                "mastery": c.mastery,
                "breakdown": {
                    "lectures": c.lecture_pct,
                    "exercises": c.exercise_pct,
                    "quizzes": c.quiz_pct,
                    "flashcards": c.flashcard_pct,
                    "manual_boost": c.manual_boost,
                },
            }
            for c in concepts
        ]
    }


class ManualBoostBody(BaseModel):
    student_id: str = "demo"
    boost: float


@router.put("/synced/{dataset_name}/concepts/{concept_name}/boost")
async def set_boost(
    dataset_name: str,
    concept_name: str,
    body: ManualBoostBody,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Set manual mastery boost for a concept."""
    if body.boost < 0 or body.boost > 100:
        raise HTTPException(status_code=400, detail="boost must be 0-100")
    await cf_repo.set_manual_boost(session, body.student_id, dataset_name, concept_name, body.boost)
    return {"status": "ok"}
