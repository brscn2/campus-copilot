# Cognee Semantic Memory — Design Spec

## Problem
Agents have no long-term memory. A student who searched for ML thesis topics last session gets no benefit from that context in future sessions. The Cognee SDK is wired (`src/lib/memory.py`) but never called.

## Solution
Async, batched memory extraction: every N conversation turns, a background task asks Sonnet to extract remembering-worthy facts from the batch, then writes them to Cognee. Agents query Cognee at the start of each request to enrich their context.

## Architecture

```
User sends message
    ↓
Orchestrator runs agent (unchanged)
    ↓
Orchestrator appends turns to SessionStore (unchanged)
    ↓
Orchestrator checks: len(session_turns) % BATCH_SIZE == 0?
    ├─ No → return immediately
    └─ Yes → fire-and-forget asyncio.create_task(extract_and_remember(...))
                ↓ (runs in background, zero latency)
                Sonnet extracts facts from last BATCH_SIZE turns
                ↓
                cognee.remember(facts, dataset_name="student_{student_id}")

--- On next request ---

Orchestrator loads session history (unchanged)
    ↓
Orchestrator queries Cognee: recall(query, dataset="student_{student_id}")
    ↓
Injects Cognee results into AgentInput.context["memory"]
    ↓
Agent prompt includes memory context
```

## Components

### 1. Memory Extractor (`src/lib/memory_extractor.py`)
- `extract_and_remember(student_id, turns)` — async function
- Calls Bedrock Sonnet with a structured prompt asking to extract facts
- Prompt: "Extract any student preferences, interests, academic goals, or scheduling patterns worth remembering long-term. Return a JSON list of strings. Return [] if nothing notable."
- On success: calls `add_to_memory(user_id=student_id, content=fact)` for each fact
- On failure: logs warning, does not raise (fire-and-forget must be safe)

### 2. Orchestrator Hook (`src/orchestrator/graph.py`)
- After `session_store.append(...)`, check turn count
- If `len(session_store.get_history(session_id)) % BATCH_SIZE == 0`: fire background task
- `BATCH_SIZE = 4` (every 2 full exchanges — user+assistant = 2 turns each exchange)

### 3. Memory Recall at Request Start (`src/orchestrator/graph.py`)
- Before dispatching to agent: `memories = await query_memory(user_id=student_id, query=query, top_k=3)`
- Pass as `AgentInput.context = {"memory": memories}` (field already exists, currently empty)

### 4. Agent Prompt Injection (all 3 agent `prompts.py`)
- Add to system prompt: "## Long-term Memory\n{memory_context}"
- If no memories, omit the section
- Format each memory as a bullet point

## Config
- `BATCH_SIZE = 4` — tunable, kept as constant in memory_extractor.py
- Extraction uses Sonnet (same model as agents) with `max_tokens=256`, `temperature=0.0`
- Cognee recall `top_k=3` — enough context without overwhelming the prompt

## What Gets Remembered (Examples)
- "Student is interested in reinforcement learning and robotics"
- "Student prefers Garching campus over Stammgelände"
- "Student is in 4th semester Informatics B.Sc."
- "Student has a deadline for IN2346 Homework 1 next week"
- "Student is looking for working student positions in ML"

## What Does NOT Get Remembered
- Transient queries ("what's for lunch?")
- System responses (only user intent matters)
- Duplicate facts (Cognee handles dedup via knowledge graph)

## Files Changed
- **New:** `src/lib/memory_extractor.py` (~60 lines)
- **Modify:** `src/orchestrator/graph.py` — add batch check + recall injection
- **Modify:** `src/agents/base.py` — no change needed (context field already exists)
- **Modify:** `src/agents/academic/prompts.py` — add memory section to system prompt
- **Modify:** `src/agents/career/prompts.py` — same
- **Modify:** `src/agents/social/prompts.py` — same
- **Modify:** `src/agents/academic/graph.py` — pass context["memory"] to prompt format
- **Modify:** `src/agents/career/graph.py` — same
- **Modify:** `src/agents/social/graph.py` — same
- **New:** `tests/unit/test_memory_extractor.py` (~40 lines)

## Testing
- Unit test: mock Bedrock + mock Cognee, verify extraction prompt and remember calls
- Unit test: verify orchestrator fires extraction at correct batch intervals
- Manual test: multi-turn conversation, restart server, verify Cognee-injected context appears

## Non-Goals
- Migrating SessionStore to Postgres (in-memory is fine for hackathon)
- Cognee forget/update (write-only for now)
- Per-agent memory namespacing (single namespace per student)
