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
