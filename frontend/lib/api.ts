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

export function listSyncedCourses(): Promise<{ courses: SyncedCourse[] }> {
  return request("/api/pipeline/synced")
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
