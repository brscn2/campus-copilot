# Quiz, Flashcard & Summary Generation — Design Spec

> Date: 2026-04-18
> Branch: `quiz_flashcard_cognee`
> Status: Draft

---

## 1. Overview

A content generation and progress tracking system for Campus Co-Pilot. After Cognee cognifies course materials, the system auto-generates quizzes, flashcards, and lecture summaries. Students consume this content through personalized sessions that adapt to their mastery level.

### Goals

- Auto-generate learning materials after every cognify run
- Store generated content on S3 (stateless, regenerated each run)
- Track student progress in Postgres (mastery per concept, attempt history)
- Serve personalized quizzes/flashcards weighted toward weak areas
- Allow manual mastery overrides by the student
- Keep the system extensible for future content types

---

## 2. Trigger: Cognify Completion Hook

**Location:** `src/lib/cognify.py::_run_cognify()` (line ~98)

The existing hook currently calls `quiz.generate_quizzes_for_course`. This is replaced with:

```python
from src.lib.content_generator import generate_all_for_course
await generate_all_for_course(course_id)
```

All content is **regenerated on every cognify run** (full overwrite of S3 keys).

> **Future direction:** Track a concept manifest on S3 (`manifest/course_{id}.json`) listing known core concepts + content hashes. On each run, diff against the manifest and only regenerate for new or changed concepts. This avoids redundant LLM calls when only one lecture is added.

---

## 3. Content Generation Pipeline

### Module: `src/lib/content_generator.py`

Replaces `src/lib/quiz.py`. Single public entry point:

```python
async def generate_all_for_course(course_id: str) -> GenerationResult
```

Three internal phases run sequentially:

### 3.1 Quiz Generation (per core concept)

| Step | Source | Detail |
|---|---|---|
| 1. Get concepts | Cognee | `get_core_concepts(course_id)` → list of core concepts |
| 2. Get leaf material | Cognee | `get_quiz_material(course_id, concept)` → leaf concept definitions |
| 3. Generate MCQs | Bedrock Sonnet | 3-5 questions per core concept, grounded in leaf definitions |
| 4. Store | S3 | `quizzes/course_{id}/{concept}.json` |

**LLM context at generation time:** The LLM receives leaf concept definitions/formulas extracted by Cognee from the lecture PDFs. It never sees raw PDFs — Cognee's knowledge graph is the sole context source.

**S3 schema — Quiz:**

```json
{
  "core_concept": "Modularity",
  "total_leaf_concepts": 10,
  "questions": [
    {
      "id": "uuid",
      "core_concept": "Modularity",
      "leaf_concepts": ["Coupling Factor α", "Cohesion Metric"],
      "question": "What does α_good represent in the coupling model?",
      "type": "multiple_choice",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct": "B",
      "difficulty": "medium",
      "explanation": "..."
    }
  ],
  "generated_at": "2026-04-18T12:00:00Z"
}
```

### 3.2 Flashcard Generation (per core concept)

| Step | Source | Detail |
|---|---|---|
| 1. Get concepts | Cognee | Same concept list from step 3.1 |
| 2. Get leaf material | Cognee | `get_quiz_material(course_id, concept)` — reuse same query |
| 3. Generate cards | Bedrock Haiku | Extract important leaf concepts as front/back pairs |
| 4. Store | S3 | `flashcards/course_{id}/{concept}.json` |

Flashcards focus on **important leaf concepts** — the LLM prompt instructs Haiku to prioritize concepts that are most likely to appear on exams or that form prerequisites for other topics.

**S3 schema — Flashcard:**

```json
{
  "core_concept": "Modularity",
  "total_leaf_concepts": 10,
  "cards": [
    {
      "id": "uuid",
      "core_concept": "Modularity",
      "leaf_concepts": ["Coupling Factor α"],
      "front": "What does α_good represent?",
      "back": "The ratio of good (intended) coupling to total coupling in a module dependency graph.",
      "difficulty": "medium"
    }
  ],
  "generated_at": "2026-04-18T12:00:00Z"
}
```

### 3.3 Summary Generation (per lecture)

| Step | Source | Detail |
|---|---|---|
| 1. Get lecture list | Cognee | `query_course_knowledge(course_id, "list all lectures/chapters")` |
| 2. Summarize each | Bedrock Sonnet | ~3 sentences + key takeaways per lecture |
| 3. Store | S3 | `summaries/course_{id}/{lecture_name}.json` |

Summaries are scoped to **lectures**, not core concepts. They provide a quick overview for students deciding what to review.

**S3 schema — Summary:**

```json
{
  "lecture": "Chapter 2.1.1 - Modularity",
  "summary": "3-sentence summary of the lecture content.",
  "key_takeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"],
  "generated_at": "2026-04-18T12:00:00Z"
}
```

### 3.4 Model usage

| Content type | Model | Rationale |
|---|---|---|
| Quizzes | Sonnet | Needs reasoning for plausible wrong answers |
| Flashcards | Haiku | Extraction task, speed matters |
| Summaries | Sonnet | Coherent multi-sentence synthesis |

---

## 4. Quiz & Flashcard Serving

### 4.1 Student requests

```python
class QuizRequest(BaseModel):
    student_id: str
    course_id: str
    num_questions: int = Field(10, ge=5, le=30)
    core_concepts: list[str] = []  # empty = auto-pick weakest

class FlashcardRequest(BaseModel):
    student_id: str
    course_id: str
    num_cards: int = Field(15, ge=5, le=50)
    core_concepts: list[str] = []  # empty = auto-pick weakest
```

### 4.2 Serving flow (same for both)

```
Student sends request (course_id, count, optional concepts)
  │
  ├─ If concepts empty (auto-pick):
  │    Query Postgres: StudentConceptProgressRow for student+course
  │    Rank by mastery_score ascending → pick weakest concepts
  │
  ├─ If concepts provided (manual):
  │    Use those directly
  │
  ├─ For each selected concept:
  │    Download from S3: {type}/course_{id}/{concept}.json
  │    Filter out already-seen IDs (from attempt history in Postgres)
  │    Sample items, weighted toward weaker concepts
  │
  └─ Assemble mixed-concept session → return to frontend
```

**Context at serving time:** S3 (pre-generated content) + Postgres (mastery, past attempts). No Cognee or LLM calls — serving is fast and deterministic.

### 4.3 Answer submission & leaf coverage weighting

Mastery is tracked at the **core concept** level. But a single quiz/flashcard session may only
cover a fraction of a concept's leaf concepts. The mastery update is therefore **weighted by
leaf coverage**: if "Modularity" has 10 leaf concepts but only 3 appeared in the quiz, the
update carries 30% confidence — it shifts mastery less than a session that covered all 10.

Leaf coverage is computed at scoring time by comparing the `leaf_concepts` arrays on the
served questions/cards against the full set in the S3 file for that concept.

**Quiz submission:**
1. Score answers → write `QuizAttemptRow`
2. Group answers by `core_concept`
3. For each concept:
   - Compute per-concept score (correct / total for that concept)
   - Compute leaf coverage ratio (unique leaf concepts in answers / total leaf concepts in S3 file)
   - Update `StudentConceptProgressRow`:
     - `quizzes_taken += 1`, `quizzes_passed += 1` if per-concept score ≥ 0.7
     - `mastery_sources["quiz"]` updated as moving average, dampened by leaf coverage
     - Recompute `mastery_score`

**Flashcard submission:**
1. Write `FlashcardAttemptRow` with per-card ratings
2. Group cards by `core_concept`
3. For each concept:
   - Compute average rating (easy=1.0, medium=0.5, hard=0.0)
   - Compute leaf coverage ratio (same as above, from S3 flashcard file)
   - Update `mastery_sources["flashcard"]`, dampened by leaf coverage
   - Recompute `mastery_score`

---

## 5. Progress Tracking (Postgres)

### 5.1 Modified: `StudentConceptProgressRow`

Two new columns on the existing table:

| Column | Type | Purpose |
|---|---|---|
| `manual_mastery` | `float \| null` | Student self-assessment override. Null = no override. |
| `mastery_sources` | `JSONB` | Per-signal breakdown: `{quiz: 0.7, flashcard: 0.6, exercise: 0.3, lecture: 0.2, manual: 0.8}` |

### 5.2 New: `QuizAttemptRow`

```
quiz_attempts
├── id                  (UUID, PK)
├── student_id          (FK → students.id)
├── course_id           (FK → courses.id)
├── core_concepts       (JSONB — array of concept strings)
├── question_ids        (JSONB — array of question UUIDs)
├── answers             (JSONB — {question_id: {selected: "B", correct: bool, core_concept: "..."}})
├── score               (float 0.0–1.0)
├── created_at          (timestamptz)
├── updated_at          (timestamptz)
INDEX(student_id, course_id)
```

### 5.3 New: `FlashcardAttemptRow`

```
flashcard_attempts
├── id                  (UUID, PK)
├── student_id          (FK → students.id)
├── course_id           (FK → courses.id)
├── core_concepts       (JSONB — array of concept strings)
├── card_ratings        (JSONB — {card_id: "easy"|"medium"|"hard"})
├── created_at          (timestamptz)
├── updated_at          (timestamptz)
INDEX(student_id, course_id)
```

### 5.4 Removed: `QuizResultRow`

The lecture-keyed `QuizResultRow` is replaced by `QuizAttemptRow`. No production data to migrate.

### 5.5 Mastery computation

Five signals feed into concept mastery:

| Signal | Trigger | Weight | Effect |
|---|---|---|---|
| Quiz score | Student submits quiz | 0.40 | Score maps directly |
| Flashcard rating | Student rates cards | 0.15 | easy=1.0, medium=0.5, hard=0.0 averaged |
| Exercise done | Student marks exercise complete | 0.25 | Bump concepts tested by that exercise (via Cognee lookup) |
| Lecture seen | Student marks lecture reviewed | 0.10 | Small bump to concepts covered by that lecture (via Cognee lookup) |
| Manual override | Student sets own level | 0.10 | Blended in; if no activity since override, used as-is |

**Formula:**

```python
if manual_mastery is not None and no_activity_since_override:
    mastery_score = manual_mastery
else:
    mastery_score = (
        0.40 * mastery_sources.get("quiz", 0.0)
        + 0.15 * mastery_sources.get("flashcard", 0.0)
        + 0.25 * mastery_sources.get("exercise", 0.0)
        + 0.10 * mastery_sources.get("lecture", 0.0)
        + 0.10 * mastery_sources.get("manual", manual_mastery or 0.0)
    )
```

`mastery_sources` is updated independently per signal. The composite `mastery_score` is recomputed on every write.

### 5.6 Course-level knowledge

No separate table. Computed on read:

```python
async def get_course_mastery(student_id: str, course_id: str) -> float:
    """Weighted average of mastery_score across all concepts for student+course."""
```

---

## 6. Lecture/Exercise → Concept Linking

When a student marks a lecture as seen or exercise as done:

1. **Lecture seen:** Query Cognee — `query_course_knowledge(course_id, "which core concepts does lecture '{title}' cover?")` → returns concept names → bump `mastery_sources["lecture"]` for each
2. **Exercise done:** Query Cognee — `get_exercise_concept_map(course_id, exercise_name)` → returns concept names → bump `mastery_sources["exercise"]` for each

Both fan out to multiple `StudentConceptProgressRow` entries and recompute `mastery_score`.

---

## 7. Files to Create/Modify

| File | Action | What |
|---|---|---|
| `src/lib/content_generator.py` | **Create** | Replaces `src/lib/quiz.py`. Quiz + flashcard + summary generation. |
| `src/lib/quiz.py` | **Delete** | Superseded by content_generator.py |
| `src/lib/quiz_serving.py` | **Create** | Quiz/flashcard sampling, scoring, progress updates. |
| `src/lib/cognify.py` | **Modify** | Change completion hook to call `content_generator.generate_all_for_course` |
| `src/storage/schema.py` | **Modify** | Add `QuizAttemptRow`, `FlashcardAttemptRow`, new columns on `StudentConceptProgressRow`, remove `QuizResultRow` |
| `src/models/quiz.py` | **Create** | Pydantic models: `QuizRequest`, `FlashcardRequest`, `QuizAttempt`, `FlashcardAttempt` |
| `src/api/quiz.py` | **Create** | REST endpoints: request quiz, submit answers, request flashcards, submit ratings |
| `src/agents/academic/tools.py` | **Modify** | Add `take_quiz`, `review_flashcards`, `get_progress`, `set_mastery` tools |
| `src/config.py` | **Modify** | Add `quiz_s3_prefix`, `flashcard_s3_prefix`, `summary_s3_prefix` if needed |

---

## 8. S3 Key Layout

```
s3://{bucket}/
├── quizzes/course_{id}/{concept}.json
├── flashcards/course_{id}/{concept}.json
├── summaries/course_{id}/{lecture_name}.json
└── slides/{dataset_name}/{filename}.pdf      (existing)
```

---

## 9. What This Does NOT Cover

- Spaced repetition scheduling for flashcards (future: integrate SM-2 or similar)
- Quiz difficulty adaptation based on past performance (future: dynamic difficulty)
- Incremental content generation (future: concept manifest diffing)
- Flashcard image support (future: diagram extraction from slides)
- Frontend implementation (separate spec)
