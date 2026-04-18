"""API routes for the Moodle → Cognee content pipeline."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from src.lib.logging import get_logger

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


_CODE_RE = re.compile(r"[_( ]\s*((?:IN|MA|CIT|CITHN)\d{3,6})\s*[_) ]?")
_SEM_RE = re.compile(r"((?:SoSe|WiSe)\s+\d{4}(?:[_/]\d{2,4})?)")
_FACULTY_RE = re.compile(
    r"\s*[_\-]\s*(?:Computation|Studentische|TUM Global|Alumni Office).*",
    re.IGNORECASE,
)


def _parse_download_folder(raw_name: str) -> tuple[str, str, str]:
    """Extract display name, course code, and semester from a Moodle download folder name."""
    codes = _CODE_RE.findall(raw_name)
    code = codes[0].upper() if codes else ""

    sem_match = _SEM_RE.search(raw_name)
    semester = sem_match.group(1).replace("_", "/") if sem_match else ""

    name = raw_name
    name = _FACULTY_RE.sub("", name)
    while _CODE_RE.search(name):
        name = _CODE_RE.sub(" ", name, count=1)
    name = _SEM_RE.sub("", name)
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" .,_-")

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
async def list_synced_courses() -> SyncedCoursesResponse:
    """List courses that have been synced (extracted locally)."""
    from pathlib import Path

    from src.config import get_settings

    settings = get_settings()
    extract_dir = Path(settings.moodle_extract_dir)
    download_dir = Path(settings.moodle_download_dir)

    if not extract_dir.exists():
        return SyncedCoursesResponse(courses=[])

    name_map = _build_download_to_extract_map(download_dir)

    courses: list[SyncedCourse] = []
    for course_dir in sorted(extract_dir.iterdir()):
        if not course_dir.is_dir():
            continue
        dataset = course_dir.name
        pdfs = list(course_dir.rglob("*.pdf"))
        s3_prefix = f"slides/{dataset}/"
        original_name = name_map.get(dataset, dataset)
        display_name, code, semester = _parse_download_folder(original_name)
        courses.append(
            SyncedCourse(
                dataset_name=dataset,
                display_name=display_name,
                course_code=code,
                semester=semester,
                pdf_count=len(pdfs),
                s3_prefix=s3_prefix,
            )
        )

    return SyncedCoursesResponse(courses=courses)


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
