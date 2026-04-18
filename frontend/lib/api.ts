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
