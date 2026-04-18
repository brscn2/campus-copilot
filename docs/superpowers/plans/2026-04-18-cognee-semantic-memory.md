# Cognee Cloud Semantic Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Cognee Cloud as an async, batched semantic memory layer so agents remember student preferences and interests across sessions.

**Architecture:** Every 4 conversation turns, a background task sends the batch to Bedrock Sonnet to extract remembering-worthy facts, then writes them to Cognee Cloud via `cogwit-sdk`. On each new request, the orchestrator queries Cognee for relevant memories and injects them into the agent's system prompt.

**Tech Stack:** `cogwit-sdk` (Cognee Cloud Python SDK), `asyncio.create_task` for fire-and-forget, Bedrock Sonnet for fact extraction.

**Key discovery:** Cognee Cloud uses `cogwit-sdk` (not the local `cognee` package). The API is: `add(data, dataset_name)` → `cognify(datasets)` → `search(query_text, query_type)`. The package is already installed.

---

### Task 1: Rewrite `src/lib/memory.py` for Cognee Cloud SDK

**Files:**
- Modify: `src/lib/memory.py`
- Modify: `src/config.py`
- Modify: `pyproject.toml`
- Modify: `tests/unit/test_memory.py`

- [ ] **Step 1: Update pyproject.toml**

Add `cogwit-sdk` to dependencies (it's pip-installed but not in pyproject.toml yet). Replace the `cognee>=0.1.0` line with `cogwit-sdk>=0.1.7`.

- [ ] **Step 2: Simplify config.py**

The Cognee Cloud SDK only needs an API key. Remove the self-hosted cognee config fields (`cognee_llm_provider`, `cognee_llm_model`, `cognee_embedding_*`) since Cognee Cloud handles LLM/embedding internally. Keep only:

```python
    # Cognee Cloud
    cognee_api_key: str = ""
```

- [ ] **Step 3: Rewrite `src/lib/memory.py`**

Replace the entire file with Cognee Cloud SDK (`cogwit_sdk`) implementation:

```python
"""Cognee Cloud memory layer — knowledge graph for cross-session retrieval."""
from __future__ import annotations

from typing import Any

import structlog
from cogwit_sdk import CogwitConfig, SearchType, cogwit

from src.config import get_settings

logger = structlog.get_logger(__name__)

_client: cogwit | None = None


def _get_client() -> cogwit | None:
    """Lazy-init the Cognee Cloud client."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.cognee_api_key:
            return None
        _client = cogwit(CogwitConfig(api_key=settings.cognee_api_key))
    return _client


async def add_to_memory(
    *,
    user_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Ingest content into Cognee Cloud knowledge graph."""
    client = _get_client()
    if client is None:
        return
    try:
        dataset_name = f"student_{user_id}"
        logger.info("memory_add", user_id=user_id, content_length=len(content))
        response = await client.add(data=content, dataset_name=dataset_name)
        if hasattr(response, "dataset_id"):
            await client.cognify(datasets=[dataset_name])
    except Exception:
        logger.warning("memory_add_failed", user_id=user_id, exc_info=True)


async def query_memory(
    *,
    user_id: str,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Query Cognee Cloud knowledge graph for relevant context."""
    client = _get_client()
    if client is None:
        return []
    try:
        logger.info("memory_query", user_id=user_id, query=query)
        response = await client.search(
            query_text=query,
            query_type=SearchType.GRAPH_COMPLETION,
        )
        if isinstance(response, list):
            results: list[dict[str, Any]] = []
            for r in response[:top_k]:
                text = str(r.search_result) if hasattr(r, "search_result") else str(r)
                results.append({"text": text})
            return results
        if hasattr(response, "result") and response.result:
            return [{"text": str(response.result)}]
        return []
    except Exception:
        logger.warning("memory_query_failed", user_id=user_id, exc_info=True)
        return []
```

- [ ] **Step 4: Update tests**

Rewrite `tests/unit/test_memory.py` to mock the cogwit client instead of the `cognee` module:

```python
"""Unit tests for the Cognee Cloud memory layer."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level client between tests."""
    import src.lib.memory as mem
    mem._client = None
    yield
    mem._client = None


@pytest.mark.asyncio
async def test_add_to_memory_calls_cogwit_add() -> None:
    mock_client = MagicMock()
    mock_client.add = AsyncMock(return_value=MagicMock(dataset_id="abc"))
    mock_client.cognify = AsyncMock(return_value=MagicMock())

    with patch("src.lib.memory._get_client", return_value=mock_client):
        from src.lib.memory import add_to_memory
        await add_to_memory(
            user_id="demo-student",
            content="Student is interested in reinforcement learning.",
        )

    mock_client.add.assert_called_once()
    assert mock_client.add.call_args[1]["dataset_name"] == "student_demo-student"
    mock_client.cognify.assert_called_once()


@pytest.mark.asyncio
async def test_query_memory_calls_cogwit_search() -> None:
    mock_result = MagicMock()
    mock_result.search_result = "Student likes ML and robotics."
    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=[mock_result])

    with patch("src.lib.memory._get_client", return_value=mock_client):
        from src.lib.memory import query_memory
        results = await query_memory(
            user_id="demo-student",
            query="What are the student's interests?",
        )

    assert len(results) == 1
    assert "ML" in results[0]["text"]


@pytest.mark.asyncio
async def test_add_to_memory_noop_without_api_key() -> None:
    with patch("src.lib.memory._get_client", return_value=None):
        from src.lib.memory import add_to_memory
        await add_to_memory(user_id="demo", content="test")
        # Should not raise


@pytest.mark.asyncio
async def test_query_memory_returns_empty_without_api_key() -> None:
    with patch("src.lib.memory._get_client", return_value=None):
        from src.lib.memory import query_memory
        results = await query_memory(user_id="demo", query="test")
        assert results == []
```

- [ ] **Step 5: Run validation**

```bash
uv run ruff check . && uv run mypy src/ && uv run pytest tests/ -x -v
```

- [ ] **Step 6: Commit**

```bash
git add src/lib/memory.py src/config.py pyproject.toml tests/unit/test_memory.py
git commit -m "feat: rewrite memory layer for Cognee Cloud SDK (cogwit-sdk)"
```

---

### Task 2: Create Memory Extractor (`src/lib/memory_extractor.py`)

**Files:**
- Create: `src/lib/memory_extractor.py`
- Create: `tests/unit/test_memory_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the background memory extractor."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.lib.memory_extractor import extract_and_remember


@pytest.mark.asyncio
async def test_extract_and_remember_calls_bedrock_and_cognee() -> None:
    turns = [
        {"role": "user", "content": "Find me thesis topics in reinforcement learning"},
        {"role": "assistant", "content": "I found 2 thesis topics about RL..."},
        {"role": "user", "content": "I prefer the robotics one at Prof. Knoll's chair"},
        {"role": "assistant", "content": "Great choice! Prof. Knoll's chair focuses on..."},
    ]

    mock_response = {
        "content": [{"text": '["Student is interested in reinforcement learning for robotics", "Student prefers Prof. Knoll chair for thesis"]'}]
    }

    with (
        patch("src.lib.memory_extractor.invoke_model", new_callable=AsyncMock, return_value=mock_response),
        patch("src.lib.memory_extractor.add_to_memory", new_callable=AsyncMock) as mock_add,
    ):
        await extract_and_remember(student_id="demo-student", turns=turns)

    assert mock_add.call_count == 2
    first_call = mock_add.call_args_list[0]
    assert first_call[1]["user_id"] == "demo-student"
    assert "reinforcement learning" in first_call[1]["content"]


@pytest.mark.asyncio
async def test_extract_and_remember_handles_empty_extraction() -> None:
    turns = [
        {"role": "user", "content": "What's for lunch?"},
        {"role": "assistant", "content": "Today's menu at Mensa Garching..."},
    ]

    mock_response = {"content": [{"text": "[]"}]}

    with (
        patch("src.lib.memory_extractor.invoke_model", new_callable=AsyncMock, return_value=mock_response),
        patch("src.lib.memory_extractor.add_to_memory", new_callable=AsyncMock) as mock_add,
    ):
        await extract_and_remember(student_id="demo-student", turns=turns)

    mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_extract_and_remember_handles_bedrock_failure() -> None:
    with patch("src.lib.memory_extractor.invoke_model", new_callable=AsyncMock, side_effect=Exception("Bedrock down")):
        await extract_and_remember(student_id="demo-student", turns=[{"role": "user", "content": "hello"}])
        # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_memory_extractor.py -v
```

- [ ] **Step 3: Implement `src/lib/memory_extractor.py`**

```python
"""Background memory extractor — asks Sonnet to extract remembering-worthy facts."""
from __future__ import annotations

import json

import structlog

from src.lib.bedrock import get_sonnet_model_id, invoke_model
from src.lib.memory import add_to_memory

logger = structlog.get_logger(__name__)

BATCH_SIZE = 4

EXTRACTION_PROMPT = """You are analyzing a conversation between a student and an AI assistant.

Extract any facts worth remembering long-term about the student. Focus on:
- Academic interests and preferences
- Career goals and target roles
- Campus preferences (buildings, locations)
- Scheduling patterns or constraints
- Skills and experience mentioned

Return a JSON array of short fact strings. Return [] if nothing notable.

Example: ["Student is interested in reinforcement learning", "Student prefers Garching campus"]

Conversation:
{conversation}"""


async def extract_and_remember(
    *,
    student_id: str,
    turns: list[dict[str, str]],
) -> None:
    """Extract facts from conversation turns and store in Cognee Cloud."""
    try:
        conversation = "\n".join(
            f"{'Student' if t['role'] == 'user' else 'Agent'}: {t['content']}" for t in turns
        )
        prompt = EXTRACTION_PROMPT.format(conversation=conversation)

        response = await invoke_model(
            model_id=get_sonnet_model_id(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.0,
        )

        raw = response["content"][0]["text"]
        facts: list[str] = json.loads(raw)

        if not facts:
            logger.info("memory_extract_nothing_notable", student_id=student_id)
            return

        logger.info("memory_extract_facts", student_id=student_id, count=len(facts))
        for fact in facts:
            await add_to_memory(user_id=student_id, content=fact)

    except Exception:
        logger.warning("memory_extract_failed", student_id=student_id, exc_info=True)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_memory_extractor.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Run full validation**

```bash
uv run ruff check . && uv run mypy src/ && uv run pytest tests/ -x -v
```

- [ ] **Step 6: Commit**

```bash
git add src/lib/memory_extractor.py tests/unit/test_memory_extractor.py
git commit -m "feat: add background memory extractor with Sonnet fact extraction"
```

---

### Task 3: Wire Orchestrator — Batch Extraction + Memory Recall

**Files:**
- Modify: `src/orchestrator/graph.py`

- [ ] **Step 1: Add background extraction trigger**

After the existing `session_store.append(...)` call, add the batch check:

```python
import asyncio
from src.lib.memory_extractor import BATCH_SIZE, extract_and_remember

# ... after session_store.append(...)

history_after = session_store.get_history(session_id)
if len(history_after) % BATCH_SIZE == 0 and len(history_after) > 0:
    recent_turns = history_after[-BATCH_SIZE:]
    asyncio.create_task(
        extract_and_remember(student_id=student_id, turns=recent_turns)
    )
```

- [ ] **Step 2: Add memory recall before dispatch**

Before dispatching to the agent, query Cognee for relevant memories:

```python
from src.lib.memory import query_memory

# ... after loading history, before creating AgentInput

memories = await query_memory(user_id=student_id, query=query, top_k=3)
memory_context = {
    "memory": [m["text"] for m in memories] if memories else [],
}
```

Pass `context=memory_context` in the `AgentInput(...)` constructor.

- [ ] **Step 3: Run validation**

```bash
uv run ruff check . && uv run mypy src/ && uv run pytest tests/ -x -v
```

- [ ] **Step 4: Commit**

```bash
git add src/orchestrator/graph.py
git commit -m "feat: wire batch memory extraction and recall into orchestrator"
```

---

### Task 4: Inject Memory into Agent Prompts

**Files:**
- Modify: `src/agents/academic/prompts.py`
- Modify: `src/agents/career/prompts.py`
- Modify: `src/agents/social/prompts.py`
- Modify: `src/agents/academic/graph.py`
- Modify: `src/agents/career/graph.py`
- Modify: `src/agents/social/graph.py`

- [ ] **Step 1: Add memory section to all 3 prompt templates**

Append to each agent's system prompt string (before the closing `"""`):

```
{memory_section}
```

- [ ] **Step 2: Update all 3 agent graph `run()` functions**

In the `run()` function where the system prompt is formatted, add memory section construction:

```python
memory_items = agent_input.context.get("memory", [])
if memory_items:
    memory_section = "\n## What I Remember About You\n" + "\n".join(
        f"- {item}" for item in memory_items
    )
else:
    memory_section = ""
```

Pass `memory_section=memory_section` to the prompt format call.

- [ ] **Step 3: Run full validation**

```bash
uv run ruff check . && uv run mypy src/ && uv run pytest tests/ -x -v
```

- [ ] **Step 4: Commit**

```bash
git add src/agents/*/prompts.py src/agents/*/graph.py
git commit -m "feat: inject Cognee memory context into agent system prompts"
```

---

### Task 5: Update `.env.example` + Final Cleanup

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Simplify .env.example Cognee section**

Replace the current Cognee section with:

```bash
# --- Cognee Cloud ---
COGNEE_API_KEY=your-cogwit-api-key-here
```

Remove the old self-hosted fields (`COGNEE_API_URL`, `COGNEE_LLM_PROVIDER`, `COGNEE_LLM_MODEL`, `COGNEE_EMBEDDING_*`).

- [ ] **Step 2: Run full validation**

```bash
uv run ruff check . && uv run mypy src/ && uv run pytest tests/ -x -v
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "chore: simplify .env.example for Cognee Cloud"
```
