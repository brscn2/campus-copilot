FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install uv

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Install Chromium for the Playwright Moodle scraper.
# `--with-deps` pulls the required system libs (libnss3, libatk1.0-0, etc.)
# via apt-get inside the playwright CLI. Cached as long as pyproject.toml
# (and therefore the playwright pin) doesn't change.
RUN uv run playwright install --with-deps chromium

COPY src/ src/
COPY alembic.ini ./
COPY alembic/ alembic/
COPY scripts/ scripts/

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
