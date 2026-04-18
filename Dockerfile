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
