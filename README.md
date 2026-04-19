# Campus Co-Pilot Suite

**3rd Place — TUM.ai Makeathon 2026 (Reply Challenge: The Campus Co-Pilot Suite)**

An autonomous AI chief-of-staff for TUM students. Built in ~36 hours by a team of 4. Campus Co-Pilot collapses the fragmented maze of TUMonline, Moodle, ZHS, Mensa, Luma, and SerpAPI into a single conversational interface that **acts** on behalf of the student -- booking sports slots, matching jobs to your profile via a knowledge graph, generating quizzes from lecture slides, and keeping everything in sync with Google Calendar.

---

## Why This Exists

Today's TUM student acts as a human API: manually scraping deadlines from half a dozen portals, copying them into calendars, racing bots for sports registrations, and browsing job boards without knowing which roles actually match their coursework. Systems don't talk to each other, so students miss deadlines, double-book themselves, and lose hours a week to pure administrative friction.

Campus Co-Pilot gives that time back. A student says *"book basketball free play for Tuesday evening"* and the system searches ZHS, finds available slots, and offers to complete the booking. Or *"find me jobs matching my ML background"* and it fetches real listings from Google Jobs, ingests them into a knowledge graph, and ranks them against the student's actual courses, grades, and skills from TUMonline.

This is not a chatbot. It is an **orchestrating multi-agent system** whose output is **concrete action in the real world**.

---

## What's Working

| Feature | Status | How |
|---|---|---|
| **Student profile** | Real data | TUMonline API -- grades, courses, lectures, identity |
| **Skill inference** | Real data | Haiku classifies skills from course descriptions |
| **Course sync** | Real data | Moodle Playwright scraper -> S3 -> Postgres |
| **Quiz generation** | Working | Bedrock Sonnet generates from cognified course PDFs |
| **Flashcard generation** | Working | Same pipeline, spaced-repetition ratings |
| **Job Scout** | Live | SerpAPI Google Jobs -> Cognee knowledge graph matching |
| **CV Audit** | Working | PDF upload -> Sonnet analysis with flags + suggestions |
| **ZHS Sports** | Live | Real-time schedule fetch, Playwright booking flow |
| **ESN TUMi events** | Live | Scraped event listings with search |
| **Mensa menu** | Live | Daily canteen menus with dietary filters |
| **Luma events** | Live | Munich career/tech events |
| **Thesis matcher** | Working | Profile-aware matching with draft outreach emails |
| **Deadlines** | Working | Moodle deadlines with priority scoring |
| **Calendar** | Working | Google Calendar sync, conflict detection |
| **Chat orchestrator** | Working | Routes to Academic/Career/Social agents via Bedrock |
| **File progress tracking** | Working | Per-student completion with mastery computation |

---

## Architecture

```
                         Next.js 14 Frontend
            Dashboard | Academic | Career | Social | Calendar
                              |
                         REST + SSE
                              |
                      FastAPI Backend (async)
                              |
              +---------------+---------------+
              |               |               |
         Academic         Career          Social
          Agent            Agent           Agent
         (LangGraph)     (LangGraph)     (LangGraph)
              |               |               |
              +-------+-------+-------+-------+
                      |               |
                 Orchestrator    Calendar Sync
                      |
         +------------+------------+------------+
         |            |            |            |
    AWS Bedrock   Cognee Cloud   TUM Systems   AWS S3
    Sonnet 4.6    Knowledge      TUMonline     Slides
    Haiku 4.5     Graph + RAG    Moodle        Quizzes
    Titan Embed                  ZHS/Mensa     Flashcards
```

---

## Tech Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui |
| Backend | Python 3.11, FastAPI, LangGraph, Pydantic v2, structlog |
| LLM | AWS Bedrock -- Claude Sonnet 4.6 (reasoning), Haiku 4.5 (routing/classification), Titan Embed v2 |
| Knowledge graph | Cognee Cloud -- course content, job matching, student memory |
| Job search | SerpAPI Google Jobs (live listings from StepStone, Indeed, LinkedIn) |
| Web automation | Playwright (Moodle scraping, ZHS booking) |
| Storage | AWS S3 (PDFs, quizzes, flashcards), Postgres 16 (sessions, progress, files) |
| Calendar | Google Calendar API (OAuth 2.0) |
| Package manager | uv |

---

## Getting Started

```bash
# Prerequisites: Python 3.11+, uv, Node.js 18+, pnpm, Docker
git clone https://github.com/brscn2/campus-copilot.git
cd campus-copilot

# Setup
cp .env.example .env          # fill in AWS, Cognee, SerpAPI, TUM credentials
docker compose up -d postgres  # start Postgres
uv sync                        # install Python deps
uv run alembic upgrade head    # run DB migrations

# Backend
uv run uvicorn src.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && pnpm install && pnpm dev

# Open http://localhost:3000
```

---

## Agents

**Academic Agent** -- Moodle course sync, lecture/exercise file tracking with completion checkboxes, quiz generation from cognified PDFs (multi-concept, difficulty-mixed), flashcard generation with spaced-repetition ratings, mastery computation (weighted: lectures 20%, exercises 30%, quizzes 35%, flashcards 15%), deadline queue with priority scoring, thesis matching with profile-aware Cognee search.

**Career Agent** -- TUMonline profile with inferred skills, SerpAPI job search (working student / internship / new grad) ingested into Cognee knowledge graph for semantic matching against student profile, CV audit via Sonnet with actionable suggestions, Luma Munich event discovery.

**Social Agent** -- ZHS sports course search and real-time schedule fetching with Playwright booking, ESN TUMi event search, Mensa daily menu with dietary filters, lunch coordination.

**Orchestrator** -- Bedrock-powered intent classification routes messages to the right specialist agent. Maintains session history in Postgres. Queries Cognee student memory for cross-session context.

---

## Team

Built by Samet Degirmenci, Baris Can, Arved, and Emir.

---

## License

MIT
