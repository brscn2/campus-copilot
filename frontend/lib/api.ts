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

// --- Social ---

export interface ZhsCourse {
  id: string
  name: string
  name_de: string
  description: string
  url: string
  poster_url: string
  category: string
  emoji: string
  level: string
  location: string
}

export interface ZhsCategory {
  category: string
  emoji: string
  count: number
}

export interface EsnEvent {
  id: string
  title: string
  description: string
  date: string
  time: string
  end_time: string
  location: string
  organizer: string
  price: string
  spots_available: number | string
  is_full: boolean
  registration_url: string
}

export async function searchZhsCourses(opts?: {
  keyword?: string
  category?: string
  location?: string
  level?: string
}): Promise<ZhsCourse[]> {
  const params = new URLSearchParams()
  if (opts?.keyword) params.set("keyword", opts.keyword)
  if (opts?.category) params.set("category", opts.category)
  if (opts?.location) params.set("location", opts.location)
  if (opts?.level) params.set("level", opts.level)
  const qs = params.toString()
  return request<ZhsCourse[]>(`/api/social/zhs${qs ? `?${qs}` : ""}`)
}

export async function fetchZhsCategories(): Promise<ZhsCategory[]> {
  return request<ZhsCategory[]>("/api/social/zhs/categories")
}

export async function searchEsnEvents(opts?: {
  keyword?: string
  tags?: string
  available_only?: boolean
}): Promise<EsnEvent[]> {
  const params = new URLSearchParams()
  if (opts?.keyword) params.set("keyword", opts.keyword)
  if (opts?.tags) params.set("tags", opts.tags)
  if (opts?.available_only) params.set("available_only", "true")
  const qs = params.toString()
  return request<EsnEvent[]>(`/api/social/events${qs ? `?${qs}` : ""}`)
}

// --- Mensa ---

export interface MensaDish {
  name: string
  dish_type: string
  price: string
  is_vegetarian: boolean
  is_vegan: boolean
  labels: string[]
}

export interface MensaCanteen {
  canteen_id: string
  name: string
  address: string
  latitude: number
  longitude: number
  open_hours: Record<string, { start: string; end: string }>
}

export async function fetchMensaMenu(opts?: {
  mensa?: string
  target_date?: string
  vegetarian_only?: boolean
  vegan_only?: boolean
}): Promise<MensaDish[]> {
  const params = new URLSearchParams()
  if (opts?.mensa) params.set("mensa", opts.mensa)
  if (opts?.target_date) params.set("target_date", opts.target_date)
  if (opts?.vegetarian_only) params.set("vegetarian_only", "true")
  if (opts?.vegan_only) params.set("vegan_only", "true")
  const qs = params.toString()
  return request<MensaDish[]>(`/api/social/mensa${qs ? `?${qs}` : ""}`)
}

export async function fetchMensaCanteens(): Promise<MensaCanteen[]> {
  return request<MensaCanteen[]>("/api/social/mensa/canteens")
}

// --- ZHS Booking (Playwright automation) ---

export interface ZhsWeeklyCourse {
  index: number
  name?: string
  date_range?: string
  schedule?: string
  location?: string
  price?: string
  leader?: string
  status?: string
  book_button_id?: string
  disabled?: boolean
}

export interface ZhsSlot {
  day: string
  date: string
  time: string
  description: string
  id: string
  disabled: boolean
  available: boolean
}

export interface ZhsSchedule {
  type: "weekly_course" | "free_play" | "unknown"
  title: string
  url: string
  courses: ZhsWeeklyCourse[]
  slots: ZhsSlot[]
  message?: string
}

export interface ZhsBookingResult {
  status: string
  message: string
  url?: string
  checkout_url?: string
  course_details?: ZhsSchedule
}

export async function fetchZhsSchedule(courseName: string): Promise<ZhsSchedule> {
  return request<ZhsSchedule>(
    `/api/social/zhs/schedule?course_name=${encodeURIComponent(courseName)}`
  )
}

export async function bookZhsCourse(opts: {
  course_name: string
  course_index?: number
  slot_id?: string
}): Promise<ZhsBookingResult> {
  return request<ZhsBookingResult>("/api/social/zhs/book", {
    method: "POST",
    body: JSON.stringify({
      course_name: opts.course_name,
      course_index: opts.course_index ?? 0,
      slot_id: opts.slot_id ?? "",
    }),
  })
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

// --- User Profile (Settings) ---

export interface TumStudentData {
  firstname: string
  lastname: string
  email: string
  matriculation_number: string
  program: string
}

export interface ProfileFormData {
  first_name: string
  last_name: string
  email: string
  program: string
  semester: number
  matriculation_number: string
}

export function fetchTumStudent(username: string): Promise<TumStudentData> {
  return request(`/api/profile/tum/${encodeURIComponent(username)}`)
}

export function getProfile(): Promise<ProfileFormData> {
  return request("/api/profile")
}

export function saveProfile(data: ProfileFormData): Promise<ProfileFormData> {
  return request("/api/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  })
}

// --- Career Profile ---

export interface ProfileSkill {
  name: string
  level: number
  source: string
}

export interface ProfileGrade {
  course_code: string
  title: string
  grade: string
  credits: number
  semester: string
  examiner: string
}

export interface ProfileLecture {
  title: string
  code: string
  type: string
  chair: string
}

export interface StudentProfile {
  name: string
  username: string
  headline: string
  summary: string
  program: string
  degree: string
  gpa: number | null
  skills: ProfileSkill[]
  grades: ProfileGrade[]
  current_lectures: ProfileLecture[]
}

export function getStudentProfile(): Promise<StudentProfile> {
  return request("/api/career/profile")
}

// --- Job Matching ---

export interface MatchedJob {
  id: string
  title: string
  company: string
  kind: string
  location: string
  salary: string
  description: string
  source_url: string
  posted_at: string
  match_score: number
  reasoning: string
}

export function listMatchedJobs(kind: string = "working_student"): Promise<MatchedJob[]> {
  return request(`/api/career/jobs/matched?kind=${encodeURIComponent(kind)}`)
}

// --- Career Events ---

export interface CareerEvent {
  title: string
  url: string
  date: string
  time: string
  organizer: string
  location: string
  status: string
  image: string
  fit_score: number
  reason: string
}

export function listCareerEvents(): Promise<CareerEvent[]> {
  return request("/api/career/events")
}

// --- CV Audit ---

export interface CvFlag {
  level: "critical" | "warning" | "good"
  text: string
}

export interface CvSuggestion {
  label: string
  original: string
  suggested: string
}

export interface CvAuditResult {
  filename: string
  flags: CvFlag[]
  suggestions: CvSuggestion[]
}

export async function uploadCvForAudit(file: File): Promise<CvAuditResult> {
  const form = new FormData()
  form.append("file", file)
  const res = await fetch(`${API_BASE}/api/career/cv/audit`, {
    method: "POST",
    body: form,
  })
  if (!res.ok) {
    throw new Error(`CV audit failed: ${res.status} ${await res.text()}`)
  }
  return res.json() as Promise<CvAuditResult>
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

// --- Agent Activity ---

export interface ActivityItem {
  id: string
  agent: "academic" | "career" | "social"
  icon: string
  text: string
  created_at: string
}

export function listActivity(limit: number = 20): Promise<{ activities: ActivityItem[] }> {
  return request(`/api/activity?limit=${limit}`)
}
