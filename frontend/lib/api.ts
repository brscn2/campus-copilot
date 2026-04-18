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
  course_id: string
  job_id: string
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
