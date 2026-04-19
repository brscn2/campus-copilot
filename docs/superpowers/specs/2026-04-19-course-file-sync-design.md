# Course File Sync, Mastery Dashboard & Student Activity Tracking

> Design spec for auto-syncing S3 course files to Postgres, on-the-fly concept mastery computation, manual mastery boost, and per-student lecture/exercise completion tracking.

## Problem

Courses uploaded to S3 via the Moodle pipeline are not persisted in Postgres. The `list_synced_courses` endpoint reads S3 on every request. There is no record of individual lecture/exercise files, no way to enrich them with KG metadata, and no mechanism for students to track which materials they have completed.

## Goals

1. Automatically sync the S3 `slides/` file inventory into a `course_files` Postgres table on startup and after pipeline ingest.
2. Categorize each file as `lecture` or `exercise` based on filename regex.
3. Enrich new files with related `core_concepts` from the Cognee knowledge graph at sync time.
4. Provide a per-student `student_file_progress` table so students can mark files as done.
5. Expose API endpoints for listing files with progress and toggling completion.
6. Compute per-concept mastery on-the-fly from lecture/exercise completion, quiz results, flashcard ratings, and a manual boost.
7. Let students set a manual mastery boost (flat %) per concept, stored in the existing `manual_mastery` column on `StudentConceptProgressRow`.

## Non-Goals

- Replacing the existing `CourseRow`/`LectureRow` schema (those serve student-specific enrollment, not shared file inventory).
- Changing how the `list_synced_courses` endpoint works (it continues to read S3 prefixes for the course list).
- Real-time S3 event notifications (we rely on startup + post-pipeline sync triggers).

---

## Data Model

### Table: `course_files`

Shared file inventory — one row per PDF in S3, not per-student.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, auto-generated | |
| `dataset_name` | `String(100)` | NOT NULL, indexed | S3 folder name under `slides/` |
| `s3_key` | `String(500)` | UNIQUE, NOT NULL | Full S3 key: `slides/<dataset>/<file>.pdf` |
| `filename` | `String(500)` | NOT NULL | Original filename from S3 |
| `display_name` | `String(500)` | NOT NULL | Cleaned filename (strip numbers, extension) |
| `category` | `String(20)` | NOT NULL | `"lecture"` or `"exercise"` |
| `sort_order` | `Integer` | NOT NULL, default 0 | Number extracted from filename for natural ordering |
| `core_concepts` | `JSONB` | NOT NULL, default `[]` | `["Trees", "Graph Traversal"]` from KG |
| `created_at` | `DateTime(tz)` | auto | |
| `updated_at` | `DateTime(tz)` | auto | |

**Indexes:** `ix_course_files_dataset` on `dataset_name`.

### Table: `student_file_progress`

Per-student completion tracking — one row per (student, file) pair.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, auto-generated | |
| `student_id` | `UUID` (FK → `students.id`) | NOT NULL | |
| `course_file_id` | `UUID` (FK → `course_files.id`) | NOT NULL | |
| `completed` | `Boolean` | NOT NULL, default `false` | The toggle |
| `completed_at` | `DateTime(tz)` | nullable | When marked done |
| `created_at` | `DateTime(tz)` | auto | |
| `updated_at` | `DateTime(tz)` | auto | |

**Constraints:** Unique on `(student_id, course_file_id)`.

---

## Sync Logic

### Function: `sync_course_files_from_s3(db: AsyncSession) -> SyncResult`

Located in `src/storage/repositories/course_files.py`.

**Steps:**

1. **List S3 objects** — `list_objects("slides/")`, collect all keys with `len(parts) >= 3`.
2. **Parse each key** into:
   - `dataset_name` — `parts[1]`
   - `filename` — `parts[2]`
   - `category` — regex match on filename: patterns containing `exercise`, `übung`, `uebung`, `homework`, `assignment`, `aufgabe`, `blatt` → `"exercise"`, else `"lecture"`
   - `sort_order` — extract leading integer from filename (e.g. `03_lecture.pdf` → 3), default 0
   - `display_name` — strip leading numbers/underscores/dashes, strip file extension, replace underscores with spaces, title-case
3. **Fetch existing rows** — `SELECT s3_key FROM course_files` to get the current set.
4. **Upsert new files** — for each S3 key not in existing set, INSERT with `core_concepts=[]`.
5. **Delete stale rows** — for each existing `s3_key` not in the S3 listing, DELETE from `course_files`. Cascading delete also removes associated `student_file_progress` rows.
6. **Enrich with KG** — for each newly inserted file, query Cognee: `"Which core concepts does <filename> cover?"` scoped to `course_<dataset_name>`. Update `core_concepts`. If Cognee is unavailable or dataset not cognified, leave as `[]` and log warning.

**Idempotency:** keyed on `s3_key` uniqueness. Running sync twice produces the same state.

**Return:** `SyncResult(inserted=N, deleted=N, enriched=N)` for logging.

### Triggers

1. **On startup** — in `lifespan()` after the DB connectivity check, call `sync_course_files_from_s3`.
2. **After pipeline ingest** — at the end of `POST /api/pipeline/ingest` and `POST /api/pipeline/run`, call `sync_course_files_from_s3`.

---

## Filename Parsing

### Category regex

```python
_EXERCISE_RE = re.compile(
    r"(exercise|übung|uebung|homework|assignment|aufgabe|blatt)",
    re.IGNORECASE,
)
```

If `_EXERCISE_RE.search(filename)` matches → `"exercise"`, else → `"lecture"`.

### Sort order extraction

```python
_LEADING_NUM_RE = re.compile(r"^(\d+)")
```

Extract from filename stem. Default to 0 if no leading number.

### Display name derivation

1. Strip file extension
2. Strip leading numbers + separators (`01_`, `03 - `)
3. Replace `_` and `-` with spaces
4. Collapse multiple spaces
5. Title-case

Example: `03_binary_search_trees.pdf` → `"Binary Search Trees"`

---

## KG Enrichment

For each new file, query:

```
"Which core concepts does '<filename>' cover? Return only concept names as a JSON list."
```

Scoped to Cognee dataset `course_<dataset_name>`.

**Error handling:** wrap in try/except. On failure, set `core_concepts = []` and log at WARNING. The file row is still created — enrichment is best-effort.

**Future improvement:** a background job could retry enrichment for files with empty `core_concepts`.

---

## API Endpoints

### `GET /api/pipeline/synced/{dataset_name}/files`

List all files for a course, annotated with the student's completion status.

**Query params:** `student_id` (default `"demo"`)

**Response:**

```json
{
  "files": [
    {
      "id": "uuid",
      "dataset_name": "machine_learning_in2064_sose2025",
      "s3_key": "slides/machine_learning_in2064_sose2025/03_trees.pdf",
      "filename": "03_trees.pdf",
      "display_name": "Trees",
      "category": "lecture",
      "sort_order": 3,
      "core_concepts": ["Decision Trees", "Random Forests"],
      "completed": false,
      "completed_at": null
    }
  ],
  "summary": {
    "total": 12,
    "completed": 5,
    "lectures": {"total": 8, "completed": 4},
    "exercises": {"total": 4, "completed": 1}
  }
}
```

**Implementation:** LEFT JOIN `course_files` with `student_file_progress` on `(course_file_id, student_id)`. Order by `category, sort_order, filename`.

### `PUT /api/pipeline/synced/{dataset_name}/files/{file_id}/progress`

Toggle completion for a student.

**Body:**

```json
{
  "student_id": "demo",
  "completed": true
}
```

**Implementation:** upsert into `student_file_progress`. If `completed=true`, set `completed_at=now()`. If `completed=false`, set `completed_at=null`.

**Response:** the updated file object with `completed` and `completed_at`.

---

## On-the-Fly Concept Mastery

### Overview

Each course's core concepts (from the KG) are shown to the student with a mastery percentage. This is computed at query time — no materialized score to keep in sync.

### Concept discovery

The full concept list for a dataset is the **union** of:
1. All distinct values in `course_files.core_concepts` JSONB arrays for that `dataset_name`
2. All distinct `core_concept` values in `StudentConceptProgressRow` for that `course_id` (dataset_name)

This ensures concepts that only appear in quiz/flashcard history (but not on any file) still show up.

### Data sources

| Signal | Source table | How it maps to a concept |
|---|---|---|
| Lectures viewed | `student_file_progress` JOIN `course_files` WHERE `category='lecture'` | File's `core_concepts` JSONB contains the concept name |
| Exercises done | `student_file_progress` JOIN `course_files` WHERE `category='exercise'` | File's `core_concepts` JSONB contains the concept name |
| Quiz performance | `StudentConceptProgressRow` | Direct match on `core_concept` column |
| Flashcard performance | `FlashcardAttemptRow` | `core_concepts` JSONB list contains the concept name |
| Manual boost | `StudentConceptProgressRow.manual_mastery` | Direct match on `core_concept` column |

### Formula

```
lecture_pct    = (lectures covering concept marked done) / (total lectures covering concept) × 100
exercise_pct   = (exercises covering concept marked done) / (total exercises covering concept) × 100
quiz_pct       = (quizzes_passed / quizzes_taken) × 100    [0 if no quizzes taken]
flashcard_pct  = avg(numeric_rating for concept) × 100       [0 if no flashcards]
                 rating map: "again"=0.0, "hard"=0.33, "good"=0.66, "easy"=1.0
manual_boost   = StudentConceptProgressRow.manual_mastery   [0 if not set]

weighted = lecture_pct × 0.20
         + exercise_pct × 0.30
         + quiz_pct × 0.35
         + flashcard_pct × 0.15

mastery = min(100, weighted + manual_boost)
```

**Notes:**
- If a signal has no data (e.g. no quizzes taken yet), that signal contributes 0 and the weights stay the same. This means early mastery is naturally low — completing lectures alone caps you around 20%, which feels right as motivation to do exercises and quizzes too.
- `manual_boost` is additive, not multiplicative. A student who sets 40% boost and has 70% from signals sees 100%.
- All percentages are 0–100 scale.

### Function: `compute_concept_mastery(db, student_id, dataset_name) -> list[ConceptMastery]`

Located in `src/storage/repositories/course_files.py`.

**Returns:**

```python
@dataclass
class ConceptMastery:
    concept: str
    mastery: float          # 0–100, capped
    lecture_pct: float      # 0–100
    exercise_pct: float     # 0–100
    quiz_pct: float         # 0–100
    flashcard_pct: float    # 0–100
    manual_boost: float     # 0–100
```

This gives the frontend enough detail to show a breakdown (e.g. a stacked bar per signal).

### Manual Boost

**Storage:** reuse the existing `StudentConceptProgressRow.manual_mastery` Float column. Stores a value 0–100 representing the flat percentage to add.

**Endpoint:** `PUT /api/pipeline/synced/{dataset_name}/concepts/{concept_name}/boost`

**Body:**

```json
{
  "student_id": "demo",
  "boost": 25.0
}
```

**Validation:** `boost` must be >= 0 and <= 100.

**Implementation:** upsert `StudentConceptProgressRow` for `(student_id, dataset_name, concept_name)`, setting `manual_mastery = boost`.

### Concepts + Mastery API

**Endpoint:** `GET /api/pipeline/synced/{dataset_name}/concepts`

**Query params:** `student_id` (default `"demo"`)

**Response:**

```json
{
  "concepts": [
    {
      "name": "Decision Trees",
      "mastery": 65.0,
      "breakdown": {
        "lectures": 80.0,
        "exercises": 50.0,
        "quizzes": 70.0,
        "flashcards": 40.0,
        "manual_boost": 10.0
      }
    }
  ]
}
```

---

## Migration

One new Alembic migration adding both tables. The `student_file_progress.course_file_id` FK has `ON DELETE CASCADE` so removing a stale file during sync automatically cleans up progress rows.

---

## File Layout

| File | Purpose |
|---|---|
| `src/storage/schema.py` | Add `CourseFileRow` and `StudentFileProgressRow` ORM models |
| `alembic/versions/<hash>_add_course_files.py` | Migration for both tables |
| `src/storage/repositories/course_files.py` | `sync_course_files_from_s3`, file queries, progress upsert, `compute_concept_mastery`, manual boost upsert |
| `src/api/pipeline.py` | New endpoints: files listing, progress toggle, concepts+mastery, manual boost |
| `src/main.py` | Call sync in `lifespan()` |

---

## Testing

- **Unit:** `sync_course_files_from_s3` with mocked S3 listing — verify insert, upsert idempotency, stale deletion, category/sort parsing.
- **Unit:** filename parsing edge cases (no number, German names, mixed case).
- **Unit:** progress toggle upsert — toggle on, toggle off, re-toggle.
- **Unit:** `compute_concept_mastery` — verify weighted formula, capping at 100, each signal contributing correctly, zero-data edge cases.
- **Unit:** manual boost — set, update, verify it adds to computed mastery, verify cap at 100.
- **Integration:** full flow — sync files, toggle progress, take quiz, set boost, verify mastery endpoint returns correct breakdown.
