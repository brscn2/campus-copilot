"""Warm the TheirStack job cache for the canonical Informatics persona (Europe-wide).

Run this once per day (or whenever you want fresh listings). It splits the
demo student's keywords into batches and makes multiple TheirStack calls per
kind to build a pool of ~30 jobs each. Results are written to the on-disk
cache so the UI, agent, and any pytest runs serve them for free for the next 24 h.

Free-tier credit math (default config):
  3 kinds  ×  ~3 batches  ×  THEIRSTACK_RESULTS_PER_CALL=10  ≈  90 credits per cold run.
  Free plan budget: 200 credits / month  ->  ~2 cold runs available.

Usage:
    JOBS_MODE=live uv run python scripts/warmup_jobs.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from src.config import get_settings
from src.integrations.jobs import search_jobs
from src.lib.skill_inference import derive_search_keywords

PERSONA_KEYWORDS: list[str] = derive_search_keywords(skills=[], program="Informatik")
KINDS: tuple[str, ...] = ("working_student", "internship", "new_grad")


async def _warm_one(kind: str) -> list[dict[str, object]]:
    """Issue one TheirStack call for the persona, return mapped results."""
    print(f"\n=== {kind} ===")
    rows = await search_jobs(
        kind=kind,
        keywords=PERSONA_KEYWORDS,
    )
    print(f"  fetched {len(rows)} job(s)")
    for r in rows[:3]:
        print(
            "  - {company} | {title} | {location} | {posted_at}".format(
                company=r.get("company", "?"),
                title=(r.get("title", "?") or "")[:70],
                location=r.get("location", "?"),
                posted_at=r.get("posted_at", "?"),
            )
        )
    return rows


async def main() -> int:
    settings = get_settings()
    print("TheirStack job cache warmup")
    print(f"  jobs_mode               = {settings.jobs_mode}")
    print(f"  results_per_call        = {settings.theirstack_results_per_call}")
    print(f"  cache_dir               = {settings.theirstack_cache_dir}")
    print(f"  cache_ttl_seconds       = {settings.theirstack_cache_ttl_seconds}")
    print(f"  api_key_present         = {bool(settings.theirstack_api_key)}")
    print(f"  persona.keywords        = {PERSONA_KEYWORDS}")
    print(f"  kinds                   = {list(KINDS)}")

    if settings.jobs_mode != "live":
        print(
            "\nWARNING: JOBS_MODE != 'live' — this run will only exercise mock data "
            "and will NOT prime the TheirStack disk cache.\n"
            "Set JOBS_MODE=live in .env (or inline) to actually fetch from TheirStack."
        )
    elif not settings.theirstack_api_key:
        print(
            "\nERROR: JOBS_MODE=live but THEIRSTACK_API_KEY is empty. "
            "Set THEIRSTACK_API_KEY in .env first."
        )
        return 2

    summary: dict[str, int] = {}
    for kind in KINDS:
        rows = await _warm_one(kind)
        summary[kind] = len(rows)

    estimated_credits = sum(summary.values()) if settings.jobs_mode == "live" else 0

    print("\n--- summary ---")
    print(json.dumps(summary, indent=2))
    print(f"estimated credits spent this run: {estimated_credits}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
