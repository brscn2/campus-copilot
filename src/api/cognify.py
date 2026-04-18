"""API routes for Cognee cognify pipeline and content webhooks."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.lib.cognify import CognifyStatus, get_job_status, trigger_cognify
from src.lib.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/cognify", tags=["cognify"])


class CognifyRequest(BaseModel):
    """Request to trigger cognify for a course."""

    course_id: str


class CognifyResponse(BaseModel):
    """Response with job ID for polling."""

    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    """Response for job status polling."""

    job_id: str
    status: str
    course_id: str
    error: str | None = None


class ContentUploadedWebhook(BaseModel):
    """Webhook payload from Moodle scraper after uploading files to Cognee."""

    course_id: str
    files: list[str] = []
    source: str = "moodle_scraper"


@router.post("/trigger", response_model=CognifyResponse)
async def trigger_cognify_endpoint(request: CognifyRequest) -> CognifyResponse:
    """Manually trigger the cognify pipeline for a course.

    Called by the frontend "Build Knowledge Graph" button.
    Returns immediately with a job_id for status polling.
    """
    logger.info("cognify_trigger_manual", course_id=request.course_id)
    job_id = await trigger_cognify(request.course_id)
    return CognifyResponse(job_id=job_id, status=CognifyStatus.PENDING)


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_cognify_status(job_id: str) -> JobStatusResponse:
    """Poll the status of a cognify job."""
    job = get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        course_id=job["course_id"],
        error=job.get("error"),
    )


@router.post("/webhooks/content-uploaded", response_model=CognifyResponse)
async def content_uploaded_webhook(payload: ContentUploadedWebhook) -> CognifyResponse:
    """Webhook called by Moodle scraper after uploading new files to Cognee.

    Auto-triggers cognify for the course so the knowledge graph stays fresh.
    """
    logger.info(
        "cognify_webhook_content_uploaded",
        course_id=payload.course_id,
        file_count=len(payload.files),
        source=payload.source,
    )
    job_id = await trigger_cognify(payload.course_id)
    return CognifyResponse(job_id=job_id, status=CognifyStatus.PENDING)
