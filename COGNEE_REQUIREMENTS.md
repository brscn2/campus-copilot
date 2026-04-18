# Cognee Integration Requirements

> Scope: Everything AFTER files are uploaded to Cognee via `/api/v1/add` (already done by Moodle scraper).

---

## 1. Cognify Pipeline

**Trigger:** After new lecture/exercise PDFs are uploaded to a course dataset.

**What it does:**
- Calls `POST /api/v1/cognify` with a custom prompt
- Builds a hierarchical concept tree from the content:
  ```
  Domain → CoreConcept → SubConcept → LeafConcept
  ```
- Maps exercise questions to the leaf concepts they test
- Identifies prerequisite relationships between concepts

**Custom prompt focus:**
- CoreConcepts = major syllabus topics (8-15 per course, used for progress tracking)
- LeafConcepts = atomic testable units (used for quiz generation)
- Exercise questions linked to LeafConcepts via TESTS relationship
- Prerequisite chains between CoreConcepts

**Config:**
| Key | Value |
|---|---|
| `COGNEE_API_URL` | `https://tenant-cc08b4f6-8cfd-4dae-9630-007897ddc466.aws.cognee.ai` |
| `COGNEE_API_KEY` | stored in `.env` |
| SDK | `cogwit-sdk` for search, raw `httpx` for file upload |
| Env var for SDK | `COGWIT_API_BASE` must be set to `COGNEE_API_URL` before importing cogwit |

**Dataset naming:** `course_{course_id}` — one dataset per course, shared across all students.

---

## 2. Search / Query Layer

**Wire into:** `src/lib/memory.py` (currently stubbed)

**Functions needed:**

### `query_course_knowledge(course_id, query, search_type) → list[str]`
- Calls Cognee `GRAPH_COMPLETION` search against `course_{course_id}` dataset
- Returns LLM-synthesized answers grounded in the knowledge graph
- Used by agents for answering student questions about lecture content

### `get_core_concepts(course_id) → list[CoreConcept]`
- Queries: "List all core concepts with their sub-concepts"
- Returns structured list for progress dashboard
- Cacheable — only changes when new lectures are cognified

### `get_exercise_concept_map(course_id, exercise_name) → dict`
- Queries: "Which core/leaf concepts does {exercise} test?"
- Returns mapping of exercise questions → concepts
- Used to update student progress after exercise completion

### `get_quiz_material(course_id, core_concept) → list[LeafConcept]`
- Queries: "List leaf concepts under {core_concept} with definitions"
- Returns leaf concepts with definitions precise enough for quiz generation
- Fed to LLM to generate quiz questions

### `get_prerequisites(course_id, topic) → list[str]`
- Queries: "What prerequisite concepts are needed for {topic}?"
- Used for study recommendations

---

## 3. Quiz Generation Pipeline

**Trigger:** After cognify completes, or on-demand per core concept.

**Flow:**
```
get_quiz_material(course_id, core_concept)
  → LeafConcepts with definitions
  → LLM generates 3-5 quiz questions per leaf concept
  → Store as JSON in S3: s3://{bucket}/quizzes/course_{id}/{core_concept}.json
```

**Quiz JSON format:**
```json
{
  "core_concept": "Modularity",
  "questions": [
    {
      "id": "uuid",
      "leaf_concept": "Coupling Factor α",
      "question": "What does α_good represent?",
      "type": "multiple_choice",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct": "B",
      "difficulty": "medium",
      "explanation": "..."
    }
  ],
  "generated_at": "2026-04-18T12:00:00Z",
  "source_lectures": ["Chapter 2.1.1"]
}
```

**Storage:** S3 bucket (or local JSON for hackathon demo).

---

## 4. Student Progress Tracking

**Storage:** Postgres (new table needed in `src/storage/schema.py`)

```sql
student_concept_progress
  ├── id                (UUID, PK)
  ├── student_id        (FK → students.id)
  ├── course_id         (FK → courses.id)
  ├── core_concept      (string — name from Cognee graph)
  ├── mastery_score     (float 0.0 → 1.0)
  ├── exercises_completed (int)
  ├── quizzes_taken     (int)
  ├── quizzes_passed    (int)
  ├── last_activity     (timestamp)
  ├── created_at        (timestamp)
  ├── updated_at        (timestamp)
  UNIQUE(student_id, course_id, core_concept)
```

**Progress update triggers:**
- Student completes exercise → query Cognee for tested concepts → bump mastery
- Student passes quiz → bump mastery for that core concept
- Mastery score formula: `(exercises_weight * exercise_ratio + quiz_weight * quiz_ratio)`

---

## 5. Quiz Serving Flow

```
Student requests quiz
  → Read Postgres: which core concepts have lowest mastery?
  → Read S3: load quiz JSON for weakest concept
  → Filter out already-answered questions (Postgres tracks quiz history)
  → Serve 5-10 questions weighted toward weak areas
  → Student submits answers
  → Score, update Postgres progress
```

---

## 6. Dependencies to Add

```toml
# pyproject.toml additions
"cogwit-sdk>=0.1.0",    # Cognee Cloud SDK (search)
"python-dotenv>=1.0.0", # .env loading for scripts
```

**Note:** `cogwit-sdk` uses `COGWIT_API_BASE` env var for tenant URL. Must set before import:
```python
os.environ["COGWIT_API_BASE"] = settings.cognee_api_url
```

---

## 7. Config Additions (src/config.py)

```python
# Add to Settings class:
cognee_tenant_id: str = ""
cognee_dataset_prefix: str = "course_"
quiz_s3_prefix: str = "quizzes/"
```

---

## 8. Files to Create/Modify

| File | Action | What |
|---|---|---|
| `src/lib/memory.py` | **Rewrite** | Wire to Cognee via cogwit-sdk + httpx |
| `src/lib/quiz.py` | **Create** | Quiz generation + S3 storage |
| `src/storage/schema.py` | **Add** | `StudentConceptProgressRow` table |
| `src/config.py` | **Add** | Cognee tenant + quiz config fields |
| `src/agents/academic/tools.py` | **Add** | `search_lectures`, `get_progress`, `take_quiz` tools |
| `src/agents/academic/prompts.py` | **Update** | Add lecture/quiz capabilities to system prompt |
| `pyproject.toml` | **Add** | `cogwit-sdk` dependency |

---

## 9. What's Already Done

- [x] Cognee Cloud tenant provisioned and accessible
- [x] API key working with `X-Api-Key` header
- [x] File upload via `POST /api/v1/add` (Moodle scraper by colleague)
- [x] Cognify tested with custom hierarchical prompt — produces good concept trees
- [x] Search tested via cogwit-sdk — GRAPH_COMPLETION returns accurate results
- [x] Exercise-to-concept mapping verified (exercise sheet 4 → chapters 2 & 3)
- [x] Custom prompt designed for CoreConcept/SubConcept/LeafConcept hierarchy

## 10. What's Next (Implementation Order)

1. **Wire `src/lib/memory.py`** — connect to Cognee for search
2. **Add progress table** — `StudentConceptProgressRow` in schema.py
3. **Create `src/lib/quiz.py`** — generation pipeline
4. **Add academic agent tools** — `search_lectures`, `get_progress`, `take_quiz`
5. **Test end-to-end** — upload → cognify → search → quiz → progress
