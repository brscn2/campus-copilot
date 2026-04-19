"""End-to-end test for TUM library room booking via anny.eu.

Run from repo root:
    uv run python scripts/test_library_booking.py

Walks through the full flow: list branches -> search rooms -> book -> verify -> QR.
Set HEADLESS=0 to watch the browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _pp(label: str, data: object) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if isinstance(data, (dict, list)):
        sanitized = json.loads(json.dumps(data, default=str))
        for k, v in (sanitized.items() if isinstance(sanitized, dict) else enumerate(sanitized)):
            if isinstance(v, str) and len(v) > 200:
                v = v[:200] + "... (truncated)"
            print(f"  {k}: {v}")
    else:
        print(f"  {data}")
    print()


async def main() -> None:
    from src.config import get_settings
    from src.lib.anny_browser import (
        book_room,
        close_browser,
        list_branches,
        scrape_rooms_and_slots,
        verify_booking,
    )

    settings = get_settings()
    username = settings.tum_username
    password = settings.tum_password

    if not username or not password:
        print("ERROR: TUM_USERNAME / TUM_PASSWORD not set in .env")
        return

    print(f"Using TUM account: {username}")
    print("Starting browser automation...\n")

    try:
        # --- Step 1: List branches ---
        print("Step 1: Listing library branches...")
        branches = await list_branches()
        _pp("Available Branches", branches)

        # --- Step 2: Search rooms ---
        branch = "mathematics-informatics"
        print(f"Step 2: Searching rooms at '{branch}'...")
        rooms_data = await scrape_rooms_and_slots(
            username=username,
            password=password,
            branch_slug=branch,
        )
        _pp(f"Rooms at {branch}", {
            "branch": rooms_data.get("branch_name"),
            "month": rooms_data.get("monthText"),
            "selected_date": rooms_data.get("selectedDate"),
            "rooms": rooms_data.get("rooms", []),
            "start_times_count": len(rooms_data.get("startTimes", [])),
            "end_times_count": len(rooms_data.get("endTimes", [])),
            "first_3_starts": [t["time"] for t in rooms_data.get("startTimes", [])[:3]],
            "features": rooms_data.get("features", []),
            "description": rooms_data.get("description", ""),
            "photos": rooms_data.get("photos", []),
        })

        rooms = rooms_data.get("rooms", [])
        start_times = rooms_data.get("startTimes", [])
        end_times = rooms_data.get("endTimes", [])
        dates = [d for d in rooms_data.get("dates", []) if not d.get("disabled")]

        if not rooms:
            print("No rooms available. Exiting.")
            return
        if not start_times:
            print("No start times available. Exiting.")
            return

        # Pick first available room and time
        room_name = rooms[0]["name"]
        start = start_times[0]["time"]
        end = end_times[0]["time"] if end_times else start_times[-1]["time"]
        selected_date = rooms_data.get("selectedDate", dates[0]["day"] if dates else "21")

        print(f"Will attempt to book: {room_name} on day {selected_date}, {start}-{end}")
        proceed = input("Proceed with booking? (y/n): ").strip().lower()
        if proceed != "y":
            print("Skipped booking. Done.")
            return

        # --- Step 3: Book ---
        print(f"\nStep 3: Booking {room_name}...")
        booking = await book_room(
            username=username,
            password=password,
            branch_slug=branch,
            room_name=room_name,
            date_day=selected_date,
            start_time=start,
            end_time=end,
            num_persons=3,
        )
        _pp("Booking Result", booking)

        if booking.get("status") != "confirmed":
            print(f"Booking not confirmed (status={booking.get('status')}). Stopping here.")
            return

        # --- Step 4: Verify booking ---
        manage_url = booking.get("manage_url")
        if manage_url:
            print("Step 4: Verifying booking...")
            verification = await verify_booking(
                username=username,
                password=password,
                booking_url=manage_url,
            )
            _pp("Verification", verification)
        else:
            print("No manage_url returned; skipping verification.")

        # --- Show QR and calendar info ---
        if booking.get("qr_code_base64"):
            print("QR code captured (base64 PNG, starts with):")
            print(f"  {booking['qr_code_base64'][:80]}...")
        else:
            print("No QR code captured.")

        if booking.get("ics_data"):
            print("\nICS calendar data captured:")
            print(f"  {booking['ics_data'][:200]}...")
        elif booking.get("calendar_link"):
            print(f"\nCalendar download link: {booking['calendar_link']}")
        else:
            print("No calendar data captured.")

        print("\nDone! Check your anny.eu bookings to confirm.")

    finally:
        await close_browser()


if __name__ == "__main__":
    asyncio.run(main())
