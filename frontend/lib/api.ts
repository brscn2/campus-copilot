const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  })
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`)
  }
  return res.json() as Promise<T>
}

// --- Pipeline ---

export interface PipelineResult {
  downloads: Record<string, unknown>[]
  extractions: Record<string, unknown>[]
  ingestions: Record<string, unknown>[]
}

export function runFullPipeline(semester?: string): Promise<PipelineResult> {
  return request("/api/pipeline/run", {
    method: "POST",
    body: JSON.stringify({ semester: semester ?? null }),
  })
}

export interface CourseFile {
  key: string
  size: number
  last_modified: string
}

export function listCourseFiles(courseId: string): Promise<{ files: CourseFile[] }> {
  return request(`/api/pipeline/files/${encodeURIComponent(courseId)}`)
}

export function getFileUrl(courseId: string, filename: string): Promise<{ url: string; key: string }> {
  return request(`/api/pipeline/files/${encodeURIComponent(courseId)}/${encodeURIComponent(filename)}/url`)
}

// --- Synced courses ---

export interface SyncedCourse {
  dataset_name: string
  display_name: string
  course_code: string
  semester: string
  pdf_count: number
  s3_prefix: string
}

export function listSyncedCourses(studentId: string = "demo"): Promise<{ courses: SyncedCourse[] }> {
  return request(`/api/pipeline/synced?student_id=${encodeURIComponent(studentId)}`)
}

// --- Course metadata overrides (semester re-categorisation) ---
//
// Backed by the `students.course_overrides` JSONB column.  These keep the
// stable Cognee `dataset_name` untouched so quizzes / flashcards / S3 keys all
// continue to work — only the displayed semester bucket changes.

export type CourseOverrides = Record<string, { semester?: string }>

export function listCourseOverrides(
  studentId: string = "demo",
): Promise<{ overrides: CourseOverrides }> {
  return request(
    `/api/pipeline/synced/overrides?student_id=${encodeURIComponent(studentId)}`,
  )
}

export function setCourseSemesterOverride(
  datasetName: string,
  semester: string,
  studentId: string = "demo",
): Promise<{ overrides: CourseOverrides }> {
  return request(
    `/api/pipeline/synced/overrides/${encodeURIComponent(datasetName)}`,
    {
      method: "PUT",
      body: JSON.stringify({ student_id: studentId, semester }),
    },
  )
}

export function deleteCourseOverride(
  datasetName: string,
  studentId: string = "demo",
): Promise<{ overrides: CourseOverrides }> {
  return request(
    `/api/pipeline/synced/overrides/${encodeURIComponent(datasetName)}?student_id=${encodeURIComponent(studentId)}`,
    { method: "DELETE" },
  )
}

export function clearCourseOverrides(
  studentId: string = "demo",
): Promise<{ overrides: CourseOverrides }> {
  return request(
    `/api/pipeline/synced/overrides?student_id=${encodeURIComponent(studentId)}`,
    { method: "DELETE" },
  )
}

// --- Cognify ---

export interface CognifyResult {
  job_id: string
  status: string
}

export function triggerCognify(courseId: string): Promise<CognifyResult> {
  return request("/api/cognify/trigger", {
    method: "POST",
    body: JSON.stringify({ course_id: courseId }),
  })
}

export interface JobStatus {
  job_id: string
  status: string
  course_id: string
  error: string | null
}

export function getCognifyStatus(jobId: string): Promise<JobStatus> {
  return request(`/api/cognify/status/${encodeURIComponent(jobId)}`)
}

// --- Learning (quiz, flashcards, progress) ---

export interface QuizQuestion {
  id: string
  core_concept: string
  leaf_concepts: string[]
  question: string
  options: string[]
  difficulty: string
  correct?: string
  explanation?: string
}

export interface QuizSession {
  course_id: string
  core_concepts: string[]
  questions: QuizQuestion[]
  total_available: number
}

export function requestQuiz(
  studentId: string,
  courseId: string,
  numQuestions: number = 10,
  coreConcepts: string[] = [],
): Promise<QuizSession> {
  return request("/api/learning/quiz", {
    method: "POST",
    body: JSON.stringify({
      student_id: studentId,
      course_id: courseId,
      num_questions: numQuestions,
      core_concepts: coreConcepts,
    }),
  })
}

export interface FlashcardItem {
  id: string
  core_concept: string
  leaf_concepts: string[]
  front: string
  back: string
  difficulty: string
}

export interface FlashcardSession {
  course_id: string
  core_concepts: string[]
  cards: FlashcardItem[]
  total_available: number
}

export interface CourseProgress {
  course_id: string
  overall_mastery: number
  concepts: {
    core_concept: string
    mastery_score: number
    quizzes_taken: number
    quizzes_passed: number
  }[]
}

export function getCourseProgress(studentId: string, courseId: string): Promise<CourseProgress> {
  return request(`/api/learning/progress/${encodeURIComponent(studentId)}/${encodeURIComponent(courseId)}`)
}

export function requestFlashcards(
  studentId: string,
  courseId: string,
  numCards: number = 15,
  coreConcepts: string[] = [],
): Promise<FlashcardSession> {
  return request("/api/learning/flashcards", {
    method: "POST",
    body: JSON.stringify({
      student_id: studentId,
      course_id: courseId,
      num_cards: numCards,
      core_concepts: coreConcepts,
    }),
  })
}

export interface QuizScoreResult {
  score: number
  total: number
  correct: number
  per_concept: Record<string, number>
  mastery_updates: Record<string, number>
}

export function submitQuiz(
  studentId: string,
  courseId: string,
  answers: { question_id: string; selected: string }[],
): Promise<QuizScoreResult> {
  return request("/api/learning/quiz/submit", {
    method: "POST",
    body: JSON.stringify({ student_id: studentId, course_id: courseId, answers }),
  })
}

export interface FlashcardScoreResult {
  per_concept: Record<string, number>
  mastery_updates: Record<string, number>
}

export function submitFlashcards(
  studentId: string,
  courseId: string,
  ratings: { card_id: string; rating: string }[],
): Promise<FlashcardScoreResult> {
  return request("/api/learning/flashcards/submit", {
    method: "POST",
    body: JSON.stringify({ student_id: studentId, course_id: courseId, ratings }),
  })
}

// --- Calendar ---

export interface CalendarEventData {
  id: string | number
  title: string
  day: number
  start: number
  end: number
  agent: "academic" | "career" | "social" | null
  location: string
  conflict?: boolean
  google_event_id?: string | null
}

export function listCalendarEvents(weekOffset?: number): Promise<{ events: CalendarEventData[] }> {
  const params = weekOffset !== undefined ? `?week_offset=${weekOffset}` : ""
  return request(`/api/calendar/events${params}`)
}

export function createCalendarEvent(event: {
  title: string
  starts_at: string
  ends_at: string
  location?: string
  agent?: string
}): Promise<CalendarEventData> {
  return request("/api/calendar/events", {
    method: "POST",
    body: JSON.stringify(event),
  })
}

export function deleteCalendarEvent(eventId: string): Promise<void> {
  return request(`/api/calendar/events/${encodeURIComponent(eventId)}`, {
    method: "DELETE",
  })
}

export function getCalendarStatus(): Promise<{ connected: boolean }> {
  return request("/api/calendar/status")
}
