# Settings Profile Auto-Fill — Design Spec

**Date:** 2026-04-19
**Status:** Draft

---

## Goal

Add editable profile fields to the existing `/settings` page. Users enter their TUM username, click "Fetch from TUMonline", and the form auto-fills from the NAT Student API. Users can edit any field and save to the database.

---

## Editable Fields

| Field | Auto-filled from NAT API | Fallback |
|---|---|---|
| First name | `firstname` | Manual entry |
| Last name | `lastname` | Manual entry |
| Email | `email` | Manual entry |
| Program | `enrolements[0]` (if available) | Manual entry |
| Semester | Manual only | Manual entry |
| Matriculation number | `matrikel` | Manual entry |

---

## Backend

### New integration function: `fetch_nat_student`

**File:** `src/integrations/tumonline.py`

Calls the NAT Student API:
```
GET https://api.srv.nat.tum.de/api/v1/students/{username}
```

- Authenticates via Keycloak token (reuses existing `_fetch_nat_token()`)
- Validates username matches `^[a-z]{2}[0-9]{2}[a-z]{3}$`
- Returns a Pydantic model with the mapped fields
- Wraps in retry/error handling consistent with existing integration patterns

### New API router: `src/api/profile.py`

Two endpoints:

**`GET /api/profile/tum/{username}`** — Fetch student data from NAT API
- Path param `username` validated against the 7-char pattern
- Calls `fetch_nat_student(username)`
- Returns: `{ firstname, lastname, email, matriculation_number, program }`
- Error: 422 for invalid username, 502 if NAT API is down

**`PUT /api/profile`** — Save profile to database
- Request body: `{ first_name, last_name, email, program, semester, matriculation_number }`
- Updates `StudentRow` for `DEMO_STUDENT_ID`
- Returns the saved profile

### Schema migration

Add columns to `StudentRow` in `src/storage/schema.py`:
- `first_name: Mapped[str | None]` (String(255), nullable)
- `last_name: Mapped[str | None]` (String(255), nullable)
- `matriculation_number: Mapped[str | None]` (String(20), nullable)

The existing columns `tum_email`, `program`, and `semester` are already present.

Generate an Alembic migration for the new columns.

### Route registration

Register the new `profile` router in `src/main.py` under `/api`.

---

## Frontend

### Settings page changes (`frontend/app/settings/page.tsx`)

Replace the current static Profile card with an interactive form:

1. **TUM Username input** — 7-char field with a "Fetch from TUMonline" button next to it
2. **Form fields** — First name, Last name, Email, Program, Semester, Matriculation number
   - All editable `<Input>` components
   - Pre-populated on page load via `GET /api/profile` (saved data from DB)
   - Auto-filled when user clicks "Fetch from TUMonline"
3. **Save button** — calls `PUT /api/profile`, shows success/error feedback
4. **Loading states** — spinner on the fetch button while NAT API call is in progress, disabled inputs during save

### New API client functions (`frontend/lib/api.ts`)

```typescript
interface TumStudentData {
  firstname: string
  lastname: string
  email: string
  matriculation_number: string
  program: string
}

function fetchTumStudent(username: string): Promise<TumStudentData>
function saveProfile(data: ProfileFormData): Promise<ProfileFormData>
function getProfile(): Promise<ProfileFormData>
```

---

## What stays the same

- The Connections card and Agent Autonomy card on the settings page are untouched
- The existing `GET /api/career/profile` endpoint is unaffected (it serves a different purpose — career-oriented profile with skills/grades)
- The sidebar avatar/name display continues to use `mock-data.ts` user object (could be wired up later)

---

## Out of scope

- Avatar upload
- Multi-user support (stays on `DEMO_STUDENT_ID`)
- Wiring sidebar display name to saved profile
- Validation of TUM email format beyond standard email validation
