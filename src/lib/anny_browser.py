"""Playwright-based anny.eu browser automation for TUM library room booking.

Handles TUM SSO login, branch browsing, room/timeslot scraping, and booking.

Booking flow on anny.eu:
1. Navigate to branch booking page (e.g. /book/group-rooms-mathematics-and-informatics)
2. SSO login via tum.de → redirects back with step=period&childResource=N
3. Select date, start time, end time, and room
4. Click "Book now" to confirm
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.exceptions import TUMAuthenticationError, TUMSystemUnavailableError
from src.lib.logging import get_logger

logger = get_logger(__name__)

ANNY_BASE = "https://anny.eu/en"
ANNY_ORG = "university-library-technical-university-of-munich"
ANNY_EXPLORE = f"{ANNY_BASE}/explore/{ANNY_ORG}/resources?o-v=list&o-cv=week"

BRANCH_SLUGS: dict[str, str] = {
    "chemistry": "group-rooms-chemistry",
    "main-campus": "group-study-rooms-main-campus",
    "mathematics-informatics": "group-rooms-mathematics-and-informatics",
    "medicine": "group-rooms-medicine",
    "physics": "group-rooms-physics",
    "sport-health": "group-rooms-sport-and-health-sciences",
    "weihenstephan": "group-rooms-weihenstephan",
}

BRANCH_NAMES: dict[str, str] = {
    "chemistry": "Branch Library Chemistry",
    "main-campus": "Branch Library Main Campus",
    "mathematics-informatics": "Branch Library Mathematics & Informatics",
    "medicine": "Branch Library Medicine",
    "physics": "Branch Library Physics",
    "sport-health": "Branch Library Sport & Health Sciences",
    "weihenstephan": "Branch Library Weihenstephan",
}

BRANCH_ADDRESSES: dict[str, str] = {
    "chemistry": "Lichtenbergstraße 4, 85748 Garching",
    "main-campus": "Arcisstraße 21, 80333 München",
    "mathematics-informatics": "Boltzmannstraße 3, 85748 Garching",
    "medicine": "Ismaninger Str. 22, 81675 München",
    "physics": "James-Franck-Straße 1, 85748 Garching",
    "sport-health": "Georg-Brauchle-Ring 60, 80992 München",
    "weihenstephan": "Maximus-von-Imhof-Forum 3, 85354 Freising",
}

_browser: Browser | None = None
_context: BrowserContext | None = None
_lock = asyncio.Lock()
_logged_in = False


def _read_file(path: str) -> str | None:
    """Sync file read for use with asyncio.to_thread."""
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return None


async def _ensure_browser() -> BrowserContext:
    """Launch browser and create context if not already running."""
    global _browser, _context

    if _context is not None:
        return _context
    pw = await async_playwright().start()
    _browser = await pw.chromium.launch(headless=True)
    _context = await _browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    return _context


async def _login_tum_sso(page: Page, username: str, password: str) -> None:
    """Handle TUM Shibboleth SSO on the TUM IdP login page."""
    try:
        await page.wait_for_selector("#username", timeout=20000)
    except Exception as exc:
        raise TUMSystemUnavailableError(f"TUM IdP login form not found: {exc}") from exc

    await page.locator("#username").fill(username)
    await page.locator("#password").fill(password)
    await page.locator("button[type='submit'], input[type='submit']").first.click()

    try:
        await page.wait_for_url("**/anny.eu/**", timeout=30000)
    except Exception:
        await page.wait_for_timeout(5000)

    if "login.tum.de" in page.url:
        raise TUMAuthenticationError("Invalid TUM credentials")


async def _login_anny_sso(page: Page, username: str, password: str) -> None:
    """Full anny.eu SSO login: anny login page → TUM SSO → back to anny."""
    global _logged_in

    await page.goto(f"{ANNY_BASE}/login", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(1000)

    sso_link = page.locator("text=Log in with SSO")
    if await sso_link.count() > 0:
        await sso_link.click()
        await page.wait_for_timeout(1000)
        await page.locator("input[placeholder*='e.g.']").fill("tum.de")
        await page.locator("button:has-text('NEXT')").click()
        await page.wait_for_url("**/login.tum.de/**", timeout=15000)
        await _login_tum_sso(page, username, password)
    elif "login.tum.de" in page.url:
        await _login_tum_sso(page, username, password)

    _logged_in = True
    logger.info("anny_browser_login_success")


async def _get_page(username: str, password: str) -> Page:
    """Get an authenticated page, logging in if needed."""
    async with _lock:
        ctx = await _ensure_browser()
        page = await ctx.new_page()

        if not _logged_in:
            await _login_anny_sso(page, username, password)

        return page


async def _navigate_to_branch(
    page: Page,
    branch_slug: str,
    username: str,
    password: str,
) -> None:
    """Navigate to a branch booking page and handle SSO if needed."""
    url = f"{ANNY_BASE}/book/{BRANCH_SLUGS.get(branch_slug, branch_slug)}"
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)

    # If we landed on the page but need to click "Log In (Studierende)"
    login_btn = page.locator("button:has-text('Log In (Studierende)')")
    if await login_btn.count() > 0:
        await login_btn.click()
        await page.wait_for_timeout(2000)

        if "login.tum.de" in page.url:
            await _login_tum_sso(page, username, password)
            await page.wait_for_url("**/anny.eu/**", timeout=30000)
        elif "anny.eu" in page.url and "login" in page.url:
            await _login_anny_sso(page, username, password)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await login_btn.click()
            await page.wait_for_timeout(3000)

    # Wait for booking panel to appear
    try:
        await page.wait_for_selector("[aria-label='Booking panel']", timeout=15000)
    except Exception:
        await page.wait_for_timeout(3000)


_SCRAPE_ROOMS_JS = """() => {
    const panel = document.querySelector("[aria-label='Booking panel']");
    if (!panel) return { rooms: [], startTimes: [], endTimes: [] };

    // Scrape rooms from the custom dropdown (class: a-child-resource-select)
    // The dropdown items contain "Name | capacity" patterns
    const sel = '.a-child-resource-select__item, ' +
        '[class*="child-resource"] [class*="item"]';
    const dropdownItems = Array.from(panel.querySelectorAll(sel));
    let rooms = dropdownItems
        .map(item => {
            const text = item.textContent.trim();
            const match = text.match(/^(.+?)\\s*\\|\\s*(.+)$/);
            if (!match) return null;
            return {
                name: match[1].trim(),
                capacity_text: match[2].trim(),
                capacity: parseInt((match[2].match(/(\\d+)/) || [0, 0])[1]),
                selected: item.classList.contains("selected") ||
                          item.getAttribute("aria-selected") === "true",
            };
        })
        .filter(Boolean);

    // Fallback: read the currently selected room from the trigger
    if (rooms.length === 0) {
        const trigger = panel.querySelector('.a-child-resource-select__trigger');
        if (trigger) {
            const text = trigger.textContent.trim();
            const match = text.match(/^(.+?)\\s*\\|\\s*(.+)$/);
            if (match) {
                rooms = [{
                    name: match[1].trim(),
                    capacity_text: match[2].trim(),
                    capacity: parseInt((match[2].match(/(\\d+)/) || [0, 0])[1]),
                    selected: true,
                }];
            }
        }
    }

    // Also check for role="option" items with pipe in text
    if (rooms.length === 0) {
        const opts = Array.from(panel.querySelectorAll('[role="option"]'));
        rooms = opts
            .map(opt => {
                const text = opt.textContent.trim().replace(/^Save\\s*/, '');
                const match = text.match(/^(.+?)\\s*\\|\\s*(.+)$/);
                if (!match) return null;
                return {
                    name: match[1].trim(),
                    capacity_text: match[2].trim(),
                    capacity: parseInt((match[2].match(/(\\d+)/) || [0, 0])[1]),
                    selected: opt.getAttribute('aria-selected') === 'true',
                };
            })
            .filter(Boolean);
    }

    // Rooms available count
    const bodyText = document.body.innerText;
    const availMatch = bodyText.match(/(\\d+) Rooms? available/);
    const roomsAvailable = availMatch ? parseInt(availMatch[1]) : rooms.length;

    // Scrape start/end time options from listboxes or UL lists
    const listboxes = Array.from(panel.querySelectorAll('[role="listbox"]'));
    let startTimes = [];
    let endTimes = [];
    if (listboxes.length >= 2) {
        startTimes = Array.from(listboxes[0].querySelectorAll('[role="option"]'))
            .map(opt => ({
                time: opt.textContent.trim(),
                selected: opt.getAttribute('aria-selected') === 'true',
            }));
        endTimes = Array.from(listboxes[1].querySelectorAll('[role="option"]'))
            .map(opt => ({
                time: opt.textContent.trim(),
                selected: opt.getAttribute('aria-selected') === 'true',
            }));
    }
    // Fallback: scrollable UL lists
    if (startTimes.length === 0) {
        const uls = Array.from(panel.querySelectorAll('ul'));
        const scrollUls = uls.filter(ul => {
            const s = window.getComputedStyle(ul);
            return s.overflowY === 'auto' || s.overflowY === 'scroll';
        });
        if (scrollUls.length >= 2) {
            startTimes = Array.from(scrollUls[0].querySelectorAll('li')).map(li => ({
                time: li.textContent.trim(),
                selected: li.classList.contains('selected') ||
                          li.getAttribute('aria-selected') === 'true',
            }));
            endTimes = Array.from(scrollUls[1].querySelectorAll('li')).map(li => ({
                time: li.textContent.trim(),
                selected: li.classList.contains('selected') ||
                          li.getAttribute('aria-selected') === 'true',
            }));
        }
    }

    // Scrape selected date
    const selectedCell = panel.querySelector('[role="gridcell"][aria-selected="true"]');
    const selectedDate = selectedCell ? selectedCell.textContent.trim() : null;

    // Scrape available dates
    const dateCells = Array.from(panel.querySelectorAll('[role="gridcell"]'));
    const dates = dateCells.map(cell => ({
        day: cell.textContent.trim(),
        selected: cell.getAttribute('aria-selected') === 'true',
        disabled: cell.getAttribute('aria-disabled') === 'true',
    }));

    // Get month header
    const monthBtn = panel.querySelector('button');
    const monthText = monthBtn ? monthBtn.textContent.trim() : '';

    // Scrape features from the page body (left panel, outside booking panel)
    const features = [];
    const tagEls = document.querySelectorAll('[class*="tag"], [class*="badge"], [class*="chip"]');
    tagEls.forEach(el => {
        const txt = el.textContent.trim();
        if (txt && ['Outlets', 'WiFi', 'Whiteboard', 'Touchscreen', 'Accessible'].some(
            f => txt.includes(f)
        )) {
            features.push(txt);
        }
    });
    // Broader fallback: look for feature text near the branch info
    if (features.length === 0) {
        const featureKeywords = ['Outlets', 'WiFi', 'Whiteboard', 'Touchscreen', 'Accessible'];
        featureKeywords.forEach(kw => {
            if (bodyText.includes(kw)) features.push(kw);
        });
    }

    // Scrape description from page body (outside panel)
    const mainContent = document.querySelector('main') || document.body;
    const allPs = Array.from(mainContent.querySelectorAll('p'));
    const descP = allPs.find(p => {
        const t = p.textContent.trim();
        return t.length > 30 && !t.includes('cookie') && !t.includes('Cookie');
    });
    const description = descP ? descP.textContent.trim() : '';

    // Scrape photos
    const photos = Array.from(document.querySelectorAll('img'))
        .map(img => img.src)
        .filter(src =>
            src.includes('anny') &&
            !src.includes('logo') &&
            !src.includes('icon') &&
            !src.includes('svg')
        );

    return {
        rooms, roomsAvailable, startTimes, endTimes,
        selectedDate, dates, monthText,
        features, description, photos,
    };
}"""


async def list_branches() -> list[dict[str, str]]:
    """Return the known TUM library branches with booking slugs."""
    return [
        {
            "slug": slug,
            "name": BRANCH_NAMES[slug],
            "address": BRANCH_ADDRESSES.get(slug, ""),
            "booking_url": f"{ANNY_BASE}/book/{url_slug}",
        }
        for slug, url_slug in BRANCH_SLUGS.items()
    ]


async def scrape_rooms_and_slots(
    *,
    username: str,
    password: str,
    branch_slug: str,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Navigate to a branch and scrape available rooms and time slots.

    Args:
        username: TUM username.
        password: TUM password.
        branch_slug: Branch key (e.g. 'mathematics-informatics').
        target_date: Optional date to select (day number, e.g. '21').

    Returns:
        Dict with rooms, startTimes, endTimes, dates, and branch info.
    """
    page = await _get_page(username, password)

    try:
        await _navigate_to_branch(page, branch_slug, username, password)

        # Select target date if specified
        if target_date:
            date_cell = page.locator(f"[role='gridcell']:has-text('{target_date}')")
            if await date_cell.count() > 0:
                await date_cell.first.click()
                await page.wait_for_timeout(1500)

        # Expand the room dropdown so all room options are visible
        room_dropdown = page.locator(
            ".a-child-resource-select__trigger, [class*='child-resource-select'] [role='button']"
        )
        if await room_dropdown.count() > 0:
            await room_dropdown.first.click()
            await page.wait_for_timeout(1500)

        data: dict[str, Any] = await page.evaluate(_SCRAPE_ROOMS_JS)
        data["branch_slug"] = branch_slug
        data["branch_name"] = BRANCH_NAMES.get(branch_slug, branch_slug)
        data["branch_address"] = BRANCH_ADDRESSES.get(branch_slug, "")
        data["url"] = page.url

        return data

    finally:
        await page.close()


async def book_room(
    *,
    username: str,
    password: str,
    branch_slug: str,
    room_name: str,
    date_day: str,
    start_time: str,
    end_time: str,
    num_persons: int = 3,
) -> dict[str, Any]:
    """Book a specific room at a branch library (full two-step checkout).

    Step 1: Select date, time, room, click "Book now"
    Step 2: Select number of persons, click "Complete booking"
    Then: Parse success page, extract manage-booking link and QR code.

    Args:
        username: TUM username.
        password: TUM password.
        branch_slug: Branch key (e.g. 'mathematics-informatics').
        room_name: Room name to select (e.g. 'Group Room 1').
        date_day: Day number to click (e.g. '21').
        start_time: Start time (e.g. '10:00').
        end_time: End time (e.g. '12:00').
        num_persons: Number of persons for the booking (3-8, default 3).

    Returns:
        Dict with status, message, booking details, and optional qr_code_base64.
    """
    page = await _get_page(username, password)

    try:
        await _navigate_to_branch(page, branch_slug, username, password)

        # --- Step 1: Select date/time/room ---

        # 1. Select date
        date_cell = page.locator(f"[role='gridcell']:has-text('{date_day}')")
        if await date_cell.count() == 0:
            return {"status": "error", "message": f"Date {date_day} not available in calendar"}
        await date_cell.first.click()
        await page.wait_for_timeout(1500)

        # 2. Select start time (listbox options or scrollable UL li items)
        start_option = page.locator(
            f"[role='listbox'] >> nth=0 >> [role='option']:has-text('{start_time}')"
        )
        if await start_option.count() == 0:
            start_option = page.locator(
                f"[aria-label='Booking panel'] ul li:has-text('{start_time}')"
            ).first
        if await start_option.count() == 0:
            return {"status": "error", "message": f"Start time {start_time} not available"}
        await start_option.first.scroll_into_view_if_needed()
        await start_option.first.click()
        await page.wait_for_timeout(1000)

        # 3. Select end time
        end_option = page.locator(
            f"[role='listbox'] >> nth=1 >> [role='option']:has-text('{end_time}')"
        )
        if await end_option.count() == 0:
            end_option = page.locator(
                f"[aria-label='Booking panel'] ul >> nth=1 >> li:has-text('{end_time}')"
            )
        if await end_option.count() == 0:
            return {"status": "error", "message": f"End time {end_time} not available"}
        await end_option.first.scroll_into_view_if_needed()
        await end_option.first.click()
        await page.wait_for_timeout(1000)

        # 4. Select room via the custom dropdown
        room_dropdown = page.locator(
            ".a-child-resource-select__trigger, [class*='child-resource-select'] [role='button']"
        )
        if await room_dropdown.count() > 0:
            await room_dropdown.first.click()
            await page.wait_for_timeout(1000)

        # Try dropdown items first, then role="option"
        room_option = page.locator(
            f".a-child-resource-select__item:has-text('{room_name}'), "
            f"[class*='child-resource'] [class*='item']:has-text('{room_name}')"
        )
        if await room_option.count() == 0:
            room_option = page.locator(f"[role='option']:has-text('{room_name}')")
        if await room_option.count() == 0:
            return {"status": "error", "message": f"Room '{room_name}' not found"}
        await room_option.first.click()
        await page.wait_for_timeout(1000)

        # 5. Click "Book now" inside the booking panel → Step 2 (checkout)
        panel = page.locator("[aria-label='Booking panel']")
        book_btn = panel.locator("button:has-text('Book now')")
        if await book_btn.count() == 0:
            book_btn = page.locator("button:has-text('Book now')").first
        if await book_btn.count() == 0:
            return {"status": "error", "message": "Book now button not found"}
        await book_btn.first.click()
        await page.wait_for_timeout(3000)

        # --- Step 2: Checkout (number of persons + complete booking) ---

        # 6. Select number of persons from the v-select dropdown
        persons_str = str(num_persons)
        persons_btn = page.locator(
            ".v-select button[aria-haspopup='true'], button.selected-options[aria-haspopup='true']"
        )
        if await persons_btn.count() > 0:
            # Get the popover ID from aria-controls, then click the trigger
            popover_id = await persons_btn.first.get_attribute("aria-controls")
            await persons_btn.first.click()
            await page.wait_for_timeout(1000)

            # Scope option search to the dropdown popover
            if popover_id:
                container = page.locator(f"#{popover_id}")
                person_opt = container.locator(f"li:has-text('{persons_str}')")
            else:
                person_opt = page.locator(
                    f".v-select li:has-text('{persons_str}'), "
                    f".dropdown-menu li:has-text('{persons_str}')"
                )
            if await person_opt.count() > 0:
                await person_opt.first.click()
                await page.wait_for_timeout(1000)
            else:
                logger.warning("persons_option_not_found", num_persons=num_persons)
        else:
            logger.warning("persons_dropdown_not_found")

        # 7. Click "Complete booking"
        complete_btn = page.locator("button:has-text('Complete booking')")
        if await complete_btn.count() == 0:
            complete_btn = page.locator("button:has-text('Confirm'), button:has-text('Book now')")
        if await complete_btn.count() > 0:
            await complete_btn.first.click()
            await page.wait_for_timeout(4000)

        # --- Step 3: Parse success page ---

        current_url = page.url
        page_text = await page.inner_text("body")

        is_success = "step=success" in current_url or any(
            kw in page_text.lower()
            for kw in ["successfully", "booked", "reservation confirmed", "booking confirmed"]
        )

        if not is_success:
            error_el = page.locator("[role='alert'], .alert-danger, .error-message")
            if await error_el.count() > 0:
                error_text = await error_el.first.inner_text()
                if len(error_text.strip()) < 200:
                    return {"status": "error", "message": f"Booking failed: {error_text}"}
            return {
                "status": "pending",
                "message": f"Booking submitted for {room_name}. Verify at anny.eu.",
                "branch": BRANCH_NAMES.get(branch_slug, branch_slug),
                "room": room_name,
                "date_day": date_day,
                "start_time": start_time,
                "end_time": end_time,
                "num_persons": num_persons,
                "checkout_url": current_url,
            }

        # Extract booking ID from URL
        booking_id = None
        id_match = re.search(r"childResource=(\d+)", current_url)
        if id_match:
            booking_id = id_match.group(1)

        result: dict[str, Any] = {
            "status": "confirmed",
            "message": (
                f"Successfully booked {room_name} on day {date_day} "
                f"from {start_time} to {end_time} for {num_persons} persons"
            ),
            "branch": BRANCH_NAMES.get(branch_slug, branch_slug),
            "room": room_name,
            "date_day": date_day,
            "start_time": start_time,
            "end_time": end_time,
            "num_persons": num_persons,
            "booking_id": booking_id,
            "url": current_url,
        }

        # --- Step 4: Add to calendar (.ics download) ---
        cal_link = page.locator(
            "a:has-text('Add to calendar'), "
            "button:has-text('Add to calendar'), "
            "a:has-text('Add to Calendar'), "
            "button:has-text('Add to Calendar')"
        )
        if await cal_link.count() > 0:
            href = await cal_link.first.get_attribute("href")
            if href:
                full_url = href if href.startswith("http") else f"{ANNY_BASE}{href}"
                result["calendar_link"] = full_url
            try:
                async with page.expect_download(timeout=5000) as dl_info:
                    await cal_link.first.click()
                download = await dl_info.value
                ics_path = await download.path()
                if ics_path:
                    ics_content = await asyncio.to_thread(_read_file, str(ics_path))
                    if ics_content:
                        result["ics_data"] = ics_content
            except Exception:
                logger.info("calendar_download_skipped", reason="no download triggered")

        # --- Step 5: Navigate to manage booking and extract QR code ---
        manage_link = page.locator("a:has-text('Manage booking')")
        if await manage_link.count() > 0:
            await manage_link.first.click()
            await page.wait_for_timeout(3000)

            qr_data = await _extract_qr_code(page)
            if qr_data:
                result["qr_code_base64"] = qr_data
            result["manage_url"] = page.url

        return result

    except TUMAuthenticationError:
        raise
    except TUMSystemUnavailableError:
        raise
    except Exception as exc:
        logger.error("anny_booking_error", branch=branch_slug, room=room_name, exc_info=True)
        return {"status": "error", "message": f"Booking failed: {exc}"}
    finally:
        await page.close()


async def _extract_qr_code(page: Page) -> str | None:
    """Extract QR code from a canvas element as base64 PNG."""
    try:
        canvas = page.locator("canvas")
        if await canvas.count() == 0:
            return None
        data: str = await page.evaluate("""() => {
            const c = document.querySelector('canvas');
            return c ? c.toDataURL('image/png') : null;
        }""")
        return data
    except Exception:
        logger.warning("qr_code_extraction_failed", exc_info=True)
        return None


async def verify_booking(
    *,
    username: str,
    password: str,
    booking_url: str,
) -> dict[str, Any]:
    """Navigate to a booking manage page and verify its status.

    Args:
        username: TUM username.
        password: TUM password.
        booking_url: Full manage booking URL from the booking result.

    Returns:
        Dict with booking status, details, and QR code if available.
    """
    page = await _get_page(username, password)

    try:
        await page.goto(booking_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        page_text = await page.inner_text("body")

        status = "unknown"
        if "upcoming" in page_text.lower():
            status = "upcoming"
        elif "cancelled" in page_text.lower():
            status = "cancelled"
        elif "completed" in page_text.lower():
            status = "completed"
        elif "confirmed" in page_text.lower():
            status = "confirmed"

        qr_data = await _extract_qr_code(page)

        return {
            "status": status,
            "qr_code_base64": qr_data,
            "url": page.url,
        }

    except Exception as exc:
        logger.error("verify_booking_error", url=booking_url, exc_info=True)
        return {"status": "error", "message": f"Failed to verify booking: {exc}"}
    finally:
        await page.close()


async def close_browser() -> None:
    """Close the anny.eu browser instance."""
    global _browser, _context, _logged_in

    if _context is not None:
        await _context.close()
        _context = None
    if _browser is not None:
        await _browser.close()
        _browser = None
    _logged_in = False
