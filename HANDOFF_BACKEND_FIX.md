# Handoff: Fix Campus Co-Pilot backend boot failure

> Paste this entire file as your first message to the new Cursor session. It is self-contained — you do not need any prior chat context.

You are picking up a task on the **Campus Co-Pilot** repo (TUM hackathon project, multi-agent assistant for students). Read [`CLAUDE.md`](CLAUDE.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), and [`README.md`](README.md) first to understand the conventions, tech stack (Python 3.11 / FastAPI / LangGraph / uv / Ruff / mypy / pytest), and module layout. The system is already partially built; you are fixing a boot-time regression and unblocking the demo.

---

## 1. Symptom

`docker compose up -d` brings up `postgres` healthy, then `backend` exits 1 immediately:

```
dependency failed to start: container campus-copilot-backend-1 exited (1)
```

`docker compose logs backend --tail 80 --no-color` ends with:

```
File "/app/src/main.py", line 128, in <module>
    app = create_app()
File "/app/src/main.py", line 68, in create_app
    _register_routes(application)
File "/app/src/main.py", line 108, in _register_routes
    from src.api.academic import router as academic_router
File "/app/src/api/academic.py", line 10, in <module>
    from src.integrations.moodle import get_courses, get_deadlines, get_slides
ImportError: cannot import name 'get_deadlines' from 'src.integrations.moodle'
```

Single bad import in one router brings the entire FastAPI app down because `_register_routes` runs inside `create_app()` at module import time ([`src/main.py:108`](src/main.py)).

---

## 2. Root Cause

The API layer ([`src/api/academic.py`](src/api/academic.py)) was scaffolded against a *planned* Moodle surface that the real Playwright-based scraper in [`src/integrations/moodle.py`](src/integrations/moodle.py) never grew into. They drifted apart.

### What `academic.py` (scaffold) expects from `moodle`

| Imported name | Used in route | Call signature in scaffold |
|---|---|---|
| `get_courses` | `GET /academic/courses` | `get_courses(student_id="demo-student")` |
| `get_deadlines` | `GET /academic/deadlines` | `get_deadlines(student_id=..., course_id=...)` |
| `get_slides` | `GET /academic/courses/{course_id}/slides` | `get_slides(course_id=...)` |

It also imports `search_rooms` from `library` (exists, OK) and `search_thesis_opportunities` from `tumonline` (exists, OK).

### What `moodle.py` (real Playwright + TUM Shibboleth SSO scraper) actually exports

| Function | Signature | What it does |
|---|---|---|
| `get_semesters(context)` | needs a `BrowserContext` | reads the `#coc-filterterm` dropdown |
| `get_courses(semester=None)` | **no `student_id` kwarg** | scrapes the `/my/` dashboard for course tiles |
| `download_all_courses(semester=None)` | — | uses Moodle's "Download Center" to fetch numbered zips of every course's materials |
| `get_uploads(moodle_course_id)` | takes `moodle_course_id`, **not `course_id`** | lists `mod/resource`, `mod/folder`, `pluginfile.php` links on a course page |

### Specific mismatches

1. **`get_deadlines` does not exist at all.** No deadline scraping path is implemented yet.
2. **`get_slides` does not exist.** Closest equivalent is `get_uploads`, which returns *all* uploaded resources (slides, exercise sheets, folders) and uses kwarg `moodle_course_id`.
3. **`get_courses` signature mismatch.** Scaffold passes `student_id`; real function takes `semester`. Per-student scoping happens implicitly via the logged-in TUM session.
4. **Statefulness mismatch.** Real Moodle functions own their own browser context (open + close Playwright per call). The scaffold treats them like cheap stateless lookups. Each request currently triggers a full Playwright launch + login check — fine for a demo but worth knowing for performance later.

### Possible Moodle data sources still missing (deficiencies, future work)

These are reachable from a logged-in Moodle session but not yet implemented in `moodle.py`:

- **Deadlines** — `mod/assign/view.php`, `mod/quiz/view.php`, the "Upcoming events" block on `/my/`, or (much cleaner) the iCal export at `/calendar/export.php` which gives `due_at`, `title`, `course_id` for free.
- **Slides as a typed subset of uploads** — filter `get_uploads` results by file extension (`.pdf`, `.pptx`, `.key`) and/or section name containing "Lecture" / "Vorlesung" / "Slides".
- **Per-resource metadata** — uploaded date, file size, section. Currently only `filename` + `url` are returned.
- **Forum posts / announcements** — `mod/forum/view.php`, useful for "what did the TA say this week?".
- **Grades** — `grade/report/user/index.php`.
- **Course → semester mapping** — `_parse_courses_from_page` doesn't tag which semester a course belongs to.

### Other backend smell to clean up while you're in there

[`src/main.py:106–125`](src/main.py): `_register_routes` registers `health_router` and `chat_router` **twice**, and has a mid-function `from src.api.social import ...` that belongs at the top of the function. Functionally harmless (FastAPI dedups by route) but a code-review smell.

---

## 3. Your Plan

Do these in order. After each step, briefly summarize what changed before moving on.

### Step 1 — Unblock boot (pick ONE option, propose to me before coding)

- **Option A — minimal stub (recommended for hackathon):** in [`src/integrations/moodle.py`](src/integrations/moodle.py), add `async def get_deadlines(student_id: str, course_id: str | None = None) -> list[dict[str, Any]]` and `async def get_slides(course_id: str) -> list[dict[str, Any]]` that return `[]` (or a small mock list). Make `get_courses` accept an ignored `student_id` kwarg, OR fix the call site.
- **Option B — fix API to match reality:** rewrite [`src/api/academic.py`](src/api/academic.py) to call `get_courses(semester=...)` and `get_uploads(moodle_course_id=course_id)`; drop the `/deadlines` route or return HTTP 501.
- **Option C — hybrid:** stub `get_deadlines`, alias `get_slides → get_uploads` (with `.pdf|.pptx` extension filtering), fix `get_courses` kwargs in the route.

Default to Option C unless I say otherwise.

### Step 2 — Audit other routers for the same drift

Read [`src/api/career.py`](src/api/career.py) and [`src/api/social.py`](src/api/social.py). Cross-check every `from src.integrations.X import ...` against the actual exports of the corresponding integration module. Known integration exports (top-level `async def`s):

- `library.py` → `search_rooms`, `book_room`
- `tumonline.py` → `search_thesis_opportunities`, `get_professor_info`
- `jobs.py` → `search_jobs`
- `zhs.py` → `search_courses`, `register_for_course`, `set_snipe_alert`
- `mensa.py` → `get_menu`
- `esn_tumi.py` → `search_events`
- `content_pipeline.py` → `extract_all_zips`, `ingest_course`, `ingest_all_courses`, `run_full_pipeline`

Fix any mismatches the same way as Step 1.

### Step 3 — Clean `_register_routes`

In [`src/main.py`](src/main.py): deduplicate the double `include_router(health_router)` / `include_router(chat_router)` calls and lift the in-function `from src.api.social import ...` to sit alongside the other imports at the top of the function.

### Step 4 — Verify boot

```bash
docker compose down
docker compose up -d --build
docker compose logs -f backend
```

Confirm uvicorn says `Application startup complete.` and these endpoints return 200 (even if empty payloads):

```bash
curl -s http://localhost:8000/api/academic/courses | head -c 200
curl -s http://localhost:8000/api/academic/deadlines | head -c 200
curl -s "http://localhost:8000/api/academic/courses/12345/slides" | head -c 200
```

### Step 5 — Run the standard project checks

Per [`CLAUDE.md`](CLAUDE.md):

```bash
uv run ruff check . && uv run mypy src/ && uv run pytest
```

All three must be green before you declare done.

### Step 6 — Discuss follow-ups (do NOT implement yet)

Once boot is fixed, propose two follow-up tickets in chat (do not code them):

1. **Real `get_deadlines`** via Moodle's `/calendar/export.php` iCal feed (stable, gives due dates for free, no scraping fragility).
2. **Real `get_slides`** as a typed view over `get_uploads` filtered by file extension and section heuristics — decide whether to read live or read from the pre-downloaded zips that `download_all_courses` already produces.

---

## 4. Constraints

- Do **not** introduce new dependencies without asking — this is a CLAUDE.md rule.
- Do **not** edit `.env`, commit secrets, or bypass `src/lib/bedrock.py` / `src/lib/memory.py`.
- Do **not** auto-commit. Ask before committing. When you do, follow Conventional Commits (`fix:`, `chore:`, `feat:`).
- Stay inside the architecture boundaries documented in [`ARCHITECTURE.md`](ARCHITECTURE.md): `api/` is thin, integrations stay pure-function, no LLM calls inside tools.

## 5. Definition of Done

- [ ] `docker compose up -d` brings backend up cleanly, no ImportError.
- [ ] `/api/academic/courses`, `/api/academic/deadlines`, `/api/academic/courses/{id}/slides` all respond 200.
- [ ] Other routers (`career`, `social`) audited and either confirmed-clean or fixed.
- [ ] `_register_routes` deduplicated.
- [ ] `uv run ruff check . && uv run mypy src/ && uv run pytest` all green.
- [ ] Two follow-up tickets (real deadlines + real slides) summarized in chat for me to approve before any further work.
