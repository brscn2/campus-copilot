# Infrastructure: Cognee Cloud + Postgres + Docker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace stubs with real Cognee Cloud memory, real Postgres with Alembic migrations, and dockerize the full stack (backend + frontend + postgres) for one-command demo startup.

**Architecture:** Three independent infrastructure layers wired together. Postgres is the durable state store (sessions, bookings, courses). Cognee Cloud is the knowledge graph for cross-session retrieval (slide summaries, past queries). Docker Compose orchestrates all services with health checks. Each layer is independently testable — Postgres can run without Cognee, Cognee can run without Docker.

**Tech Stack:** PostgreSQL 16, Alembic, Cognee SDK 1.0 (`remember`/`recall`/`forget`), Docker + Docker Compose, asyncpg, SQLAlchemy 2.x async.

---

## File Structure

```
# New files
alembic.ini                              # Alembic config pointing to src/storage
alembic/env.py                           # Alembic env with async engine support
alembic/script.py.mako                   # Migration template
alembic/versions/                        # Auto-generated migrations
scripts/seed_demo_student.py             # Seed script for demo data
Dockerfile                               # Multi-stage Python backend image
Dockerfile.frontend                      # Node.js frontend image
docker-compose.yml                       # Full stack: postgres + backend + frontend
.dockerignore                            # Exclude .venv, node_modules, .env

# Modified files
src/lib/memory.py                        # Replace stubs with real Cognee SDK calls
src/config.py                            # Add COGNEE_LLM_PROVIDER + any Docker-aware defaults
src/main.py                              # Add lifespan handler for DB init
.env.example                             # Add new vars (COGNEE_LLM_PROVIDER, etc.)
tests/conftest.py                        # Add async DB fixture option
```

---

### Task 1: Alembic Init + Initial Migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/` (auto-generated)
- Modify: `src/main.py`

- [ ] **Step 1: Initialize Alembic**

```bash
uv run alembic init alembic
```

- [ ] **Step 2: Configure alembic.ini**

Replace the `sqlalchemy.url` line in `alembic.ini`:

```ini
# Leave blank — we set it programmatically in env.py
sqlalchemy.url =
```

- [ ] **Step 3: Rewrite alembic/env.py for async + our models**

Replace the entire `alembic/env.py` with:

```python
"""Alembic env — async migration runner."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import get_settings
from src.storage.schema import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_settings().database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async engine."""
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Generate the initial migration**

Requires a running Postgres. Start one with Docker:

```bash
docker run -d --name copilot-pg -e POSTGRES_USER=copilot -e POSTGRES_PASSWORD=copilot -e POSTGRES_DB=campus_copilot -p 5432:5432 postgres:16-alpine
```

Wait for it to be ready, then:

```bash
uv run alembic revision --autogenerate -m "initial schema"
```

- [ ] **Step 5: Apply the migration**

```bash
uv run alembic upgrade head
```

Verify with:

```bash
docker exec copilot-pg psql -U copilot -d campus_copilot -c "\dt"
```

Expected: tables `students`, `courses`, `lectures`, `quiz_results`, `deadlines`, `thesis_opportunities`, `jobs`, `bookings`, `sessions` plus `alembic_version`.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/
git commit -m "chore: initialize Alembic with async env and initial migration"
```

---

### Task 2: Demo Seed Script

**Files:**
- Create: `scripts/seed_demo_student.py`

- [ ] **Step 1: Write the seed script**

```python
"""Seed a demo student with courses, deadlines, and lectures for the hackathon demo."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.config import get_settings
from src.storage.schema import (
    Base,
    BookingRow,
    CourseRow,
    DeadlineRow,
    LectureRow,
    StudentRow,
)


async def seed() -> None:
    engine = create_async_engine(get_settings().database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        student = StudentRow(
            id="demo-student",
            tum_email="alex.mueller@tum.de",
            display_name="Alex Müller",
            program="Informatics, B.Sc.",
            semester=4,
            priorities={"academics": 5, "career": 3, "social": 4},
        )
        session.add(student)

        courses = [
            CourseRow(
                id="moodle-IN2346",
                student_id="demo-student",
                code="IN2346",
                title="Introduction to Deep Learning",
                professor="Prof. Dr. Niels Landwehr",
                credits=6,
                moodle_id="100001",
            ),
            CourseRow(
                id="moodle-IN2064",
                student_id="demo-student",
                code="IN2064",
                title="Machine Learning",
                professor="Prof. Dr. Stephan Günnemann",
                credits=6,
                moodle_id="100002",
            ),
            CourseRow(
                id="moodle-IN2349",
                student_id="demo-student",
                code="IN2349",
                title="Advanced Deep Learning",
                professor="Prof. Dr. Nassir Navab",
                credits=5,
                moodle_id="100003",
            ),
        ]
        session.add_all(courses)

        now = datetime.now(UTC)
        deadlines = [
            DeadlineRow(
                course_id="moodle-IN2346",
                title="Homework 1 — Neural Network Implementation",
                due_at=now + timedelta(days=7),
                weight=0.15,
                source="moodle",
                priority_score=85.0,
            ),
            DeadlineRow(
                course_id="moodle-IN2064",
                title="Exercise Sheet 1 — Linear Regression",
                due_at=now + timedelta(days=4),
                weight=0.10,
                source="moodle",
                priority_score=92.0,
            ),
            DeadlineRow(
                course_id="moodle-IN2346",
                title="Midterm Exam",
                due_at=now + timedelta(days=32),
                weight=0.30,
                source="tumonline",
                priority_score=78.0,
            ),
        ]
        session.add_all(deadlines)

        lectures = [
            LectureRow(
                course_id="moodle-IN2346",
                title="Lecture 1 — Neural Network Basics",
                summary="Introduction to artificial neurons, activation functions, forward pass.",
                reviewed=True,
            ),
            LectureRow(
                course_id="moodle-IN2346",
                title="Lecture 2 — Backpropagation & Optimization",
                summary="Chain rule, computational graphs, gradient descent variants.",
                reviewed=False,
            ),
            LectureRow(
                course_id="moodle-IN2064",
                title="Lecture 1 — Supervised Learning Overview",
                summary="Problem formulation, hypothesis spaces, bias-variance tradeoff.",
                reviewed=True,
            ),
        ]
        session.add_all(lectures)

        await session.commit()
        print(f"Seeded demo student: {student.display_name} ({student.tum_email})")
        print(f"  {len(courses)} courses, {len(deadlines)} deadlines, {len(lectures)} lectures")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: Run the seed script**

```bash
uv run python scripts/seed_demo_student.py
```

Expected output:
```
Seeded demo student: Alex Müller (alex.mueller@tum.de)
  3 courses, 3 deadlines, 3 lectures
```

- [ ] **Step 3: Verify data in Postgres**

```bash
docker exec copilot-pg psql -U copilot -d campus_copilot -c "SELECT id, display_name, program FROM students;"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_demo_student.py
git commit -m "chore: add demo student seed script"
```

---

### Task 3: Wire Cognee Cloud Memory Layer

**Files:**
- Modify: `src/lib/memory.py`
- Modify: `src/config.py`
- Modify: `.env.example`
- Create: `tests/unit/test_memory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_memory.py`:

```python
"""Unit tests for the Cognee memory layer."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.lib.memory import add_to_memory, query_memory


@pytest.mark.asyncio
async def test_add_to_memory_calls_cognee_remember() -> None:
    with patch("src.lib.memory.cognee") as mock_cognee:
        mock_result = AsyncMock()
        mock_result.status = "completed"
        mock_cognee.remember = AsyncMock(return_value=mock_result)

        await add_to_memory(
            user_id="demo-student",
            content="Lecture 1 covers neural network basics.",
            metadata={"course": "IN2346"},
        )

        mock_cognee.remember.assert_called_once()
        call_args = mock_cognee.remember.call_args
        assert "neural network" in call_args[0][0]
        assert call_args[1]["dataset_name"] == "student_demo-student"


@pytest.mark.asyncio
async def test_query_memory_calls_cognee_recall() -> None:
    with patch("src.lib.memory.cognee") as mock_cognee:
        mock_cognee.recall = AsyncMock(return_value=[
            {"text": "Neural networks use backpropagation.", "score": 0.9}
        ])

        results = await query_memory(
            user_id="demo-student",
            query="How does backpropagation work?",
        )

        mock_cognee.recall.assert_called_once()
        assert len(results) == 1
        assert "backpropagation" in results[0]["text"]


@pytest.mark.asyncio
async def test_add_to_memory_handles_cognee_failure_gracefully() -> None:
    with patch("src.lib.memory.cognee") as mock_cognee:
        mock_cognee.remember = AsyncMock(side_effect=Exception("Cognee down"))

        await add_to_memory(
            user_id="demo-student",
            content="Some content",
        )
        # Should not raise — logs warning and returns
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/unit/test_memory.py -v
```

Expected: FAIL — `add_to_memory` currently doesn't call cognee.

- [ ] **Step 3: Update src/config.py with Cognee Cloud settings**

Add to the `Settings` class after the existing `cognee_api_url` field:

```python
    cognee_llm_provider: str = "custom"
```

- [ ] **Step 4: Implement the real memory layer**

Replace `src/lib/memory.py` entirely:

```python
"""Cognee Cloud memory layer — knowledge graph for cross-session retrieval."""
from __future__ import annotations

from typing import Any

import cognee
import structlog

from src.config import get_settings
from src.exceptions import CogneeIngestionError, CogneeRetrievalError

logger = structlog.get_logger(__name__)

_initialized = False


async def _ensure_init() -> None:
    """One-time Cognee config from env vars."""
    global _initialized
    if _initialized:
        return
    settings = get_settings()
    if settings.cognee_api_key:
        cognee.config.set_llm_config(
            {
                "llm_api_key": settings.cognee_api_key,
                "llm_provider": settings.cognee_llm_provider,
            }
        )
    _initialized = True


async def add_to_memory(
    *,
    user_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Ingest content into Cognee knowledge graph.

    Args:
        user_id: Student identifier for namespace isolation.
        content: Text content to ingest.
        metadata: Optional metadata to attach.
    """
    try:
        await _ensure_init()
        dataset_name = f"student_{user_id}"
        logger.info("memory_add", user_id=user_id, content_length=len(content))
        await cognee.remember(content, dataset_name=dataset_name)
    except Exception:
        logger.warning("memory_add_failed", user_id=user_id, exc_info=True)


async def query_memory(
    *,
    user_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Query Cognee knowledge graph for relevant context.

    Args:
        user_id: Student identifier for namespace isolation.
        query: Natural language query.
        top_k: Number of results to return.

    Returns:
        List of matching documents with content and metadata.
    """
    try:
        await _ensure_init()
        logger.info("memory_query", user_id=user_id, query=query, top_k=top_k)
        results = await cognee.recall(
            query,
            datasets=[f"student_{user_id}"],
            top_k=top_k,
        )
        return [
            {"text": str(r.get("text", r)), "score": r.get("score", 0.0)}
            if isinstance(r, dict)
            else {"text": str(r), "score": 0.0}
            for r in results
        ]
    except Exception:
        logger.warning("memory_query_failed", user_id=user_id, exc_info=True)
        return []
```

- [ ] **Step 5: Update .env.example**

Add after the existing Cognee section:

```bash
COGNEE_LLM_PROVIDER=custom
```

- [ ] **Step 6: Run the tests**

```bash
uv run pytest tests/unit/test_memory.py -v
```

Expected: 3 PASSED.

- [ ] **Step 7: Run full validation**

```bash
uv run ruff check . && uv run mypy src/ && uv run pytest tests/ -x -v
```

- [ ] **Step 8: Commit**

```bash
git add src/lib/memory.py src/config.py .env.example tests/unit/test_memory.py
git commit -m "feat: wire Cognee Cloud as real memory layer with graceful fallback"
```

---

### Task 4: Dockerize the Backend

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create .dockerignore**

```dockerignore
.venv/
__pycache__/
*.pyc
.env
.git/
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
frontend/
alembic/versions/__pycache__/
docs/
.claude/
.agents/
```

- [ ] **Step 2: Create the backend Dockerfile**

```dockerfile
FROM python:3.11-slim AS base

WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

COPY src/ src/
COPY alembic.ini ./
COPY alembic/ alembic/
COPY scripts/ scripts/

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Test the Docker build**

```bash
docker build -t campus-copilot-backend .
```

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "chore: add backend Dockerfile with uv"
```

---

### Task 5: Dockerize the Frontend

**Files:**
- Create: `Dockerfile.frontend`

- [ ] **Step 1: Create the frontend Dockerfile**

```dockerfile
FROM node:20-alpine AS base

WORKDIR /app

COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile 2>/dev/null || pnpm install

COPY frontend/ .

ENV NEXT_PUBLIC_BACKEND_URL=http://backend:8000
RUN pnpm build

EXPOSE 3000

CMD ["pnpm", "start"]
```

- [ ] **Step 2: Test the Docker build**

```bash
docker build -f Dockerfile.frontend -t campus-copilot-frontend .
```

Expected: Build succeeds (may have TS warnings — that's OK since `ignoreBuildErrors: true`).

- [ ] **Step 3: Commit**

```bash
git add Dockerfile.frontend
git commit -m "chore: add frontend Dockerfile with pnpm"
```

---

### Task 6: Docker Compose — Full Stack

**Files:**
- Create: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Write docker-compose.yml**

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: copilot
      POSTGRES_PASSWORD: copilot
      POSTGRES_DB: campus_copilot
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U copilot -d campus_copilot"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://copilot:copilot@postgres:5432/campus_copilot
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 3

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_BACKEND_URL: http://backend:8000
    depends_on:
      backend:
        condition: service_healthy

volumes:
  pgdata:
```

- [ ] **Step 2: Test docker compose up**

```bash
docker compose up --build -d
```

Wait for all services to be healthy:

```bash
docker compose ps
```

Expected: 3 services running (`postgres`, `backend`, `frontend`).

- [ ] **Step 3: Verify backend health through Docker**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Verify frontend loads**

Open `http://localhost:3000` in a browser. The dashboard should render.

- [ ] **Step 5: Run migrations inside the container**

```bash
docker compose exec backend uv run alembic upgrade head
```

- [ ] **Step 6: Seed demo data inside the container**

```bash
docker compose exec backend uv run python scripts/seed_demo_student.py
```

- [ ] **Step 7: Tear down**

```bash
docker compose down
```

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose with postgres, backend, and frontend"
```

---

### Task 7: Backend Lifespan Hook for DB + Final Validation

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Add lifespan context manager to main.py**

Add a lifespan handler that logs startup and verifies DB connectivity. Add this import and handler before `create_app`:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — verify DB connectivity on startup."""
    from src.storage.db import _engine
    async with _engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("startup_db_connected", database=get_settings().database_url.split("@")[-1])
    yield
```

Add `from sqlalchemy import text` to imports. Pass `lifespan=lifespan` to the `FastAPI(...)` constructor.

- [ ] **Step 2: Run the full end-to-end check (no Docker)**

```bash
uv run ruff check . && uv run mypy src/ && uv run pytest tests/ -x -v
```

Expected: All 66+ tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add lifespan hook with DB connectivity check on startup"
```

---

### Task 8: Final Docker Smoke Test

- [ ] **Step 1: Full stack up**

```bash
docker compose up --build -d
```

- [ ] **Step 2: Run migrations + seed**

```bash
docker compose exec backend uv run alembic upgrade head
docker compose exec backend uv run python scripts/seed_demo_student.py
```

- [ ] **Step 3: Test chat endpoint end-to-end**

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are my upcoming deadlines?"}'
```

Expected: SSE stream with `event: thinking` then `event: final`.

- [ ] **Step 4: Test REST endpoints**

```bash
curl http://localhost:8000/api/academic/deadlines | python -m json.tool
curl http://localhost:8000/api/social/mensa | python -m json.tool
```

- [ ] **Step 5: Test frontend chat**

Open `http://localhost:3000`, click "Ask Co-Pilot", type a message. Should get a real agent response (if AWS credentials are configured) or a graceful fallback.

- [ ] **Step 6: Tear down + final commit**

```bash
docker compose down
git add -A
git commit -m "chore: final docker smoke test verified"
```
