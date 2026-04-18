"""ZHS (Zentraler Hochschulsport) Munich integration via MeiliSearch API.

Fetches real sport course data from kurse.zhs-muenchen.de.
Public read access — no authentication required for course discovery.
Registration requires TUM login (user handles this on the website).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from src.exceptions import TUMSystemUnavailableError
from src.lib.logging import get_logger
from src.lib.retry import retry_external
from src.models.zhs import ZhsCourse, _infer_category, _infer_level, _infer_location

logger = get_logger(__name__)

ZHS_BASE_URL = "https://kurse.zhs-muenchen.de"
ZHS_SEARCH_URL = f"{ZHS_BASE_URL}/services/search"
ZHS_API_KEY = "5632a784b8e5e66066307adbeb8e19bb6558fdf2bca26ef35dd3ee98b17e0c1e"
ZHS_INDEX = "public_offers"

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    return " ".join(cleaned.split()).strip()


_GROUP_SLUG_MAP: dict[str, str] = {
    "b092c32f-0f8f-4c4c-9ca5-d7e621876b85": "muenchen",
    "c5c8eebc-2e3e-4e0c-9b4b-8f9f8d8e8e8e": "starnberg",
    "d6d9ffcd-3f4f-5f1d-0c5c-9g0g9e9f9f9f": "weihenstephan-triesdorf-freising-landshut",
}


def _resolve_group_slug(group_id: str) -> str:
    """Map a group ID to its URL slug. Falls back to 'muenchen'."""
    return _GROUP_SLUG_MAP.get(group_id, "muenchen")


def _parse_course(hit: dict[str, Any]) -> ZhsCourse:
    """Convert a MeiliSearch hit into a ZhsCourse model."""
    name_dict = hit.get("name", {})
    name_de = name_dict.get("de_DE", "") or name_dict.get("en_EN", "")
    name = name_de

    desc_dict = hit.get("description") or {}
    desc_raw = desc_dict.get("de_DE", "") or desc_dict.get("en_EN", "")
    desc_short = _strip_html(desc_raw)[:300]

    slug_dict = hit.get("slug", {})
    slug = slug_dict.get("de_DE", "") or slug_dict.get("en_EN", "")

    group_id = ""
    if hit.get("group") and isinstance(hit["group"], dict):
        group_id = hit["group"].get("id", "")

    poster_dict = hit.get("poster", {})
    poster = poster_dict.get("de_DE", "") or poster_dict.get("en_EN", "")

    group_slug = _resolve_group_slug(group_id)
    url = f"{ZHS_BASE_URL}/de/{group_slug}/{slug}" if slug else ""

    return ZhsCourse(
        id=hit["id"],
        name=name,
        name_de=name_de,
        description_short=desc_short,
        slug=slug,
        group_id=group_id,
        url=url,
        poster_url=poster,
        category=_infer_category(name, desc_short),
        level=_infer_level(name),
        location=_infer_location(name),
    )


async def _meili_search(
    query: str = "",
    *,
    limit: int = 20,
    offset: int = 0,
    filter_expr: str | None = None,
) -> dict[str, Any]:
    """Execute a search against the ZHS MeiliSearch index."""
    body: dict[str, Any] = {"q": query, "limit": limit, "offset": offset}
    if filter_expr:
        body["filter"] = filter_expr

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{ZHS_SEARCH_URL}/indexes/{ZHS_INDEX}/search",
            json=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {ZHS_API_KEY}",
            },
        )
        if response.status_code != 200:
            raise TUMSystemUnavailableError(f"ZHS search returned {response.status_code}")
        result: dict[str, Any] = response.json()
        return result


@retry_external()  # type: ignore[untyped-decorator]
async def search_courses(
    *,
    keyword: str | None = None,
    category: str | None = None,
    location: str | None = None,
    level: str | None = None,
) -> list[dict[str, Any]]:
    """Search for ZHS sport courses with optional client-side filters.

    Args:
        keyword: Text search against course names and descriptions.
        category: Filter by inferred category (e.g. "Yoga & Mindfulness").
        location: Filter by campus location (e.g. "Freising", "Munich").
        level: Filter by level (e.g. "Beginner", "Intermediate", "Advanced").

    Returns:
        List of matching ZHS course dicts.
    """
    logger.info("zhs_search_courses", keyword=keyword, category=category, location=location)

    data = await _meili_search(keyword or "", limit=141)
    hits = data.get("hits", [])

    courses: list[ZhsCourse] = []
    for hit in hits:
        try:
            courses.append(_parse_course(hit))
        except (KeyError, ValueError):
            logger.warning("zhs_parse_error", course_id=hit.get("id"), exc_info=True)
            continue

    if category:
        courses = [c for c in courses if c.category == category]
    if location:
        courses = [c for c in courses if c.location == location]
    if level:
        courses = [c for c in courses if c.level == level]

    return [c.to_tool_dict() for c in courses]


@retry_external()  # type: ignore[untyped-decorator]
async def get_categories() -> list[dict[str, Any]]:
    """Get all course categories with counts and emoji.

    Returns:
        List of category dicts with name, emoji, and count.
    """
    from src.models.zhs import CATEGORY_EMOJI

    data = await _meili_search("", limit=141)
    hits = data.get("hits", [])

    counts: dict[str, int] = {}
    for hit in hits:
        try:
            c = _parse_course(hit)
            counts[c.category] = counts.get(c.category, 0) + 1
        except (KeyError, ValueError):
            continue

    return sorted(
        [
            {"category": cat, "emoji": CATEGORY_EMOJI.get(cat, "\U0001f3c5"), "count": cnt}
            for cat, cnt in counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )


@retry_external()  # type: ignore[untyped-decorator]
async def get_course_detail(slug: str) -> dict[str, Any] | None:
    """Search for a specific course by slug.

    Args:
        slug: The course slug (e.g. 'yoga-hatha-1').

    Returns:
        Course dict if found, None otherwise.
    """
    logger.info("zhs_get_course_detail", slug=slug)
    data = await _meili_search(slug, limit=5)
    hits = data.get("hits", [])

    for hit in hits:
        slug_dict = hit.get("slug", {})
        hit_slug_de = slug_dict.get("de_DE", "")
        hit_slug_en = slug_dict.get("en_EN", "")
        if slug in (hit_slug_de, hit_slug_en):
            return _parse_course(hit).to_tool_dict()

    if hits:
        return _parse_course(hits[0]).to_tool_dict()
    return None


async def register_for_course(
    *,
    course_id: str,
    student_id: str,
) -> dict[str, Any]:
    """Direct the student to register on the ZHS website.

    Registration requires TUM login — we provide the link.

    Args:
        course_id: The ZHS course identifier.
        student_id: The student making the registration.

    Returns:
        Registration guidance dict with URL.
    """
    logger.info("zhs_register", course_id=course_id, student_id=student_id)

    data = await _meili_search(course_id, limit=5)
    hits = data.get("hits", [])

    course_name = "this course"
    course_url = f"{ZHS_BASE_URL}/en/muenchen"

    for hit in hits:
        if hit.get("id") == course_id:
            name_dict = hit.get("name", {})
            course_name = name_dict.get("en_EN", "") or name_dict.get("de_DE", "")
            slug_dict = hit.get("slug", {})
            slug = slug_dict.get("en_EN", "") or slug_dict.get("de_DE", "")
            if slug:
                course_url = f"{ZHS_BASE_URL}/en/muenchen/{slug}"
            break

    return {
        "status": "redirect_to_zhs",
        "course_name": course_name,
        "registration_url": course_url,
        "login_url": f"{ZHS_BASE_URL}/auth/login",
        "message": (
            f"To register for {course_name}, visit the ZHS website and log in "
            f"with your TUM credentials. Registration link: {course_url}"
        ),
    }


async def set_snipe_alert(
    *,
    course_id: str,
    student_id: str,
) -> dict[str, Any]:
    """Snipe alerts are not yet supported with real ZHS data.

    Returns guidance to check the ZHS website directly.
    """
    logger.info("zhs_set_snipe", course_id=course_id, student_id=student_id)

    return {
        "status": "not_available",
        "message": (
            "Snipe alerts for ZHS courses are not yet available. "
            "Please check the ZHS website directly for spot availability: "
            f"{ZHS_BASE_URL}/en/muenchen"
        ),
        "zhs_url": f"{ZHS_BASE_URL}/en/muenchen",
    }
