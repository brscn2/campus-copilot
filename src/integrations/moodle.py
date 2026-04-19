"""Real Moodle scraper via Playwright.

Logs in through TUM Shibboleth SSO, saves the session for reuse,
scrapes the dashboard for active courses (filterable by semester),
and downloads all course materials via Download Center as numbered zips.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from src.config import get_settings
from src.exceptions import TUMAuthenticationError, TUMSystemUnavailableError
from src.lib.logging import get_logger

logger = get_logger(__name__)

MOODLE_BASE = "https://www.moodle.tum.de"
LOGIN_URL = f"{MOODLE_BASE}/login/index.php"
DASHBOARD_URL = f"{MOODLE_BASE}/my/"


def _safe_dirname(name: str) -> str:
    """Sanitize a course name into a filesystem-safe directory name."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_ ")
    return "".join(c if c in keep else "_" for c in name).strip()[:120]


# ---------------------------------------------------------------------------
# Browser / session management
# ---------------------------------------------------------------------------


async def _ensure_browser_context(
    session_dir: Path,
) -> tuple[Any, BrowserContext]:
    """Launch Chromium and optionally restore a saved session."""
    settings = get_settings()
    session_file = session_dir / "moodle_state.json"

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=settings.moodle_headless)

    if session_file.exists():
        logger.info("moodle_session_reuse", path=str(session_file))
        context = await browser.new_context(
            storage_state=str(session_file),
            accept_downloads=True,
        )
    else:
        context = await browser.new_context(accept_downloads=True)

    return pw, context


async def _save_session(context: BrowserContext, session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "moodle_state.json"
    await context.storage_state(path=str(session_file))
    logger.info("moodle_session_saved", path=str(session_file))


async def _login(context: BrowserContext, session_dir: Path) -> None:
    """Perform TUM Shibboleth SSO login."""
    settings = get_settings()

    if not settings.tum_username or not settings.tum_password:
        raise TUMAuthenticationError("TUM_USERNAME and TUM_PASSWORD must be set")

    page = await context.new_page()
    logger.info("moodle_login_start")

    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        tum_login_link = page.locator("a:has-text('TUM Login')").first
        try:
            await tum_login_link.wait_for(state="visible", timeout=5000)
        except Exception:
            tum_login_link = page.locator(
                "xpath=/html/body/div[2]/div[2]/div/div/div/div/div/div"
                "/div/div[1]/div[3]/div[2]/div/ul/li[1]/dl/dt/a"
            )
        await tum_login_link.click()

        await page.wait_for_url("**/login.tum.de/**", timeout=15000)
        logger.info("moodle_login_shibboleth_page")

        await page.fill("#username", settings.tum_username)
        await page.fill("#password", settings.tum_password)
        await page.click("#btnLogin")

        await page.wait_for_url(f"{MOODLE_BASE}/**", timeout=30000)
        logger.info("moodle_login_success")

        await _save_session(context, session_dir)
    except Exception as exc:
        if "login" in str(exc).lower() or "timeout" in str(exc).lower():
            raise TUMAuthenticationError(f"Moodle login failed: {exc}") from exc
        raise TUMSystemUnavailableError(f"Moodle unreachable: {exc}") from exc
    finally:
        await page.close()


async def _ensure_logged_in(context: BrowserContext, session_dir: Path) -> None:
    page = await context.new_page()
    await page.goto(DASHBOARD_URL, wait_until="domcontentloaded")

    if "login" in page.url.lower():
        logger.info("moodle_session_expired")
        await page.close()
        await _login(context, session_dir)
    else:
        logger.info("moodle_session_valid")
        await page.close()


# ---------------------------------------------------------------------------
# Semester filter
# ---------------------------------------------------------------------------


async def get_semesters(context: BrowserContext) -> list[dict[str, str]]:
    """Return available semesters from the dashboard filter dropdown."""
    page = await context.new_page()
    await page.goto(DASHBOARD_URL, wait_until="domcontentloaded")

    semesters: list[dict[str, str]] = []
    select = page.locator("#coc-filterterm")

    if await select.count() > 0:
        options = select.locator("option")
        count = await options.count()
        for i in range(count):
            opt = options.nth(i)
            value = await opt.get_attribute("value") or ""
            label = (await opt.inner_text()).strip()
            if label:
                semesters.append({"value": value, "label": label})

    logger.info("moodle_semesters_fetched", count=len(semesters))
    await page.close()
    return semesters


# ---------------------------------------------------------------------------
# Course listing
# ---------------------------------------------------------------------------


async def _select_semester(page: Page, semester_value: str) -> None:
    select = page.locator("#coc-filterterm")
    if await select.count() == 0:
        logger.warning("moodle_semester_filter_not_found")
        return
    await select.select_option(semester_value)
    await page.wait_for_timeout(2000)
    logger.info("moodle_semester_selected", value=semester_value)


async def _parse_courses_from_page(page: Page) -> list[dict[str, Any]]:
    """Extract course list from a dashboard page."""
    courses: list[dict[str, Any]] = []
    course_links = page.locator("a[href*='/course/view.php?id=']")
    count = await course_links.count()
    seen_ids: set[str] = set()

    for i in range(count):
        link = course_links.nth(i)
        href = await link.get_attribute("href") or ""
        if "id=" not in href:
            continue
        course_id = href.split("id=")[-1].split("&")[0]
        if course_id in seen_ids:
            continue
        seen_ids.add(course_id)
        name = (await link.inner_text()).strip()
        if not name or len(name) < 3:
            continue
        courses.append({"moodle_id": course_id, "name": name, "url": href})

    return courses


async def get_courses(semester: str | None = None) -> list[dict[str, Any]]:
    """Fetch courses from dashboard, optionally filtered by semester."""
    settings = get_settings()
    session_dir = Path(settings.moodle_session_dir)

    pw, context = await _ensure_browser_context(session_dir)
    try:
        await _ensure_logged_in(context, session_dir)

        page = await context.new_page()
        await page.goto(DASHBOARD_URL, wait_until="domcontentloaded")

        if semester is not None:
            await _select_semester(page, semester)

        courses = await _parse_courses_from_page(page)
        logger.info("moodle_courses_fetched", count=len(courses))

        await page.close()
        await _save_session(context, session_dir)
        return courses
    finally:
        await context.close()
        await pw.stop()


# ---------------------------------------------------------------------------
# Download Center — download all materials for one course
# ---------------------------------------------------------------------------


async def _download_course_zip(
    page: Page,
    course: dict[str, Any],
    download_dir: Path,
) -> Path | None:
    """Navigate to Download Center and download the numbered zip."""
    course_url = f"{MOODLE_BASE}/course/view.php?id={course['moodle_id']}"
    await page.goto(course_url, wait_until="domcontentloaded")
    logger.info("moodle_download_course_page", course=course["name"])

    dc_link = page.locator("a:has-text('Download center'), a:has-text('Download Center')").first
    try:
        await dc_link.wait_for(state="visible", timeout=3000)
    except Exception:
        more_menu = page.locator(
            ".moremenu .dropdownmoremenu a.dropdown-toggle, "
            "a[data-toggle='dropdown']:has-text('Mehr'), "
            "a[data-toggle='dropdown']:has-text('More')"
        ).first
        try:
            await more_menu.wait_for(state="visible", timeout=2000)
            await more_menu.click()
            await page.wait_for_timeout(500)
            dc_link = page.locator(
                ".dropdown-menu a:has-text('Download center'), "
                ".dropdown-menu a:has-text('Download Center')"
            ).first
            await dc_link.wait_for(state="visible", timeout=3000)
        except Exception:
            logger.warning("moodle_download_no_download_center", course=course["name"])
            return None

    await dc_link.click()
    await page.wait_for_load_state("domcontentloaded")
    logger.info("moodle_download_center_opened", course=course["name"])

    checkboxes = page.locator("input[type='checkbox'][name^='item_']")
    cb_count = await checkboxes.count()
    for i in range(cb_count):
        cb = checkboxes.nth(i)
        if not await cb.is_checked():
            await cb.check()
    logger.info("moodle_download_all_checked", course=course["name"], count=cb_count)

    numbering_cb = page.locator("#id_addnumbering")
    if await numbering_cb.count() > 0 and not await numbering_cb.is_checked():
        await numbering_cb.check()

    submit_btn = page.locator("#id_submitbutton")
    try:
        await submit_btn.wait_for(state="visible", timeout=3000)
    except Exception:
        logger.warning("moodle_download_no_submit_button", course=course["name"])
        return None

    if cb_count == 0:
        logger.warning("moodle_download_no_files", course=course["name"])
        return None

    course_dir = download_dir / _safe_dirname(course["name"])
    course_dir.mkdir(parents=True, exist_ok=True)

    async with page.expect_download(timeout=120000) as download_info:
        await submit_btn.click()

    download = await download_info.value
    dest = course_dir / (download.suggested_filename or f"{course['moodle_id']}.zip")
    await download.save_as(str(dest))
    logger.info("moodle_download_saved", course=course["name"], path=str(dest))
    return dest


async def download_all_courses(
    semester: str | None = None,
) -> list[dict[str, Any]]:
    """Download materials for all courses via Download Center.

    Returns:
        List of dicts with course info and the path to the downloaded zip.
    """
    settings = get_settings()
    session_dir = Path(settings.moodle_session_dir)
    download_dir = Path(settings.moodle_download_dir)

    pw, context = await _ensure_browser_context(session_dir)
    try:
        await _ensure_logged_in(context, session_dir)

        page = await context.new_page()
        await page.goto(DASHBOARD_URL, wait_until="domcontentloaded")

        if semester is not None:
            await _select_semester(page, semester)

        courses = await _parse_courses_from_page(page)
        await page.close()
        logger.info("moodle_download_courses_found", count=len(courses))

        results: list[dict[str, Any]] = []
        for course in courses:
            page = await context.new_page()
            try:
                zip_path = await _download_course_zip(page, course, download_dir)
                results.append(
                    {
                        **course,
                        "zip_path": str(zip_path) if zip_path else None,
                        "status": "downloaded" if zip_path else "skipped",
                    }
                )
            except Exception as exc:
                logger.exception("moodle_download_error", course=course["name"])
                results.append({**course, "zip_path": None, "status": f"error: {exc}"})
            finally:
                await page.close()

        await _save_session(context, session_dir)
        return results
    finally:
        await context.close()
        await pw.stop()


SLIDE_EXTENSIONS = (".pdf", ".pptx", ".ppt", ".key")


async def get_slides(*, course_id: str) -> list[dict[str, Any]]:
    """Return uploads from a course filtered to slide-deck file types.

    Thin typed view over `get_uploads` — same Playwright path, just narrowed
    to lecture-style file extensions.

    Args:
        course_id: The Moodle course identifier (numeric string from the URL).

    Returns:
        Subset of `get_uploads` whose filename or URL ends in a slide extension.
    """
    uploads = await get_uploads(course_id)
    return [
        u
        for u in uploads
        if u["filename"].lower().endswith(SLIDE_EXTENSIONS)
        or u["url"].lower().rsplit("?", 1)[0].endswith(SLIDE_EXTENSIONS)
    ]


# ---------------------------------------------------------------------------
# Deadlines — real Moodle calendar scraper with mock fallback
# ---------------------------------------------------------------------------

CALENDAR_UPCOMING_URL = f"{MOODLE_BASE}/calendar/view.php?view=upcoming"

_MOCK_DEADLINES: list[dict[str, Any]] = [
    {
        "deadline_id": "dl-idl-hw1",
        "course_id": "IN2346",
        "title": "Homework 1 — Neural Network Implementation",
        "due_at": "2026-04-25T23:59:00+02:00",
        "weight": 0.15,
        "mastery_gap": 42,
        "priority": 88,
        "source": "moodle",
    },
    {
        "deadline_id": "dl-idl-hw2",
        "course_id": "IN2346",
        "title": "Homework 2 — CNN from Scratch",
        "due_at": "2026-05-09T23:59:00+02:00",
        "weight": 0.15,
        "mastery_gap": 55,
        "priority": 72,
        "source": "moodle",
    },
    {
        "deadline_id": "dl-idl-midterm",
        "course_id": "IN2346",
        "title": "Midterm Exam",
        "due_at": "2026-05-20T10:00:00+02:00",
        "weight": 0.30,
        "mastery_gap": 61,
        "priority": 92,
        "source": "moodle",
    },
    {
        "deadline_id": "dl-ml-hw1",
        "course_id": "IN2064",
        "title": "Exercise Sheet 1 — Linear Regression",
        "due_at": "2026-04-22T23:59:00+02:00",
        "weight": 0.10,
        "mastery_gap": 28,
        "priority": 85,
        "source": "moodle",
    },
    {
        "deadline_id": "dl-ml-project",
        "course_id": "IN2064",
        "title": "Project Proposal Submission",
        "due_at": "2026-05-01T23:59:00+02:00",
        "weight": 0.20,
        "mastery_gap": 35,
        "priority": 71,
        "source": "moodle",
    },
    {
        "deadline_id": "dl-adl-paper",
        "course_id": "IN2349",
        "title": "Paper Review — Attention Is All You Need",
        "due_at": "2026-04-28T23:59:00+02:00",
        "weight": 0.10,
        "mastery_gap": 19,
        "priority": 54,
        "source": "moodle",
    },
]


_DE_MONTHS: dict[str, int] = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}

_IS_DUE_SUFFIX = re.compile(r"\s+is\s+due$", re.IGNORECASE)


def _parse_german_date(text: str) -> str:
    """Best-effort parse of Moodle's German locale dates into ISO 8601.

    Handles patterns like "Freitag, 1. Mai, 23:59" and
    "Mittwoch, 28. April 2026, 23:59".
    """
    try:
        return datetime.fromisoformat(text).isoformat()
    except (ValueError, TypeError):
        pass

    cleaned = text.strip().rstrip(".")
    nums = re.findall(r"\d+", cleaned)
    lower = cleaned.lower()
    month = 0
    for name, num in _DE_MONTHS.items():
        if name in lower:
            month = num
            break

    if not month or not nums:
        return text

    day = int(nums[0])
    year_candidates = [int(n) for n in nums if len(n) == 4]
    year = year_candidates[0] if year_candidates else datetime.now().year

    hour, minute = 23, 59
    time_match = re.search(r"(\d{1,2}):(\d{2})", cleaned)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))

    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Europe/Berlin"))
        return dt.isoformat()
    except (ValueError, OverflowError):
        return text


def _clean_title(title: str) -> str:
    """Strip Moodle UI suffixes like 'is due' from event titles."""
    return _IS_DUE_SUFFIX.sub("", title).strip()


def _make_deadline_id(title: str, due_at: str) -> str:
    """Deterministic ID from title + due date."""
    return "dl-" + hashlib.sha256(f"{title}|{due_at}".encode()).hexdigest()[:12]


def _extract_course_code(course_name: str) -> str:
    """Try to pull a TUM-style course code (e.g. 'IN2064') from a course name."""
    match = re.search(r"\b([A-Z]{2}\d{4})\b", course_name)
    return match.group(1) if match else course_name[:20]


def _compute_priority(due_at_str: str) -> int:
    """Heuristic priority based on time until due. Closer = higher."""
    try:
        due = datetime.fromisoformat(due_at_str)
        now = datetime.now(UTC)
        days_left = max((due - now).total_seconds() / 86400, 0)
        if days_left <= 1:
            return 98
        if days_left <= 3:
            return 90
        if days_left <= 7:
            return 75
        if days_left <= 14:
            return 60
        return 40
    except (ValueError, TypeError):
        return 50


async def _scrape_deadlines_from_calendar(
    context: BrowserContext,
) -> list[dict[str, Any]]:
    """Scrape the Moodle upcoming calendar view for deadline events."""
    page = await context.new_page()
    try:
        await page.goto(CALENDAR_UPCOMING_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        deadlines: list[dict[str, Any]] = []
        event_blocks = page.locator(".event")
        count = await event_blocks.count()
        logger.info("moodle_calendar_events_found", count=count)

        for i in range(count):
            block = event_blocks.nth(i)
            try:
                title_sel = ".name, h3, .referer a, a[href*='calendar/view.php']"
                title_el = block.locator(title_sel).first
                title = (await title_el.inner_text()).strip() if await title_el.count() > 0 else ""
                if not title:
                    continue

                date_el = block.locator(".date, .col-11, time").first
                date_text = ""
                if await date_el.count() > 0:
                    date_text = (
                        await date_el.get_attribute("datetime")
                        or (await date_el.inner_text()).strip()
                    )

                course_sel = ".course, .text-muted a, a[href*='course/view.php']"
                course_el = block.locator(course_sel).first
                course_name = ""
                if await course_el.count() > 0:
                    course_name = (await course_el.inner_text()).strip()

                course_code = _extract_course_code(course_name) if course_name else "UNKNOWN"
                title = _clean_title(title)
                due_at = _parse_german_date(date_text) if date_text else ""
                priority = _compute_priority(due_at)

                deadlines.append({
                    "deadline_id": _make_deadline_id(title, due_at),
                    "course_id": course_code,
                    "title": title,
                    "due_at": due_at,
                    "weight": 0.0,
                    "mastery_gap": 0,
                    "priority": priority,
                    "source": "moodle",
                })
            except Exception:
                logger.warning("moodle_calendar_event_parse_error", index=i, exc_info=True)
                continue

        return sorted(deadlines, key=lambda d: d.get("due_at", ""))
    finally:
        await page.close()


async def get_deadlines(
    *,
    student_id: str,
    course_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return upcoming deadlines scraped from Moodle's calendar.

    Falls back to mock data when TUM credentials are not configured or
    Moodle is unreachable.

    Args:
        student_id: Student identifier (logged for tracing).
        course_id: Optional course code filter (e.g. "IN2064").

    Returns:
        List of deadline dicts sorted by `due_at`.
    """
    settings = get_settings()

    if not settings.tum_username or not settings.tum_password:
        logger.info(
            "moodle_deadlines_fallback_mock",
            reason="no_credentials",
            student_id=student_id,
        )
        return _filter_deadlines(_MOCK_DEADLINES, course_id)

    session_dir = Path(settings.moodle_session_dir)
    try:
        pw, context = await _ensure_browser_context(session_dir)
        try:
            await _ensure_logged_in(context, session_dir)
            deadlines = await _scrape_deadlines_from_calendar(context)
            logger.info(
                "moodle_deadlines_scraped",
                student_id=student_id,
                count=len(deadlines),
            )
            await _save_session(context, session_dir)
            if not deadlines:
                logger.info("moodle_deadlines_empty_fallback_mock")
                return _filter_deadlines(_MOCK_DEADLINES, course_id)
            return _filter_deadlines(deadlines, course_id)
        finally:
            await context.close()
            await pw.stop()
    except Exception:
        logger.warning("moodle_deadlines_scrape_failed_fallback_mock", exc_info=True)
        return _filter_deadlines(_MOCK_DEADLINES, course_id)


def _filter_deadlines(
    deadlines: list[dict[str, Any]],
    course_id: str | None,
) -> list[dict[str, Any]]:
    if course_id is None:
        return sorted(deadlines, key=lambda d: d.get("due_at", ""))
    return sorted(
        [d for d in deadlines if d.get("course_id") == course_id],
        key=lambda d: d.get("due_at", ""),
    )


async def get_uploads(moodle_course_id: str) -> list[dict[str, Any]]:
    """Fetch recent uploads/resources from a specific course page."""
    settings = get_settings()
    session_dir = Path(settings.moodle_session_dir)

    pw, context = await _ensure_browser_context(session_dir)
    try:
        await _ensure_logged_in(context, session_dir)

        page = await context.new_page()
        course_url = f"{MOODLE_BASE}/course/view.php?id={moodle_course_id}"
        await page.goto(course_url, wait_until="domcontentloaded")

        uploads: list[dict[str, Any]] = []
        resource_links = page.locator(
            "a[href*='/mod/resource/view.php'], "
            "a[href*='/mod/folder/view.php'], "
            "a[href*='/pluginfile.php']"
        )
        count = await resource_links.count()
        seen_urls: set[str] = set()

        for i in range(count):
            link = resource_links.nth(i)
            href = await link.get_attribute("href") or ""
            if href in seen_urls or not href:
                continue
            seen_urls.add(href)
            name = (await link.inner_text()).strip()
            if not name or len(name) < 2:
                continue
            uploads.append(
                {
                    "filename": name,
                    "url": href,
                    "moodle_course_id": moodle_course_id,
                }
            )

        logger.info("moodle_uploads_fetched", course_id=moodle_course_id, count=len(uploads))
        await page.close()
        await _save_session(context, session_dir)
        return uploads
    finally:
        await context.close()
        await pw.stop()


