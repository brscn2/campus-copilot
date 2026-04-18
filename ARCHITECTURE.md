# ARCHITECTURE.md — Campus Co-Pilot Blueprint

> Read this before making any structural change: adding a new agent, creating a new top-level directory, changing how data flows between layers, or introducing a new external system. If your change doesn't fit the patterns here, update this file in the same PR.

---

## 1. Guiding Principles

1. **Agents are brains; tools are hands.** LLM reasoning happens in graph nodes. I/O happens in tools. Never mix them.
2. **The Calendar Orchestrator is the spine.** Availability is not an afterthought — it's how agents avoid stepping on each other.
3. **Cognee first, live system second.** If the student has already asked about it, the answer is in the knowledge graph. Hitting TUMonline on every query is slow and brittle.
4. **Human-in-the-loop for irreversible actions.** Drafts get surfaced to the user; the user presses send.
5. **Thin FastAPI, fat agents.** Routes are <30 lines. Business logic lives in the agent graphs.
6. **One responsibility per module.** If you can't summarize a file's purpose in one sentence, split it.

---

## 2. Directory Structure

```
campus-copilot/
├── README.md                 # Why. See it for project purpose.
├── CLAUDE.md                 # How Claude Code should behave in this repo.
├── ARCHITECTURE.md           # This file — structural blueprint.
├── pyproject.toml            # uv-managed dependencies, Ruff + mypy config.
├── .env.example              # Every required env var, dummy values.
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── main.py               # FastAPI app, global exception handler, route registration.
│   ├── config.py             # Pydantic Settings. One Settings instance, imported everywhere.
│   ├── exceptions.py         # All custom exception classes.
│   │
│   ├── api/                  # FastAPI routes. THIN — no business logic.
│   │   ├── __init__.py
│   │   ├── chat.py           # POST /chat (SSE streaming), main conversational entrypoint.
│   │   ├── academic.py       # REST endpoints for Academic tab (courses, deadlines, thesis).
│   │   ├── career.py         # REST endpoints for Career tab.
│   │   ├── social.py         # REST endpoints for Social tab.
│   │   ├── calendar.py       # REST endpoints for Calendar view + priority settings.
│   │   └── auth.py           # TUM credential submission + OAuth callbacks.
│   │
│   ├── orchestrator/         # The top-level agent.
│   │   ├── __init__.py
│   │   ├── graph.py          # LangGraph definition: router → agent(s) → aggregator.
│   │   ├── router.py         # Haiku-powered intent classifier.
│   │   ├── aggregator.py     # Merges multi-agent outputs into a single response.
│   │   └── prompts.py
│   │
│   ├── agents/               # One subdirectory per specialist agent. Same shape each.
│   │   ├── __init__.py
│   │   ├── base.py           # AgentInput, AgentOutput, BaseAgent protocol.
│   │   │
│   │   ├── academic/
│   │   │   ├── __init__.py
│   │   │   ├── graph.py      # LangGraph for this agent.
│   │   │   ├── state.py      # TypedDict / Pydantic state passed between nodes.
│   │   │   ├── tools.py      # Pure-function tools (no LLM calls inside).
│   │   │   ├── prompts.py    # Prompt templates as module constants.
│   │   │   └── repl.py       # `python -m src.agents.academic.repl` for debugging.
│   │   │
│   │   ├── career/           # Same shape as academic/
│   │   └── social/           # Same shape as academic/
│   │
│   ├── calendar/             # The spine. Called by every agent.
│   │   ├── __init__.py
│   │   ├── orchestrator.py   # Conflict detection + resolution logic.
│   │   ├── google.py         # Google Calendar API wrapper.
│   │   └── priorities.py     # Student-defined priority model (exam > sports > social).
│   │
│   ├── integrations/         # Adapters for external systems. One file per system.
│   │   ├── __init__.py
│   │   ├── moodle.py         # Slide downloads, deadline scraping.
│   │   ├── tumonline.py      # Exams, course registration, transcript.
│   │   ├── library.py        # Study room search + booking.
│   │   ├── zhs.py            # Sports registration + sniper.
│   │   ├── mensa.py          # Daily menu fetch.
│   │   ├── esn_tumi.py       # ESN + TUMi event feeds.
│   │   └── luma.py           # Reply workshops + Luma event matching.
│   │
│   ├── lib/                  # Cross-cutting infrastructure. No domain logic.
│   │   ├── __init__.py
│   │   ├── bedrock.py        # The ONE Bedrock client. All LLM calls go here.
│   │   ├── memory.py         # Cognee + S3 Vectors abstraction.
│   │   ├── credentials.py    # KMS-encrypted TUM credential storage.
│   │   ├── logging.py        # structlog setup + PII redaction.
│   │   ├── retry.py          # tenacity-based retry decorators.
│   │   └── sse.py            # Server-sent event helpers for streaming.
│   │
│   ├── models/               # Pydantic models for domain entities.
│   │   ├── __init__.py
│   │   ├── student.py
│   │   ├── course.py
│   │   ├── mastery.py
│   │   ├── deadline.py
│   │   ├── thesis.py
│   │   ├── job.py
│   │   ├── booking.py
│   │   └── calendar_event.py
│   │
│   └── storage/              # Persistence layer.
│       ├── __init__.py
│       ├── db.py             # SQLAlchemy async engine + session factory.
│       ├── schema.py         # SQLAlchemy ORM models (mirror models/ where applicable).
│       └── repositories/     # One repo per entity. Thin wrappers over SQLAlchemy.
│
├── tests/
│   ├── conftest.py           # Shared fixtures: mock Bedrock, mock Cognee, test DB.
│   ├── unit/
│   │   ├── test_tools_academic.py
│   │   ├── test_tools_career.py
│   │   └── ...
│   ├── integration/
│   │   ├── test_agent_academic.py       # Runs full graph with mocked Bedrock.
│   │   └── test_orchestrator.py
│   └── e2e/
│       └── test_chat_flow.py            # Hits FastAPI with TestClient end-to-end.
│
└── scripts/                  # One-off utilities. Not imported by src/.
    ├── seed_mock_student.py
    └── ingest_moodle_slides.py
```

**Rules about this structure:**
- `src/api/` never imports from `integrations/` directly — it goes through an agent.
- `src/agents/*/tools.py` is the only place that imports from `integrations/`.
- `src/lib/` imports nothing from `src/` outside itself. It is the foundation.
- `src/models/` imports nothing from `src/` outside `lib/`. Models are leaf nodes.
- Circular imports are a design failure. If you hit one, the dependency graph is wrong — fix the graph, don't paper over with local imports.

---

## 3. State Management & Data Flow

### Request lifecycle for a chat message

```
User types in frontend
   │
   ▼
POST /chat (FastAPI, SSE response)
   │
   ▼
Orchestrator.router  ──────► Haiku classifies intent → {agent: "academic", action: "find_thesis"}
   │
   ▼
Orchestrator dispatches to Academic Agent's graph
   │
   ▼
Academic Agent state machine:
   retrieve_context (Cognee) → plan (Sonnet) → execute_tools → reflect → respond
   │                                                  │
   │                                                  ▼
   │                                          Tools call integrations/
   │                                          (moodle, tumonline, library, ...)
   ▼
Proposed actions collected
   │
   ▼
Calendar Orchestrator validates & resolves conflicts
   │
   ▼
Aggregator formats response
   │
   ▼
SSE stream back to frontend (events: "thinking", "tool_call", "draft_ready", "final")
```

### State rules

- **Inside a LangGraph run:** state is a Pydantic model or TypedDict, passed between nodes. Never use module-level mutables.
- **Across requests:** persistent state lives in Postgres (via SQLAlchemy) or Cognee. Never in-process memory.
- **Session state (conversation history):** stored in Postgres, keyed by `session_id`. Last N turns hydrated on each request; older context summarized and pushed to Cognee.
- **Configuration:** one `Settings` instance from `src/config.py`. Import it; do not re-read env vars elsewhere.
- **No globals.** If you find yourself writing `GLOBAL_CACHE = {}`, stop — use a repository + the DB.

### Frontend ↔ backend contract

- REST endpoints return JSON matching Pydantic response models in `src/models/` — the frontend's TypeScript types mirror these.
- `/chat` is SSE. Event types:
  - `thinking` — intermediate "agent is working" message for UI
  - `tool_call` — agent is invoking a tool; includes tool name + arguments for transparency
  - `draft_ready` — human-in-the-loop approval needed; payload is the draft
  - `action_complete` — booking/email/etc confirmed
  - `final` — conversation turn ended

---

## 4. Database Schema (SQLAlchemy)

We are using Postgres for durable state. Use SQLAlchemy 2.0 async. Every table has `id: UUID`, `created_at: timestamptz`, `updated_at: timestamptz`. Mirror Pydantic models in `src/models/` — the ORM schema is an implementation detail, the Pydantic model is the contract.

```python
# src/storage/schema.py (abbreviated, shows the shape)

class Student(Base):
    __tablename__ = "students"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tum_email: Mapped[str] = mapped_column(unique=True, index=True)
    display_name: Mapped[str]
    program: Mapped[str]                 # e.g. "Informatics, B.Sc."
    semester: Mapped[int]
    priorities: Mapped[dict] = mapped_column(JSONB)   # ordered list of categories
    google_calendar_token: Mapped[bytes] = mapped_column(LargeBinary)  # KMS-encrypted
    tum_credentials: Mapped[bytes] = mapped_column(LargeBinary)        # KMS-encrypted

class Course(Base):
    __tablename__ = "courses"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("students.id"))
    code: Mapped[str]                    # "IN2064"
    title: Mapped[str]
    moodle_id: Mapped[str | None]
    tumonline_id: Mapped[str | None]

class Lecture(Base):
    __tablename__ = "lectures"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str]
    slide_s3_key: Mapped[str | None]
    summary: Mapped[str | None]          # populated by Academic Agent
    reviewed: Mapped[bool] = mapped_column(default=False)   # student toggles this

class QuizResult(Base):
    __tablename__ = "quiz_results"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lecture_id: Mapped[UUID] = mapped_column(ForeignKey("lectures.id"))
    score: Mapped[float]                 # 0.0 – 1.0
    questions: Mapped[list[dict]] = mapped_column(JSONB)

class Deadline(Base):
    __tablename__ = "deadlines"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str]
    due_at: Mapped[datetime]
    weight: Mapped[float]                # normalized exam/grade contribution
    source: Mapped[str]                  # "moodle" | "tumonline" | "manual"
    priority_score: Mapped[float]        # computed by Academic Agent

class ThesisOpportunity(Base):
    __tablename__ = "thesis_opportunities"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    chair: Mapped[str]
    professor_name: Mapped[str]
    professor_email: Mapped[str]
    topic: Mapped[str]
    description: Mapped[str]
    match_score: Mapped[float | None]
    source_url: Mapped[str]

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company: Mapped[str]
    title: Mapped[str]
    kind: Mapped[str]                    # "working_student" | "internship" | "new_grad"
    description: Mapped[str]
    source_url: Mapped[str]
    match_score: Mapped[float | None]

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("students.id"))
    kind: Mapped[str]                    # "study_room" | "zhs" | "event" | "lunch"
    external_ref: Mapped[str | None]     # ID returned by the external system
    status: Mapped[str]                  # "pending" | "confirmed" | "failed"
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    payload: Mapped[dict] = mapped_column(JSONB)    # kind-specific details
    calendar_event_id: Mapped[str | None]           # Google Calendar event ID

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("students.id"))
    turns: Mapped[list[dict]] = mapped_column(JSONB)    # [{role, content, ts}, ...]
```

**Schema rules:**
- All timestamps are `timestamptz`. Store UTC. Convert at the edges.
- Foreign keys always have an index (SQLAlchemy does this by default for `ForeignKey`).
- Use JSONB for shape-variable payloads (quiz questions, booking details) — don't create a table per variant.
- Soft deletes only where audit trails matter (bookings, sessions). Everything else: hard delete.
- Migrations: Alembic. Every schema change has a migration in `alembic/versions/`.

---

## 5. Adding a New Agent

If the challenge scope grows (e.g., a "Finance Agent" for BAföG tracking), follow this recipe exactly:

1. Create `src/agents/<name>/` with the five standard files: `graph.py`, `state.py`, `tools.py`, `prompts.py`, `repl.py`.
2. Define your state model in `state.py` — a Pydantic model, not a raw dict.
3. Write tools in `tools.py`. Each tool is `async`, fully typed, and returns either a primitive, a Pydantic model, or a structured error dict.
4. Write prompts in `prompts.py` as module constants.
5. Build the LangGraph in `graph.py`. Expose `async def run(input: AgentInput) -> AgentOutput`.
6. Register the agent in `src/orchestrator/router.py` so the intent classifier can route to it.
7. Add integration tests in `tests/integration/test_agent_<name>.py` with mocked Bedrock.
8. Update this file's directory tree.

---

## 6. Adding a New External Integration

1. New file in `src/integrations/<system>.py`.
2. Async client class with explicit method names (`fetch_slides`, `book_slot`). No `do_stuff(action=...)` dispatch methods.
3. Wrap every external call in the retry decorator from `src/lib/retry.py`.
4. Raise a domain-specific exception from `src/exceptions.py` on failure — never let `httpx.HTTPError` leak to callers.
5. If the integration needs credentials, add them to `.env.example` and document in `README.md`.
6. Add a `tests/unit/test_integration_<system>.py` with `httpx.MockTransport`.

---

## 7. Performance & Cost Notes for the Demo

- **Haiku for routing.** A top-level Opus call per request is a credit bonfire.
- **Cache thesis scrapes.** Chair pages don't change hourly — 24h TTL in S3 is fine.
- **Stream everything.** The demo looks instant if tokens are flowing; a 6-second buffered response feels broken.
- **Pre-warm Cognee** for the demo student before the pitch. Cold retrieval is slow.

---

## 8. What Not To Do

- Don't add a new top-level directory without updating this file.
- Don't put LLM calls inside tool functions.
- Don't store state in module globals.
- Don't catch `Exception` broadly anywhere.
- Don't bypass `src/lib/bedrock.py` or `src/lib/memory.py`.
- Don't auto-send emails, auto-submit bookings without explicit user approval, or auto-register for anything that has a cost attached.
- Don't ship a file over ~400 lines. Split.
