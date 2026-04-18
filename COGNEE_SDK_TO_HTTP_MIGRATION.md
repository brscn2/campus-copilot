# Cognee SDK → HTTP API Migration Guide

> The `cogwit-sdk` doesn't support dataset-scoped queries. This doc explains how to replace SDK calls with raw HTTP calls to the Cognee API.

---

## Why migrate?

The `cogwit-sdk` (`cogwit.search()`) sends all queries to `/search` without any dataset filter. This means every search hits the **entire tenant** — all courses mixed together. The raw HTTP API supports a `datasets` array that scopes the search to specific course data.

```python
# SDK — no dataset scoping (searches everything)
results = await client.search(query_text="...", query_type=SearchType.GRAPH_COMPLETION)

# HTTP — scoped to a specific course dataset
resp = await httpx.post(
    f"{COGNEE_API_URL}/api/v1/search",
    json={"query": "...", "search_type": "GRAPH_COMPLETION", "datasets": ["course_IN2064"]},
    headers={"X-Api-Key": COGNEE_API_KEY},
)
```

---

## HTTP API reference

### Search endpoint

```
POST {COGNEE_API_URL}/api/v1/search
```

**Headers:**
```
X-Api-Key: {COGNEE_API_KEY}
Content-Type: application/json
```

**Body:**
```json
{
  "query": "your natural language question",
  "search_type": "GRAPH_COMPLETION",
  "datasets": ["course_dataset_name"]
}
```

**Search types available:**
- `GRAPH_COMPLETION` — LLM-synthesized answer grounded in the knowledge graph (recommended)
- `CHUNKS` — raw text chunks matching the query
- `SUMMARIES` — summary-level matches

**Response:** JSON array or object. Format varies by search type. For `GRAPH_COMPLETION`, the response is typically a list with one item containing the synthesized answer as a string.

### File upload endpoint

```
POST {COGNEE_API_URL}/api/v1/add
```

**Headers:**
```
X-Api-Key: {COGNEE_API_KEY}
```

**Body:** multipart form data
```
data: (filename, file_bytes, mime_type)   — the file to upload
datasetName: "course_dataset_name"         — target dataset
```

### Cognify endpoint

```
POST {COGNEE_API_URL}/api/v1/cognify
```

**Headers:**
```
X-Api-Key: {COGNEE_API_KEY}
Content-Type: application/json
```

**Body:**
```json
{
  "datasets": ["course_dataset_name"],
  "customPrompt": "Your custom processing prompt..."
}
```

---

## Migration pattern

### Before (cogwit SDK)

```python
from cogwit_sdk import CogwitConfig, cogwit

client = cogwit(CogwitConfig(api_key=settings.cognee_api_key))

# No dataset scoping possible
results = await client.search(
    query_text="List all core concepts",
    query_type=client.SearchType.GRAPH_COMPLETION,
)

# Parse results
for r in results:
    text = str(r.search_result) if hasattr(r, "search_result") else str(r)
```

### After (raw HTTP)

```python
import httpx

async with httpx.AsyncClient(timeout=60.0) as client:
    resp = await client.post(
        f"{settings.cognee_api_url}/api/v1/search",
        json={
            "query": "List all core concepts",
            "search_type": "GRAPH_COMPLETION",
            "datasets": [f"course_{course_id}"],
        },
        headers={"X-Api-Key": settings.cognee_api_key},
    )
    resp.raise_for_status()
    data = resp.json()

# Parse results — response is typically a list of strings/dicts
texts = []
if isinstance(data, list):
    for item in data:
        text = str(item.get("search_result", item)) if isinstance(item, dict) else str(item)
        texts.append(text)
```

---

## Response format gotchas

Cognee's `GRAPH_COMPLETION` search wraps responses in Python list repr format:

```
["{'key': 'value'}"]        — single-item list containing a string of Python dict repr
['{"key": "value"}']        — single-item list containing a JSON string
["item1; item2; item3"]     — semicolon-separated list for simple queries
```

To handle this reliably:

```python
import ast
import json

def parse_cognee_response(raw: str) -> Any:
    """Unwrap Cognee's Python-list-repr wrapper and parse the inner content."""
    text = raw.strip()

    # Try unwrapping Python list repr: ['{ json }']
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list) and parsed:
                text = str(parsed[0])
        except (ValueError, SyntaxError):
            text = text[1:-1].strip().strip("'\"")

    # Try JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text  # Return as plain string
```

---

## Current state in the codebase

`src/lib/memory.py` uses a hybrid approach:
- **Dataset-scoped queries** → `_search_via_http()` (raw HTTP with `datasets` parameter)
- **Unscoped queries** → cogwit SDK (for backward compatibility with student memory)

The cogwit SDK is still imported for unscoped searches (e.g., `query_memory` for student-specific data that uses `student_{user_id}` datasets — though these should also be migrated to HTTP).

### Files that use the Cognee SDK or HTTP API

| File | Current approach | Should migrate? |
|---|---|---|
| `src/lib/memory.py` | Hybrid (HTTP for dataset, SDK for unscoped) | SDK calls should move to HTTP |
| `src/lib/cognify.py` | Raw HTTP (upload + cognify) | Already HTTP, no change needed |
| `src/integrations/content_pipeline.py` | Calls `memory.py` + `cognify.py` | No direct Cognee calls |

### Config values needed

```python
# From src/config.py (Settings class)
cognee_api_key: str       # API key for X-Api-Key header
cognee_api_url: str       # Tenant URL, e.g. https://tenant-xxx.aws.cognee.ai
cognee_dataset_prefix: str  # "course_" — prepended to course IDs for dataset names
```

---

## Checklist for migrating a new search call

1. Replace `client.search(query_text=..., query_type=...)` with `httpx.post()` to `/api/v1/search`
2. Add `"datasets": [dataset_name]` to the JSON body for scoped queries
3. Handle the Python-list-repr response wrapper (see parsing section above)
4. Use `settings.cognee_api_url` and `settings.cognee_api_key` from config
5. Set `timeout=60.0` on the httpx client (Cognee can be slow for large graphs)
6. Wrap in try/except and raise `CogneeRetrievalError` on failure