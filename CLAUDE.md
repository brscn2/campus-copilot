# CLAUDE.md — Campus Co-Pilot Backend Control Center

> This is the **operating manual** for Claude Code on this repository. Read this file at the start of every session. If any instruction here conflicts with a user request in chat, ask for clarification before proceeding.

---

## 1. What You Are Building

A multi-agent backend for **Campus Co-Pilot**, an autonomous AI assistant for TUM students. The system exposes three specialist agents — **Academic**, **Career**, **Social** — coordinated by a **Calendar Orchestrator**, all reachable through a single conversational API the Next.js frontend consumes.

For the "why" and the domain model, read `README.md`. For directory layout, state flow, and data schemas, read `ARCHITECTURE.md`. **Always read both before making structural changes.**

---

## 2. Tech Stack (Non-Negotiable)

| Layer | Choice | Notes |
|---|---|---|
| Language | **Python 3.11+** | Type hints required on every function signature |
| API framework | **FastAPI** | Async endpoints only |
| Agent framework | **LangGraph** | One graph per specialist agent, orchestrator graph on top |
| LLM provider | **AWS Bedrock** | No direct Anthropic/OpenAI SDK calls |
| Primary reasoning model | `anthropic.claude-sonnet-4-6-20250514-v1:0` via Bedrock inference profile |
| Fast/cheap model | `anthropic.claude-haiku-4-5-20251001-v1:0` — use for classification, routing, short summarization |
| Embeddings | `amazon.titan-embed-text-v2:0` |
| Memory / knowledge graph | **Cognee Cloud** | Primary retrieval layer — see §7 |
| Storage | **AWS S3** for files (CVs, slide PDFs), **S3 Vectors** as fallback vector store |
| Config | **Pydantic Settings** reading from `.env` |
| Package manager | **uv** | Never use `pip install` directly; use `uv add <pkg>` |
| Lint / format | **Ruff** (format + lint in one) |
| Types | **mypy** in strict mode for `src/`, relaxed for `tests/` |
| Tests | **pytest** + **pytest-asyncio** |
| Logging | **structlog** (JSON in prod, pretty in dev) |

**Do not introduce new dependencies without asking.** If you think a library is needed, propose it in chat first with a one-line justification.

---

## 3. Build, Run, Test Commands

Every command below is runnable from the repo root. If a command fails, **fix the underlying issue** — do not work around it by skipping the step.

```bash
# Install / sync dependencies
uv sync

# Run the API locally (hot reload)
uv run uvicorn src.main:app --reload --port 8000

# Run a single agent interactively (useful for debugging)
uv run python -m src.agents.academic.repl

# Lint + format (run before every commit)
uv run ruff format .
uv run ruff check --fix .

# Type check (must pass with zero errors in src/)
uv run mypy src/

# Tests
uv run pytest                              # full suite
uv run pytest tests/agents/test_academic.py -v   # single file
uv run pytest -k "thesis_matcher" -v       # by keyword
uv run pytest --cov=src --cov-report=term-missing  # with coverage

# End-to-end check before pushing — all must pass
uv run ruff check . && uv run mypy src/ && uv run pytest
```

**After any non-trivial change, run the full end-to-end check.** Do not declare work "done" until it passes.

---

## 4. Code Style & Formatting

### Python

- **Formatter:** Ruff format, line length **100**. Do not hand-format; let Ruff do it.
- **Quotes:** Double quotes `"..."` for strings, single quotes only inside f-strings when needed.
- **Indentation:** 4 spaces, no tabs.
- **Naming:**
  - `snake_case` for variables, functions, modules
  - `PascalCase` for classes and Pydantic models
  - `SCREAMING_SNAKE_CASE` for module-level constants
  - Private helpers prefixed with a single underscore: `_internal_helper`
  - Async functions are **not** prefixed with `async_` — the `async def` keyword is enough
- **Imports:** grouped as stdlib → third-party → first-party (`src.*`), separated by blank lines. Ruff handles this automatically.
- **Type hints:** required on every function signature (arguments and return type). Use `from __future__ import annotations` at the top of every file. Prefer built-in generics (`list[str]`, `dict[str, int]`) over `List`, `Dict`.
- **Pydantic:** use v2 syntax. Models go in `src/models/` or colocated with their agent. Use `model_config = ConfigDict(frozen=True)` for value objects.
- **Async:** all I/O (HTTP, Bedrock, Cognee, S3) must be async. Never call a blocking library inside an async function — wrap with `asyncio.to_thread` if there is no async alternative.

### Comments & Docstrings

- **Docstrings:** Google style, required on every public function, class, and module. Keep them tight — one-sentence summary, then `Args:` / `Returns:` / `Raises:` only when non-obvious.
- **Inline comments:** explain *why*, not *what*. If the code needs a comment to say what it does, the code is wrong.
- **No commented-out code.** Delete it; Git remembers.
- **TODOs:** format as `# TODO(name): short description` — always attributed, never anonymous.

---

## 5. Error Handling Rules

1. **Never use bare `except:`.** Always catch a specific exception class.
2. **Never `except Exception: pass`.** If you genuinely want to swallow an error, log it at WARNING and comment why.
3. **Custom exceptions** for every failure mode the caller might want to branch on — defined in `src/exceptions.py`. Examples: `BedrockRateLimitError`, `TUMSystemUnavailableError`, `CogneeRetrievalError`.
4. **API boundary:** every FastAPI route is wrapped in the global exception handler in `src/main.py`. Domain exceptions map to specific HTTP status codes; unknown exceptions return 500 with a generic message and log the traceback.
5. **Agent boundary:** when an agent tool fails, the agent must receive a structured error dict (`{"error": "...", "recoverable": bool}`) rather than a raised exception, so the LLM can reason about retry vs. giving up.
6. **External systems (TUMonline, Moodle, ZHS, etc.):** wrap every call in a retry decorator with exponential backoff (3 attempts max, jitter on). Use `tenacity`.
7. **Logging on error:**
   ```python
   logger.error(
       "failed_to_book_study_room",
       room_id=room_id,
       user_id=user_id,
       exc_info=True,
   )
   ```
   Always use structured key-value logging — never f-strings in log messages.

---

## 6. Agent Development Rules

- **One agent per subdirectory** under `src/agents/` — each contains `graph.py` (LangGraph definition), `tools.py`, `prompts.py`, `state.py`.
- **Tool functions are pure and testable.** They take primitives, return primitives (or Pydantic models). No hidden global state. No LLM calls inside a tool — tools are the hands; the LLM is the brain.
- **Prompts live in `prompts.py` as module-level constants**, never inline in graph code. This keeps them diffable and lets us unit-test rendered prompts.
- **Every agent must expose:** `async def run(input: AgentInput) -> AgentOutput` as its public entrypoint. The orchestrator only calls this.
- **The orchestrator** (`src/orchestrator/`) is responsible for: routing user requests to the right agent, resolving Calendar conflicts between agents, and aggregating multi-agent responses.
- **Streaming:** agent responses stream via SSE to the frontend. Intermediate "agent is working" states are first-class events, not log spam.
- **Human-in-the-loop actions** (sending emails, submitting bookings) must always pause and return a draft for explicit user approval. Never auto-send.

---

## 7. Cognee Cloud — Memory & Retrieval

Cognee is the primary memory layer. Treat it as a persistent, cross-session knowledge graph of everything the student has done.

- **Ingest on write:** when the Academic Agent summarizes a Moodle slide deck, that summary is cogneeified (`cognee.add` → `cognee.cognify`) so later queries ("what did we cover about B-trees?") retrieve it graph-aware.
- **Query on read:** before any agent answers a factual/historical question about the student, it queries Cognee first. Fall back to live TUM systems only if Cognee has no relevant node.
- **Namespacing:** use `dataset_name=f"student_{user_id}"` — never mix users.
- **Do not** push raw PII (full name, address, ID numbers) into Cognee. Push derived facts only.

S3 Vectors is the **fallback** if Cognee is down — see `src/lib/memory.py` for the abstraction.

---

## 8. AWS Bedrock Rules

- Always go through `src/lib/bedrock.py`. Never instantiate a `boto3` Bedrock client elsewhere.
- Use **inference profiles**, not raw model IDs — region-specific throughput matters for the hackathon demo.
- Respect the model hierarchy:
  - **Opus 4.6** — only for thesis matching, CV audit, quiz generation (tasks needing deep reasoning)
  - **Sonnet 4.6** — default for all agent reasoning
  - **Haiku 4.5** — router, intent classification, short summaries, tool-call formatting
- Stream by default. Buffer only when the downstream consumer cannot handle chunks.
- Set `max_tokens` explicitly on every call. The default is too high and burns credits.

---

## 9. Security & Secrets

- **Never commit a secret.** `.env` is gitignored; `.env.example` lists every required variable with dummy values.
- **Never log a secret.** The structlog processor in `src/lib/logging.py` redacts known key names (`api_key`, `token`, `authorization`, `password`) — do not bypass it.
- **TUM credentials** (TUMonline/Moodle cookies) are encrypted at rest using AWS KMS before being stored. See `src/lib/credentials.py`.
- **Input validation:** every FastAPI endpoint uses a Pydantic request model. No `dict[str, Any]` endpoints.

---

## 10. Git & Commit Conventions

- **Branch naming:** `feat/<short-name>`, `fix/<short-name>`, `chore/<short-name>`.
- **Commit messages:** Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`). Imperative mood, no period, ≤72 chars for the subject line.
- **One logical change per commit.** If you touch two agents for unrelated reasons, that's two commits.
- **Never commit if `ruff check`, `mypy`, or `pytest` fails.**

---

## 11. When In Doubt

- If a request is ambiguous, **ask in chat** before writing code.
- If you need to install a new dependency, **propose it first**.
- If you're about to write more than ~150 lines without running a test, **stop and run what you have**.
- If a file exceeds ~400 lines, **split it** — long files are a code smell here.
- If you find yourself mocking something complex just to get tests to pass, the abstraction is probably wrong — flag it in chat.

Your job is not to produce the most code fastest. It is to produce code that a sleep-deprived teammate at 3 AM can read, trust, and extend.
