"""Playwright-based ZHS browser automation.

Handles login, course discovery, slot scraping, and booking.

ZHS has two page types:
- /courses/.../offers/{slug} — weekly paid courses (add to cart, user completes checkout)
- /product-offers/{uuid} — free play timeslots (fully automated checkout, it's free)
"""

from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.exceptions import TUMAuthenticationError, TUMSystemUnavailableError
from src.lib.logging import get_logger

logger = get_logger(__name__)

ZHS_BASE = "https://kurse.zhs-muenchen.de"
ZHS_OFFERS = f"{ZHS_BASE}/de/muenchen"

_browser: Browser | None = None
_context: BrowserContext | None = None
_lock = asyncio.Lock()
_logged_in = False

_visible_browser: Browser | None = None
_visible_context: BrowserContext | None = None
_visible_logged_in = False


async def _ensure_browser(*, headless: bool = True) -> BrowserContext:
    """Launch browser and create context if not already running."""
    global _browser, _context, _visible_browser, _visible_context

    if headless:
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

    if _visible_context is not None:
        return _visible_context
    pw = await async_playwright().start()
    _visible_browser = await pw.chromium.launch(headless=False)
    _visible_context = await _visible_browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    return _visible_context


async def _login(page: Page, username: str, password: str) -> None:
    """Perform TUM Shibboleth login on ZHS."""
    global _logged_in

    await page.goto(f"{ZHS_BASE}/auth/login", wait_until="networkidle", timeout=30000)

    submitted: bool = await page.evaluate("""() => {
        const form = document.querySelector('form');
        if (!form) return false;
        const input = document.createElement('input');
        input.type = 'hidden'; input.name = 'provider'; input.value = 'oidc-tum';
        form.appendChild(input); form.submit(); return true;
    }""")
    if not submitted:
        raise TUMSystemUnavailableError("Cannot find Kratos login form")

    try:
        await page.wait_for_selector("#username", timeout=25000)
    except Exception:
        await page.wait_for_timeout(5000)
        try:
            await page.wait_for_selector("#username", timeout=15000)
        except Exception as exc:
            raise TUMSystemUnavailableError(f"TUM IdP login form not found: {exc}") from exc

    await page.locator("#username").fill(username)
    await page.locator("#password").fill(password)
    await page.locator("button[type='submit'], input[type='submit']").first.click()

    try:
        await page.wait_for_url(f"**/{ZHS_BASE.split('//')[1]}/**", timeout=30000)
    except Exception:
        await page.wait_for_timeout(5000)

    current = page.url
    if "login" in current.lower() and "tum.de" in current.lower():
        raise TUMAuthenticationError("Invalid TUM credentials")

    _logged_in = True
    logger.info("zhs_browser_login_success")


async def _get_page(username: str, password: str, *, headless: bool = True) -> Page:
    """Get an authenticated page, logging in if needed."""
    global _visible_logged_in
    async with _lock:
        ctx = await _ensure_browser(headless=headless)
        page = await ctx.new_page()

        needs_login = (headless and not _logged_in) or (not headless and not _visible_logged_in)
        if needs_login:
            await _login(page, username, password)
            if not headless:
                _visible_logged_in = True

        return page


# ---------------------------------------------------------------------------
# Search & navigation
# ---------------------------------------------------------------------------


async def search_and_get_course_page(
    *,
    username: str,
    password: str,
    course_name: str,
) -> tuple[Page, str]:
    """Search for a course and navigate to its page.

    Returns the page and the kind of URL found.  ZHS has two page layouts:
    - ``/courses/.../offers/`` — weekly paid courses
    - ``/product-offers/`` — free play timeslots
    """
    page = await _get_page(username, password)

    try:
        await page.goto(ZHS_OFFERS, wait_until="networkidle", timeout=20000)

        search_input = page.locator(
            '[id="searchbox-offer-list-searchbar"] input, '
            'input[placeholder*="Search"], input[placeholder*="Suche"]'
        )
        await search_input.fill(course_name)
        await page.wait_for_timeout(1000)

        # Collect all result links (courses AND product-offers)
        result_links = page.locator(
            'a[href*="/courses/"][href*="/offers/"], a[href*="/product-offers/"]'
        )
        count: int = await result_links.count()
        if count == 0:
            raise TUMSystemUnavailableError(f"No results found for '{course_name}'")

        # Free play offerings have both a /courses/ link (empty page) and a
        # /product-offers/ link (actual timeslots). Detect by name keywords.
        name_lower = course_name.lower()
        is_free_play = "freies spiel" in name_lower or "flatrate" in name_lower
        product_link = page.locator('a[href*="/product-offers/"]')
        course_link = page.locator('a[href*="/courses/"][href*="/offers/"]')

        if is_free_play and await product_link.count():
            await product_link.first.click()
        elif await course_link.count():
            await course_link.first.click()
        else:
            await result_links.first.click()
        await page.wait_for_load_state("networkidle", timeout=15000)

        return page, page.url

    except TUMSystemUnavailableError:
        await page.close()
        raise
    except Exception as exc:
        await page.close()
        raise TUMSystemUnavailableError(
            f"Failed to search for course '{course_name}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

_SCRAPE_WEEKLY_JS = """() => {
    const data = { type: 'weekly_course', courses: [], title: '' };
    const h1 = document.querySelector('h1');
    if (h1) data.title = h1.textContent.trim();

    function parseCard(card, i) {
        const c = { index: i };
        const hl = card.querySelector('[slot="headline"]');
        if (hl) c.name = hl.textContent.trim();

        const dateEl = card.querySelector(
            '[data-testid^="date-course-list-item-"],' +
            '[data-testid^="date-course-list-expired-item-"]'
        );
        if (dateEl) c.date_range = dateEl.textContent.trim();

        const timeEl = card.querySelector(
            '[data-testid^="weekday-time-course-list-item-"],' +
            '[data-testid^="weekday-time-course-list-expired-item-"]'
        );
        if (timeEl) c.schedule = timeEl.textContent.trim();

        const locEl = card.querySelector(
            '[data-testid^="location-course-list-item-"],' +
            '[data-testid^="location-course-list-expired-item-"]'
        );
        if (locEl) c.location = locEl.textContent.trim();

        const entries = card.querySelectorAll('[data-testid="card-entry"]');
        entries.forEach(pe => {
            const n = pe.querySelector('dt span');
            const v = pe.querySelector('dd span');
            if (n && v) {
                const t = n.textContent.trim();
                if (t.includes('Studierende') && !c.price)
                    c.price = v.textContent.trim();
                if (t.includes('Leader') || t.includes('Kursleitung'))
                    c.leader = v.textContent.trim();
            }
        });

        // Determine status from cart container data-state
        const container = card.querySelector(
            '[data-testid^="add-to-cart-button-container-"]'
        );
        if (container) {
            c.status = container.getAttribute('data-state') || 'unknown';
        }

        // Book button (available courses)
        const bookBtn = card.querySelector('[data-testid^="book-now-button-"]');
        if (bookBtn) {
            c.book_button_testid = bookBtn.getAttribute('data-testid');
            c.disabled = bookBtn.disabled;
        }

        // Waitlist button
        const wlBtn = card.querySelector(
            '[data-testid^="add-to-waiting-list-"]'
        );
        if (wlBtn) {
            c.waitlist_button_testid = wlBtn.getAttribute('data-testid');
        }

        // Already on waitlist
        const rmWlBtn = card.querySelector(
            '[data-testid^="remove-from-waiting-list-"]'
        );
        if (rmWlBtn) {
            c.status = 'already_on_waitlist';
        }

        // Already in cart
        const descEl = card.querySelector(
            '[data-testid$="-description"]'
        );
        if (descEl) {
            const desc = descEl.textContent.trim();
            if (desc.includes('Warenkorb')) c.status = 'in_cart';
        }

        return c;
    }

    // Active courses
    const activeCards = document.querySelectorAll(
        '[data-testid^="course-list-item-"]'
    );
    let idx = 0;
    activeCards.forEach(card => {
        const c = parseCard(card, idx++);
        if (!c.status) c.status = 'unknown';
        data.courses.push(c);
    });

    // Expired courses (separate list)
    const expiredCards = document.querySelectorAll(
        '[data-testid^="course-list-expired-item-"]'
    );
    expiredCards.forEach(card => {
        const c = parseCard(card, idx++);
        c.status = 'booking_expired';
        data.courses.push(c);
    });

    return data;
}"""

_SCRAPE_PRODUCT_OFFER_JS = """() => {
    const data = { type: 'free_play', slots: [], title: '', product_name: '' };
    const h1 = document.querySelector('[data-testid="product-offer-name"]');
    if (h1) data.title = h1.textContent.trim();

    const h3 = document.querySelector('[data-testid="h3"]');
    if (h3) data.product_name = h3.textContent.trim();

    // Slots are grouped in 3-day columns
    const columns = document.querySelectorAll('.grid > .col-span-1');
    columns.forEach(col => {
        // Day header: <p class="text-light-grey-500">Dienstag</p>
        const pEls = col.querySelectorAll('p');
        let dayName = '', dayDate = '';
        pEls.forEach(p => {
            const text = p.textContent.trim();
            // Short heuristic: day names are short; date has a dot
            if (text.includes('.') && text.length < 20) dayDate = text;
            else if (text.length < 15 && !text.includes(':')) dayName = text;
        });

        const slotBtns = col.querySelectorAll('[data-testid^="slot-list-"] button');
        slotBtns.forEach(btn => {
            const slot = { day: dayName, date: dayDate, id: btn.id || '' };
            const tEl = btn.querySelector('[data-testid$="-time"]');
            if (tEl) slot.time = tEl.textContent.trim();
            const dEl = btn.querySelector('[data-testid$="-description"]');
            if (dEl) slot.description = dEl.textContent.trim();
            slot.disabled = btn.disabled;
            slot.available = !btn.disabled &&
                !((slot.description || '').toLowerCase().includes('warenkorb')) &&
                !((slot.description || '').toLowerCase().includes('abgelaufen'));
            data.slots.push(slot);
        });

        // Empty-day message
        const notice = col.querySelector('[data-testid="notification-card"]');
        if (notice && slotBtns.length === 0) {
            data.slots.push({
                day: dayName, date: dayDate, time: '', id: '',
                description: notice.textContent.trim().replace(/\\s+/g, ' '),
                disabled: true, available: false,
            });
        }
    });
    return data;
}"""


async def scrape_course_details(page: Page) -> dict[str, Any]:
    """Scrape course info from a course page.

    Detects whether the page is a weekly-course offer or a free-play
    product-offer and uses the appropriate extraction logic.
    """
    url = page.url
    is_product_offer = "/product-offers/" in url

    if is_product_offer:
        result: dict[str, Any] = await page.evaluate(_SCRAPE_PRODUCT_OFFER_JS)
    else:
        active: int = await page.locator('[data-testid^="course-list-item-"]').count()
        expired: int = await page.locator('[data-testid^="course-list-expired-item-"]').count()
        if active > 0 or expired > 0:
            result = await page.evaluate(_SCRAPE_WEEKLY_JS)
        else:
            result = {
                "type": "unknown",
                "title": "",
                "courses": [],
                "slots": [],
                "message": "",
            }
            h1 = page.locator("h1")
            if await h1.count():
                result["title"] = (await h1.first.text_content() or "").strip()
            hint = page.locator('[data-testid="hint-empty"]')
            if await hint.count():
                result["message"] = (await hint.text_content() or "").strip()
            title_lower = result["title"].lower()
            if "free" in title_lower or "frei" in title_lower:
                result["type"] = "free_play"

    result["url"] = url
    return result


async def scrape_product_offer_all_days(
    page: Page,
    *,
    days_ahead: int = 6,
) -> dict[str, Any]:
    """Scrape a product-offer page across multiple 3-day windows.

    Clicks the "next 3 days" button to accumulate slots for ``days_ahead`` days.
    """
    all_slots: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    base_result: dict[str, Any] = await page.evaluate(_SCRAPE_PRODUCT_OFFER_JS)
    for s in base_result.get("slots", []):
        if s["id"] and s["id"] not in seen_ids:
            seen_ids.add(s["id"])
            all_slots.append(s)

    next_btn = page.locator('button:has-text("select next"), button:has-text("nächsten")')
    steps = days_ahead // 3
    for _ in range(steps):
        if not await next_btn.count():
            break
        await next_btn.first.click()
        await page.wait_for_timeout(1200)
        chunk: dict[str, Any] = await page.evaluate(_SCRAPE_PRODUCT_OFFER_JS)
        for s in chunk.get("slots", []):
            if s["id"] and s["id"] not in seen_ids:
                seen_ids.add(s["id"])
                all_slots.append(s)

    base_result["slots"] = all_slots
    base_result["url"] = page.url
    return base_result


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


async def _complete_free_play_checkout(page: Page) -> dict[str, Any]:
    """Complete checkout for free play slots (fully automated — it's free).

    Flow: slot click → "In den Warenkorb" (save-button) →
    "Zur Kasse" (save-button reused) → /payments/checkout →
    Weiter → checkbox → confirm → success
    """
    try:
        save_btn = page.locator('[data-testid="save-button"]:visible')
        await save_btn.wait_for(state="visible", timeout=8000)

        # Step 1: "In den Warenkorb"
        await save_btn.click()
        await page.wait_for_timeout(1500)

        # Step 2: "Zur Kasse"
        zur_kasse = page.locator('[data-testid="save-button"]:visible')
        await zur_kasse.wait_for(state="visible", timeout=8000)
        await zur_kasse.click()
        await page.wait_for_load_state("networkidle", timeout=15000)
        await page.wait_for_timeout(1500)

        # Step 3: Weiter
        weiter = page.locator('[data-testid="submit-user-form-button"]:visible')
        if await weiter.count():
            await weiter.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            await page.wait_for_timeout(1500)

        # Step 4: Terms checkbox
        checkbox = page.locator("#condition_acceptance")
        if await checkbox.count():
            await checkbox.check()
            await page.wait_for_timeout(500)

        # Step 5: Confirm
        confirm = page.locator('[data-testid="submit-consent-form-button"]')
        if await confirm.count():
            await confirm.click()
            await page.wait_for_timeout(4000)

        if "success" in page.url:
            return {
                "status": "booked",
                "message": "Free play slot booked successfully!",
                "url": page.url,
            }

        return {
            "status": "booked",
            "message": "Checkout completed. Check your ZHS account.",
            "url": page.url,
        }

    except Exception as exc:
        logger.error("zhs_free_play_checkout_failed", exc_info=True)
        return {
            "status": "error",
            "message": f"Checkout failed: {exc}",
            "url": page.url,
        }


async def _add_to_cart_and_handoff(
    page: Page,
    *,
    username: str,
    password: str,
) -> dict[str, Any]:
    """Add a weekly course to cart, then open a visible browser for user checkout.

    Weekly courses may require course-specific forms (certificates, language
    proficiency, etc.) so we let the user finish checkout themselves.
    """
    try:
        save_btn = page.locator('[data-testid="save-button"]:visible')
        await save_btn.wait_for(state="visible", timeout=8000)
        await save_btn.click()
        await page.wait_for_timeout(2000)

        await page.close()

        # Open a visible browser at pre-checkout for the user to finish
        visible_page = await _get_page(username, password, headless=False)
        await visible_page.goto(
            f"{ZHS_BASE}/de/pre-checkout", wait_until="networkidle", timeout=20000
        )

        return {
            "status": "in_cart",
            "message": (
                "Course added to cart. A browser window has been opened "
                "for you to complete checkout."
            ),
            "checkout_url": f"{ZHS_BASE}/de/pre-checkout",
        }

    except Exception as exc:
        logger.error("zhs_add_to_cart_failed", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to add to cart: {exc}",
        }


async def book_free_play_slot(page: Page, *, slot_id: str) -> dict[str, Any]:
    """Click a free play slot button and complete checkout."""
    btn = page.locator(f'[id="{slot_id}"]')

    if not await btn.count():
        return {"status": "error", "message": f"Slot '{slot_id}' not found on page"}

    if await btn.is_disabled():
        return {"status": "error", "message": "Slot is not available for booking"}

    await btn.click()
    await page.wait_for_timeout(1000)
    return await _complete_free_play_checkout(page)


async def book_weekly_course(
    page: Page,
    *,
    course_index: int = 0,
    username: str,
    password: str,
) -> dict[str, Any]:
    """Add a weekly course to cart and open a visible browser for checkout.

    Weekly courses may need course-specific forms (certificates, language
    proficiency, etc.) so the user completes checkout themselves.

    Handles six course states:
    - available → add to cart, open browser for user
    - join_waiting_list → click button, confirm in modal, done
    - already_in_cart → open browser at pre-checkout directly
    - already_on_waitlist → inform user
    - booked_out → error
    - booking_expired → error
    """
    idx = course_index

    # 1. Try "In den Warenkorb" (available)
    book_btn = page.locator(f'[data-testid="book-now-button-course-list-item-0-{idx}"]')
    if await book_btn.count() and not await book_btn.is_disabled():
        await book_btn.click()
        await page.wait_for_timeout(1000)
        return await _add_to_cart_and_handoff(page, username=username, password=password)

    # 2. Try "Warteliste beitreten" (join waitlist)
    # Waitlist flow: click button → modal appears → click save-button → done
    wl_btn = page.locator(f'[data-testid="add-to-waiting-list-course-list-item-0-{idx}"]')
    if await wl_btn.count() and not await wl_btn.is_disabled():
        await wl_btn.click()
        await page.wait_for_timeout(2000)
        save_btn = page.locator('[data-testid="save-button"]:visible')
        if await save_btn.count():
            await save_btn.click()
            await page.wait_for_timeout(2000)
        # Verify we're now on the waitlist
        rm_btn = page.locator(
            f'[data-testid="remove-from-waiting-list-course-list-item-0-{idx}"]'
        )
        if await rm_btn.count():
            return {
                "status": "joined_waitlist",
                "message": "Successfully joined the waiting list! "
                "You will be notified when a spot opens.",
            }
        return {
            "status": "joined_waitlist",
            "message": "Waitlist request submitted. Check your ZHS account for confirmation.",
        }

    # 3. Already on waitlist
    rm_wl = page.locator(f'[data-testid="remove-from-waiting-list-course-list-item-0-{idx}"]')
    if await rm_wl.count():
        return {
            "status": "already_on_waitlist",
            "message": "You are already on the waiting list for this course.",
        }

    # 4. Already in cart — just open browser at cart
    container = page.locator(
        f'[data-testid="add-to-cart-button-container-course-list-item-0-{idx}"]'
    )
    if await container.count():
        state: str = await container.get_attribute("data-state") or "unknown"
        if state == "already_in_cart":
            await page.close()
            visible_page = await _get_page(username, password, headless=False)
            await visible_page.goto(
                f"{ZHS_BASE}/de/pre-checkout", wait_until="networkidle", timeout=20000
            )
            return {
                "status": "in_cart",
                "message": (
                    "Course is already in your cart. A browser window has been "
                    "opened for you to complete checkout."
                ),
                "checkout_url": f"{ZHS_BASE}/de/pre-checkout",
            }
        return {
            "status": "error",
            "message": f"Cannot book: course status is '{state}'",
        }

    # 5. Expired course card
    expired = page.locator(f'[data-testid="course-list-expired-item-0-{idx}"]')
    if await expired.count():
        return {
            "status": "error",
            "message": "Cannot book: booking period has expired",
        }

    return {"status": "error", "message": "Course not found on page"}


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------


async def _navigate_to_date(page: Page, target: date) -> None:
    """Click 'next 3 days' / 'prev 3 days' until the target date is visible."""
    for _ in range(10):
        visible_text: str = await page.evaluate(
            "() => (document.querySelector('[data-testid=\"tab-content-desktop-0\"]') "
            "|| document.querySelector('main') || document.body).innerText"
        )
        day_str = f"{target.day}. "
        if day_str in visible_text:
            return

        today = date.today()
        if target > today:
            btn = page.locator('button:has-text("select next"), button:has-text("nächsten")')
        else:
            btn = page.locator(
                'button:has-text("select 3 days before"), button:has-text("vorherigen")'
            )

        if await btn.count():
            await btn.first.click()
            await page.wait_for_timeout(1200)
        else:
            break


async def get_course_info(
    *,
    username: str,
    password: str,
    course_name: str,
) -> dict[str, Any]:
    """Search for a course and return its schedule/slot details."""
    page, url = await search_and_get_course_page(
        username=username, password=password, course_name=course_name
    )
    try:
        if "/product-offers/" in url:
            return await scrape_product_offer_all_days(page, days_ahead=6)
        details: dict[str, Any] = await scrape_course_details(page)
        details["url"] = url
        return details
    finally:
        await page.close()


async def book_course(
    *,
    username: str,
    password: str,
    course_name: str,
    course_index: int = 0,
    slot_id: str | None = None,
    target_date: date | None = None,
) -> dict[str, Any]:
    """Full booking flow: search, navigate, and book."""
    page, url = await search_and_get_course_page(
        username=username, password=password, course_name=course_name
    )
    try:
        is_product = "/product-offers/" in url

        # Extract date from slot ID (format: uuid-2026-04-21T18:00:00Z-...)
        if is_product and not target_date and slot_id:
            m = re.search(r"(\d{4}-\d{2}-\d{2})T", slot_id)
            if m:
                target_date = date.fromisoformat(m.group(1))

        if is_product and target_date:
            await _navigate_to_date(page, target_date)

        if slot_id:
            result: dict[str, Any] = await book_free_play_slot(page, slot_id=slot_id)
        elif is_product:
            details = await scrape_course_details(page)
            available = [s for s in details.get("slots", []) if s.get("available")]
            if not available:
                return {"status": "error", "message": "No available slots", "details": details}
            result = await book_free_play_slot(page, slot_id=available[0]["id"])
        else:
            result = await book_weekly_course(
                page, course_index=course_index, username=username, password=password
            )

        return result
    finally:
        if not page.is_closed():
            await page.close()


async def close_browser() -> None:
    """Clean up headless browser resources. Visible browser stays open for the user."""
    global _browser, _context, _logged_in
    if _context:
        await _context.close()
        _context = None
    if _browser:
        await _browser.close()
        _browser = None
    _logged_in = False


async def close_all_browsers() -> None:
    """Clean up all browser resources including visible browser."""
    global _visible_browser, _visible_context, _visible_logged_in
    await close_browser()
    if _visible_context:
        await _visible_context.close()
        _visible_context = None
    if _visible_browser:
        await _visible_browser.close()
        _visible_browser = None
    _visible_logged_in = False
