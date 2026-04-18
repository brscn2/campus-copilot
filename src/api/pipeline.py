"""API routes for the Moodle → Cognee content pipeline."""

from __future__ import annotations

from typing import Any

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
