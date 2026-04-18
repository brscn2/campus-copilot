"""Content pipeline — extract Moodle zips, upload PDFs to Cognee, build knowledge graphs.

Bridges the Moodle scraper (downloads zips) and the Cognee cognify pipeline
(builds knowledge graphs). Extracts downloaded course zips, uploads PDFs via
the Cognee HTTP API, then triggers cognify to build per-course knowledge graphs.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.exceptions import CogneeIngestionError
from src.lib.cognify import trigger_cognify, upload_file_to_cognee
from src.lib.logging import get_logger
from src.lib.s3 import upload_file as s3_upload

logger = get_logger(__name__)


def _safe_dataset_name(name: str) -> str:
    """Sanitize a course name into a cognee-safe dataset identifier."""
    keep = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    raw = name.lower().replace(" ", "_").replace("-", "_")
    return "".join(c if c in keep else "" for c in raw)[:60] or "course"


# ---------------------------------------------------------------------------
# Step 1: Extract zips into per-course folders
# ---------------------------------------------------------------------------


def extract_all_zips(
    download_dir: Path | None = None,
    extract_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Unzip all course zips into extract_dir.

    Args:
        download_dir: Override for the download directory.
        extract_dir: Override for the extraction directory.

    Returns:
        Metadata per course including file paths and PDF counts.
    """
    settings = get_settings()
    dl = download_dir or Path(settings.moodle_download_dir)
    out = extract_dir or Path(settings.moodle_extract_dir)
    out.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    for zip_path in sorted(dl.rglob("*.zip")):
        course_name = zip_path.parent.name
        dest = out / _safe_dataset_name(course_name)

        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest)

        files = list(dest.rglob("*"))
        pdfs = [f for f in files if f.suffix.lower() == ".pdf"]
        all_files = [f for f in files if f.is_file()]

        logger.info(
            "pipeline_extract_done",
            course=course_name,
            total_files=len(all_files),
            pdfs=len(pdfs),
        )
        results.append(
            {
                "course_name": course_name,
                "dataset_name": _safe_dataset_name(course_name),
                "extract_path": str(dest),
                "total_files": len(all_files),
                "pdf_count": len(pdfs),
                "file_paths": [str(f) for f in all_files],
                "pdf_paths": [str(f) for f in pdfs],
            }
        )

    return results


# ---------------------------------------------------------------------------
# Step 2: Upload PDFs to Cognee and trigger cognify
# ---------------------------------------------------------------------------


async def ingest_course(
    course_id: str,
    dataset_name: str,
    pdf_paths: list[str],
) -> dict[str, Any]:
    """Upload PDFs to Cognee and trigger cognify for one course.

    Args:
        course_id: Course identifier used for the Cognee dataset.
        dataset_name: Sanitized dataset name.
        pdf_paths: Absolute paths to PDF files to ingest.

    Returns:
        Status dict with dataset name, file count, and cognify job ID.
    """
    if not pdf_paths:
        logger.info("pipeline_ingest_skip", dataset=dataset_name, reason="no PDFs")
        return {"dataset": dataset_name, "status": "skipped", "reason": "no PDFs"}

    logger.info("pipeline_ingest_start", dataset=dataset_name, files=len(pdf_paths))

    s3_keys: list[str] = []

    for pdf_path in pdf_paths:
        path = Path(pdf_path)
        try:
            file_content = path.read_bytes()

            s3_key = f"slides/{dataset_name}/{path.name}"
            await s3_upload(s3_key, file_content, content_type="application/pdf")
            s3_keys.append(s3_key)

            await upload_file_to_cognee(
                course_id=course_id,
                file_content=file_content,
                filename=path.name,
            )
            logger.info("pipeline_upload_done", dataset=dataset_name, file=path.name)
        except Exception as exc:
            logger.error(
                "pipeline_upload_error",
                dataset=dataset_name,
                file=path.name,
                exc_info=True,
            )
            raise CogneeIngestionError(
                f"Failed to upload {path.name} for {dataset_name}: {exc}"
            ) from exc

    job_id = await trigger_cognify(course_id)
    logger.info("pipeline_cognify_triggered", dataset=dataset_name, job_id=job_id)

    return {
        "dataset": dataset_name,
        "status": "ingesting",
        "files_uploaded": len(pdf_paths),
        "s3_keys": s3_keys,
        "cognify_job_id": job_id,
    }


async def ingest_all_courses(
    courses: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Extract zips and ingest all courses into Cognee.

    Args:
        courses: Pre-extracted course metadata. If None, runs extract_all_zips first.

    Returns:
        List of per-course ingestion results.
    """
    if courses is None:
        courses = extract_all_zips()

    results: list[dict[str, Any]] = []
    for course in courses:
        try:
            result = await ingest_course(
                course_id=course["dataset_name"],
                dataset_name=course["dataset_name"],
                pdf_paths=course.get("pdf_paths", []),
            )
            results.append(result)
        except CogneeIngestionError:
            results.append(
                {
                    "dataset": course["dataset_name"],
                    "status": "error",
                }
            )
        except Exception as exc:
            logger.exception("pipeline_ingest_error", dataset=course["dataset_name"])
            results.append(
                {
                    "dataset": course["dataset_name"],
                    "status": f"error: {exc}",
                }
            )

    return results


# ---------------------------------------------------------------------------
# Full pipeline: scrape → extract → upload → cognify
# ---------------------------------------------------------------------------


async def run_full_pipeline(semester: str | None = None) -> dict[str, Any]:
    """Run the complete Moodle → Cognee pipeline.

    1. Download all course materials from Moodle.
    2. Extract zips into per-course folders.
    3. Upload PDFs to Cognee.
    4. Trigger cognify to build knowledge graphs.

    Args:
        semester: Optional semester filter for Moodle courses.

    Returns:
        Summary with download results and ingestion results.
    """
    from src.integrations.moodle import download_all_courses

    logger.info("pipeline_full_start", semester=semester)

    download_results = await download_all_courses(semester=semester)
    logger.info(
        "pipeline_downloads_done",
        total=len(download_results),
        downloaded=sum(1 for r in download_results if r["status"] == "downloaded"),
    )

    courses = extract_all_zips()
    logger.info("pipeline_extraction_done", courses=len(courses))

    ingestion_results = await ingest_all_courses(courses)
    logger.info("pipeline_ingestion_done", results=len(ingestion_results))

    return {
        "downloads": download_results,
        "extractions": courses,
        "ingestions": ingestion_results,
    }
