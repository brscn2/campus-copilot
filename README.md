# Campus Co-Pilot Suite

**An autonomous AI chief-of-staff for TUM students.**

Built for the Reply Challenge at the TUM Makeathon. Campus Co-Pilot collapses the fragmented maze of TUMonline, Moodle, the Library portal, ZHS, Mensa, and a dozen other platforms into a single conversational interface that **acts** on behalf of the student — booking rooms, drafting emails to professors, sniping ZHS sports slots the second they open, and keeping everything in sync with Google Calendar.

---

## Why This Exists

Today's TUM student acts as a human API: manually scraping deadlines from half a dozen portals, copying them into calendars, racing bots for sports registrations, and drafting the same cold emails to professors from scratch every time. Systems don't talk to each other, so students miss deadlines, double-book themselves, and lose hours a week to pure administrative friction.

Campus Co-Pilot gives that time back. Instead of "open five tabs and reconcile," a student says *"find me a quiet study room near Mathematik at 2 PM, summarize today's new Moodle slides, and draft an email to Prof. Schmidt about her open thesis on graph neural networks"* — and the system does it.

This is not a chatbot. It is an **orchestrating multi-agent system** whose output is **concrete action in the real world**.

---

## Who It's For

- TUM students (undergrad and graduate) juggling coursework, career development, and a social life
- Anyone who has ever missed a ZHS climbing slot because the tab didn't refresh fast enough
- Students looking for thesis opportunities but not sure how to cold-email a professor without sounding like a bot

The architecture is deliberately TUM-specific for the hackathon, but the pattern (orchestrator + specialist agents over fragmented bureaucratic systems) generalizes to any university, enterprise, or government workflow.

---

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Next.js Frontend (v0-generated UI, shadcn/ui, Tailwind)      │
│  Dashboard · Academic · Career · Social · Calendar · Chat     │
└──────────────────────────┬────────────────────────────────────┘
                           │  REST + SSE streaming
┌──────────────────────────▼────────────────────────────────────┐
│  FastAPI Backend (Python 3.11, async)                         │
│                                                               │
│  ┌──────────────── Orchestrator Agent ────────────────────┐   │
│  │  Intent routing · Conflict resolution · Aggregation    │   │
│  └─────┬───────────────┬───────────────┬──────────────────┘   │
│        │               │               │                      │
│  ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐                │
│  │ Academic  │   │  Career   │   │  Social   │                │
│  │  Agent    │   │   Agent   │   │   Agent   │                │
│  └─────┬─────┘   └─────┬─────┘   └─────┬─────┘                │
│        │               │               │                      │
│  ┌─────▼───────────────▼───────────────▼─────┐                │
│  │        Calendar Orchestrator (spine)      │                │
│  └───────────────────────────────────────────┘                │
└──────┬────────────────────────┬──────────────────────────┬────┘
       │                        │                          │
┌──────▼──────┐         ┌───────▼───────┐        ┌─────────▼────┐
│ AWS Bedrock │         │ Cognee Cloud  │        │ TUM Systems  │
│ Claude Opus │         │ Knowledge     │        │ TUMonline    │
│ Claude Sonnet│         │ Graph + RAG   │        │ Moodle       │
│ Claude Haiku │         │               │        │ Library      │
│ Titan Embed  │         │               │        │ ZHS · Mensa  │
└──────────────┘         └───────────────┘        └──────────────┘
                                   │
                         ┌─────────▼───────┐
                         │  AWS S3 / S3V   │
                         │  Files + Vecs   │
                         └─────────────────┘
```

**Data flow in one sentence:** The frontend sends a user message to `/chat`, the Orchestrator routes it to one or more specialist agents, each agent retrieves context from Cognee + live TUM systems, reasons with a Bedrock-hosted Claude model, proposes actions, the Calendar Orchestrator resolves any conflicts, human-in-the-loop confirmations are requested where required, and the result streams back to the UI as SSE events.

---

## Tech Stack Summary

- **Frontend:** Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui (scaffolded with v0)
- **Backend:** Python 3.11, FastAPI, LangGraph, Pydantic v2, structlog
- **AI:** AWS Bedrock — Claude Opus 4.6, Sonnet 4.6, Haiku 4.5; Titan Embeddings v2
- **Memory & retrieval:** Cognee Cloud (primary), S3 Vectors (fallback)
- **Storage:** AWS S3
- **Infra:** AWS SageMaker Notebooks for experimentation, single AWS account per team

For the complete stack specification and version constraints, see `CLAUDE.md`. For directory layout and module boundaries, see `ARCHITECTURE.md`.

---

## Core Entities

The domain model has eight main nouns. Every feature in the system is ultimately a verb acting on one of these.

- **Student** — the authenticated user. Has a profile, enrolled courses, a CV, a calendar, and priority preferences.
- **Course** — a TUM course the student is enrolled in. Holds lectures, slide decks, deadlines, and a per-student **Mastery** record.
- **Mastery** — the student's self-marked "I reviewed this" coverage per lecture, plus quiz results. Drives deadline prioritization.
- **Deadline** — a dated obligation (homework, exam, application) pulled from Moodle, TUMonline, or added manually. Has a weight and a priority score.
- **Thesis Opportunity** — an open thesis posting scraped from a chair's website, matched against the student's profile.
- **Job** — a working-student, internship, or new-grad listing. Has a match score and can be used as a target for CV optimization.
- **Booking** — any reservation the system performs: a library study room, a ZHS sports slot, an ESN event, a lunch. Every booking is a Calendar Event.
- **Calendar Event** — the unified representation in Google Calendar. Color-coded by originating agent. The single source of truth for availability.

---

## Specialist Agents

Each agent is a LangGraph graph with its own tools and prompts, invoked by the Orchestrator.

- **Academic Agent** — Moodle slide summarization, mastery tracking, quiz generation, unified deadline queue across Moodle + TUMonline, library room booking, thesis matching with drafted outreach emails.
- **Career Agent** — Profile enrichment from transcript, CV audit with flagged red flags, job scouting with match scores, per-listing CV optimization.
- **Social Agent** — ZHS sniper (books the instant registration opens), ESN/TUMi event booking, lunch coordination across friend calendars with Mensa menu integration.
- **Calendar Orchestrator** — The spine. Every agent reads/writes availability through it. Detects proposed-booking conflicts between agents and resolves them based on student-defined priorities (e.g., exam prep > sports > social).

---

## Getting Started

```bash
# Prereqs: Python 3.11+, uv, AWS credentials with Bedrock access, Cognee API key
git clone <repo>
cd campus-copilot
cp .env.example .env   # fill in AWS + Cognee credentials
uv sync
uv run uvicorn src.main:app --reload
```

Frontend setup lives in `frontend/README.md`.

---

## Project Status

Built in 48 hours for the Reply Challenge at the TUM Makeathon. Demo-quality, not production. The ambition is that after the hackathon this actually becomes a real service students at TUM can use — see the "Why It Matters" section of the original challenge brief.

---

## License

MIT for the hackathon submission.
