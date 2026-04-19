"use client"

import * as React from "react"
import { PageHeader } from "@/components/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  runFullPipeline,
  listCourseFiles,
  listEnrichedFiles,
  toggleFileProgress,
  getFileUrl,
  listSyncedCourses,
  listCourseOverrides,
  setCourseSemesterOverride,
  clearCourseOverrides,
  getCourseProgress,
  requestQuiz,
  requestFlashcards,
  submitQuiz,
  submitFlashcards,
  listLibraryBranches,
  searchLibraryRooms,
  bookLibraryRoom,
  type CourseFile,
  type EnrichedFile,
  type FileSummary,
  type SyncedCourse,
  type QuizQuestion,
  type FlashcardItem,
  type LibraryBranch,
  type RoomSearchResult,
  type ScrapedRoom,
  listDeadlines,
  listTheses,
  createCalendarEvent,
  type Deadline,
  type ThesisOpportunity,
} from "@/lib/api"
import { AgentBadge } from "@/components/agent-badge"
import {
  ArrowRight,
  ArrowUpDown,
  BookOpen,
  Check,
  Calendar as CalendarIcon,
  ChevronRight,
  Clock,
  Download,
  FileText,
  GripVertical,
  Layers,
  Loader2,
  ExternalLink,
  Mail,
  MapPin,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Undo2,
  Users as UsersIcon,
} from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

const _SEMESTER_RE = /(SoSe|WiSe)\s+(\d{4})/
const _UNKNOWN_SEMESTER = "Other"

function semesterSortKey(label: string): number {
  const m = _SEMESTER_RE.exec(label)
  if (!m) return -Infinity
  const year = Number.parseInt(m[2], 10)
  return year * 2 + (m[1] === "WiSe" ? 1 : 0)
}

function groupCoursesBySemester(
  courses: SyncedCourse[],
): { semester: string; key: number; items: SyncedCourse[] }[] {
  const buckets = new Map<string, SyncedCourse[]>()
  for (const c of courses) {
    const label = c.semester || _UNKNOWN_SEMESTER
    const bucket = buckets.get(label)
    if (bucket) bucket.push(c)
    else buckets.set(label, [c])
  }
  return [...buckets.entries()]
    .map(([semester, items]) => ({
      semester,
      key: semesterSortKey(semester),
      items: [...items].sort((a, b) => a.display_name.localeCompare(b.display_name)),
    }))
    .sort((a, b) => b.key - a.key)
}

// Semester overrides are persisted on the backend via
// `students.course_overrides` (see src/storage/repositories/course_overrides.py)
// keyed by Cognee `dataset_name` so quiz / flashcard / S3 paths stay stable.
const COURSE_DRAG_MIME = "application/x-campus-course-dataset"
const STUDENT_ID = "demo"

export default function AcademicPage() {
  return (
    <div>
      <PageHeader
        title="Academic"
        description="Summaries, deadlines, thesis matches, and rooms — coordinated by your Academic Agent."
        actions={<AgentBadge agent="academic" className="px-2.5 py-1" />}
      />

      <Tabs defaultValue="courses" className="w-full">
        <TabsList className="mb-5 w-full max-w-xl">
          <TabsTrigger value="courses">Courses</TabsTrigger>
          <TabsTrigger value="deadlines">Deadlines</TabsTrigger>
          <TabsTrigger value="thesis">Thesis Matcher</TabsTrigger>
          <TabsTrigger value="rooms">Study Room</TabsTrigger>
        </TabsList>

        <TabsContent value="courses">
          <CoursesTab />
        </TabsContent>
        <TabsContent value="deadlines">
          <DeadlinesTab />
        </TabsContent>
        <TabsContent value="thesis">
          <ThesisTab />
        </TabsContent>
        <TabsContent value="rooms">
          <StudyRoomTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function CoursesTab() {
  const [selectedSynced, setSelectedSynced] = React.useState<SyncedCourse | null>(null)
  const [syncing, setSyncing] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [syncedCourses, setSyncedCourses] = React.useState<SyncedCourse[]>([])
  const [masteryMap, setMasteryMap] = React.useState<Record<string, number>>({})
  const [overrides, setOverrides] = React.useState<Record<string, { semester?: string }>>({})
  const [extraSemesters, setExtraSemesters] = React.useState<string[]>([])
  const [draggingId, setDraggingId] = React.useState<string | null>(null)
  const [dropTarget, setDropTarget] = React.useState<string | null>(null)
  const [addingSemester, setAddingSemester] = React.useState(false)
  const [newSemester, setNewSemester] = React.useState("")

  React.useEffect(() => {
    listCourseOverrides(STUDENT_ID)
      .then((res) => setOverrides(res.overrides))
      .catch(() => {
        // Endpoint not reachable (offline or backend down) — no overrides applied.
      })
  }, [])

  React.useEffect(() => {
    listSyncedCourses(STUDENT_ID)
      .then((res) => {
        setSyncedCourses(res.courses)
        for (const sc of res.courses) {
          getCourseProgress(STUDENT_ID, sc.dataset_name)
            .then((p) => setMasteryMap((prev) => ({ ...prev, [sc.dataset_name]: Math.round(p.overall_mastery * 100) })))
            .catch(() => {})
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = await runFullPipeline()
      const ingested = result.ingestions?.filter((i) => i.status === "ingesting").length ?? 0
      toast.success(`Pipeline complete: ${ingested} courses ingested to S3 + Cognee`)
      const synced = await listSyncedCourses(STUDENT_ID)
      setSyncedCourses(synced.courses)
    } catch (err) {
      toast.error(`Pipeline failed: ${err instanceof Error ? err.message : "Unknown error"}`)
    } finally {
      setSyncing(false)
    }
  }

  const setOverride = React.useCallback(async (datasetName: string, semester: string) => {
    // Optimistic update so the card moves immediately.
    setOverrides((prev) => ({ ...prev, [datasetName]: { semester } }))
    try {
      const res = await setCourseSemesterOverride(datasetName, semester, STUDENT_ID)
      setOverrides(res.overrides)
    } catch (err) {
      toast.error(
        `Could not save the new semester: ${err instanceof Error ? err.message : "Unknown error"}`,
      )
      // Roll back to the server's truth.
      try {
        const fresh = await listCourseOverrides(STUDENT_ID)
        setOverrides(fresh.overrides)
      } catch {
        /* leave optimistic state in place */
      }
    }
  }, [])

  const resetOverrides = React.useCallback(async () => {
    const previous = overrides
    setOverrides({})
    setExtraSemesters([])
    try {
      await clearCourseOverrides(STUDENT_ID)
      toast.success("Restored Moodle semester labels")
    } catch (err) {
      setOverrides(previous)
      toast.error(
        `Could not reset overrides: ${err instanceof Error ? err.message : "Unknown error"}`,
      )
    }
  }, [overrides])

  const addExtraSemester = React.useCallback((label: string) => {
    const trimmed = label.trim()
    if (!trimmed) return
    setExtraSemesters((prev) => (prev.includes(trimmed) ? prev : [...prev, trimmed]))
  }, [])

  const effectiveCourses = React.useMemo(
    () =>
      syncedCourses.map((c) => ({
        ...c,
        semester: overrides[c.dataset_name]?.semester ?? c.semester,
      })),
    [syncedCourses, overrides],
  )

  const groups = React.useMemo(() => {
    const fromCourses = groupCoursesBySemester(effectiveCourses)
    const existing = new Set(fromCourses.map((g) => g.semester))
    const empties = extraSemesters
      .filter((s) => !existing.has(s))
      .map((s) => ({ semester: s, key: semesterSortKey(s), items: [] as SyncedCourse[] }))
    return [...fromCourses, ...empties].sort((a, b) => b.key - a.key)
  }, [effectiveCourses, extraSemesters])

  const overrideCount = Object.keys(overrides).length

  const handleDragStart = (e: React.DragEvent<HTMLElement>, datasetName: string) => {
    e.dataTransfer.setData(COURSE_DRAG_MIME, datasetName)
    e.dataTransfer.effectAllowed = "move"
    setDraggingId(datasetName)
  }

  const handleDragEnd = () => {
    setDraggingId(null)
    setDropTarget(null)
  }

  const handleDragOver = (e: React.DragEvent<HTMLElement>, semester: string) => {
    if (!e.dataTransfer.types.includes(COURSE_DRAG_MIME)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    if (dropTarget !== semester) setDropTarget(semester)
  }

  const handleDragLeave = (e: React.DragEvent<HTMLElement>, semester: string) => {
    // Only clear if we're actually leaving the section, not entering a child.
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
    if (dropTarget === semester) setDropTarget(null)
  }

  const handleDrop = (e: React.DragEvent<HTMLElement>, targetSemester: string) => {
    e.preventDefault()
    const datasetName = e.dataTransfer.getData(COURSE_DRAG_MIME)
    setDropTarget(null)
    setDraggingId(null)
    if (!datasetName) return
    const current = effectiveCourses.find((c) => c.dataset_name === datasetName)
    if (!current) return
    if (current.semester === targetSemester) return
    void setOverride(datasetName, targetSemester)
    toast.success(`Moved “${current.display_name}” → ${targetSemester}`)
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">
          {syncedCourses.length > 0
            ? `${syncedCourses.length} course${syncedCourses.length === 1 ? "" : "s"} synced from Moodle · drag a card into a semester to re-categorise`
            : loading
              ? "Loading your Moodle courses…"
              : "No Moodle courses synced yet."}
        </div>
        <Button onClick={handleSync} disabled={syncing} className="gap-2">
          {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {syncing ? "Syncing from Moodle…" : "Sync from Moodle"}
        </Button>
      </div>

      {overrideCount > 0 && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <span>
            {overrideCount} course{overrideCount === 1 ? "" : "s"} re-categorised from the Moodle defaults.
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1.5 px-2 text-xs"
            onClick={() => void resetOverrides()}
          >
            <Undo2 className="h-3.5 w-3.5" />
            Reset to Moodle labels
          </Button>
        </div>
      )}

      <div className="flex flex-col gap-6">
        {groups.map((group) => {
          const isTarget = dropTarget === group.semester
          return (
            <section
              key={group.semester}
              onDragOver={(e) => handleDragOver(e, group.semester)}
              onDragEnter={(e) => handleDragOver(e, group.semester)}
              onDragLeave={(e) => handleDragLeave(e, group.semester)}
              onDrop={(e) => handleDrop(e, group.semester)}
              className={cn(
                "rounded-lg border border-transparent p-2 transition-colors",
                isTarget && "border-primary/40 bg-primary/5",
              )}
            >
              <div className="mb-2 flex items-baseline justify-between">
                <h2 className="text-sm font-medium">{group.semester}</h2>
                <span className="text-xs text-muted-foreground">
                  {group.items.length} course{group.items.length === 1 ? "" : "s"}
                </span>
              </div>
              {group.items.length === 0 ? (
                <div className="flex h-24 items-center justify-center rounded-md border border-dashed border-border text-xs text-muted-foreground">
                  Drop a course here to assign it to {group.semester}
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {group.items.map((sc) => {
                    const mastery = masteryMap[sc.dataset_name] ?? 0
                    const isDragging = draggingId === sc.dataset_name
                    return (
                      <div
                        key={sc.dataset_name}
                        role="button"
                        tabIndex={0}
                        draggable
                        onDragStart={(e) => handleDragStart(e, sc.dataset_name)}
                        onDragEnd={handleDragEnd}
                        onClick={() => setSelectedSynced(sc)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            setSelectedSynced(sc)
                          }
                        }}
                        className={cn(
                          "group cursor-grab text-left outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 active:cursor-grabbing",
                          isDragging && "opacity-50",
                        )}
                      >
                        <Card className="h-full transition-all hover:-translate-y-0.5 hover:shadow-sm">
                          <CardHeader className="pb-3">
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex min-w-0 items-start gap-2">
                                <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/60 transition-colors group-hover:text-muted-foreground" />
                                <div className="min-w-0">
                                  {sc.course_code && (
                                    <div className="font-mono text-xs font-medium text-primary">
                                      {sc.course_code}
                                    </div>
                                  )}
                                  <CardTitle className="mt-0.5 text-base leading-snug">
                                    {sc.display_name}
                                  </CardTitle>
                                </div>
                              </div>
                              {sc.pdf_count > 0 ? (
                                <Badge className="shrink-0 bg-academic-soft text-academic hover:bg-academic-soft">
                                  {sc.pdf_count} PDFs
                                </Badge>
                              ) : (
                                <Badge variant="secondary" className="shrink-0">
                                  No files
                                </Badge>
                              )}
                            </div>
                          </CardHeader>
                          <CardContent>
                            {sc.semester && (
                              <div className="text-xs text-muted-foreground">{sc.semester}</div>
                            )}
                            <div className="mt-3 flex items-center justify-between text-xs">
                              <span className="text-muted-foreground">Mastery</span>
                              <span className="font-medium tabular-nums">{mastery}%</span>
                            </div>
                            <Progress value={mastery} className="mt-1.5 h-1.5" />
                            <div className="mt-3 flex items-center justify-end text-xs text-primary opacity-0 transition-opacity group-hover:opacity-100">
                              Open <ChevronRight className="ml-0.5 h-3 w-3" />
                            </div>
                          </CardContent>
                        </Card>
                      </div>
                    )
                  })}
                </div>
              )}
            </section>
          )
        })}

        {syncedCourses.length > 0 && (
          <div className="flex items-center gap-2">
            {addingSemester ? (
              <form
                className="flex items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  addExtraSemester(newSemester)
                  setNewSemester("")
                  setAddingSemester(false)
                }}
              >
                <Input
                  autoFocus
                  value={newSemester}
                  onChange={(e) => setNewSemester(e.target.value)}
                  placeholder="e.g. WiSe 2025/26"
                  className="h-8 w-48 text-sm"
                />
                <Button type="submit" size="sm" className="h-8">
                  Add
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-8"
                  onClick={() => {
                    setAddingSemester(false)
                    setNewSemester("")
                  }}
                >
                  Cancel
                </Button>
              </form>
            ) : (
              <Button
                size="sm"
                variant="outline"
                className="h-8 gap-1.5"
                onClick={() => setAddingSemester(true)}
              >
                <Plus className="h-3.5 w-3.5" />
                Add semester
              </Button>
            )}
          </div>
        )}
      </div>

      <SyncedCourseDialog course={selectedSynced} onClose={() => setSelectedSynced(null)} />
    </>
  )
}

function SyncedCourseDialog({ course, onClose }: { course: SyncedCourse | null; onClose: () => void }) {
  const [files, setFiles] = React.useState<EnrichedFile[]>([])
  const [summary, setSummary] = React.useState<FileSummary | null>(null)
  const [filesLoading, setFilesLoading] = React.useState(false)
  const [quizOpen, setQuizOpen] = React.useState(false)
  const [flashcardOpen, setFlashcardOpen] = React.useState(false)
  const [configOpen, setConfigOpen] = React.useState<"quiz" | "flashcard" | null>(null)
  const [quizQuestions, setQuizQuestions] = React.useState<QuizQuestion[]>([])
  const [flashcards, setFlashcards] = React.useState<FlashcardItem[]>([])
  const [loadingContent, setLoadingContent] = React.useState(false)
  const [mastery, setMastery] = React.useState(0)

  React.useEffect(() => {
    if (course) {
      setFilesLoading(true)
      listEnrichedFiles(course.dataset_name, STUDENT_ID)
        .then((res) => {
          setFiles(res.files)
          setSummary(res.summary)
        })
        .catch(() => { setFiles([]); setSummary(null) })
        .finally(() => setFilesLoading(false))

      getCourseProgress("demo", course.dataset_name)
        .then((p) => setMastery(Math.round(p.overall_mastery * 100)))
        .catch(() => setMastery(0))
    } else {
      setFiles([])
      setMastery(0)
    }
  }, [course])

  const handleLaunch = async (type: "quiz" | "flashcard", count: number, concept: string) => {
    if (!course) return
    setLoadingContent(true)
    setConfigOpen(null)
    const concepts = concept ? [concept] : []
    try {
      if (type === "quiz") {
        const session = await requestQuiz("demo", course.dataset_name, count, concepts)
        setQuizQuestions(session.questions)
        setQuizOpen(true)
      } else {
        const session = await requestFlashcards("demo", course.dataset_name, count, concepts)
        setFlashcards(session.cards)
        setFlashcardOpen(true)
      }
    } catch (err) {
      toast.error(`Failed to load ${type}: ${err instanceof Error ? err.message : "Unknown error"}`)
    } finally {
      setLoadingContent(false)
    }
  }

  return (
    <>
      <Dialog open={!!course && !quizOpen && !flashcardOpen} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="my-8 max-h-[80vh] max-w-2xl overflow-y-auto pb-6">
          {course ? (
            <>
              <DialogHeader>
                {course.course_code && (
                  <div className="font-mono text-xs text-primary">{course.course_code}</div>
                )}
                <DialogTitle className="text-xl">{course.display_name}</DialogTitle>
                <DialogDescription>
                  {course.semester} · {course.pdf_count} PDFs synced from Moodle
                </DialogDescription>
              </DialogHeader>

              <div className="rounded-lg border border-border bg-muted/40 p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs text-muted-foreground">Overall mastery</div>
                    <div className="text-lg font-semibold tabular-nums">{mastery}%</div>
                  </div>
                  <Progress value={mastery} className="h-2 w-32" />
                </div>
                <div className="mt-3 flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1 gap-1.5"
                    onClick={() => setConfigOpen("flashcard")}
                    disabled={loadingContent}
                  >
                    {loadingContent && configOpen === "flashcard" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Layers className="h-3.5 w-3.5" />
                    )}
                    Flashcards
                  </Button>
                  <Button
                    size="sm"
                    className="flex-1 gap-1.5"
                    onClick={() => setConfigOpen("quiz")}
                    disabled={loadingContent}
                  >
                    {loadingContent && configOpen === "quiz" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Sparkles className="h-3.5 w-3.5" />
                    )}
                    Start quiz
                  </Button>
                </div>
              </div>

              {filesLoading && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading files…
                </div>
              )}

              {files.length > 0 && (
                <div className="space-y-3">
                  {summary && (
                    <div className="flex gap-4 text-xs text-muted-foreground">
                      <span>{summary.lectures.total} lectures</span>
                      <span>{summary.exercises.total} exercises</span>
                      <span>{summary.completed}/{summary.total} completed</span>
                    </div>
                  )}
                  {(["lecture", "exercise"] as const).map((cat) => {
                    const catFiles = files.filter((f) => f.category === cat)
                    if (catFiles.length === 0) return null
                    return (
                      <div key={cat}>
                        <div className="mb-1.5 text-sm font-medium capitalize">{cat}s ({catFiles.length})</div>
                        <div className="max-h-[180px] overflow-y-auto rounded-lg border border-border">
                          <div className="flex flex-col">
                            {catFiles.map((f) => (
                              <div
                                key={f.id}
                                className="flex items-center justify-between border-b border-border p-2 last:border-b-0"
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <button
                                    className={cn(
                                      "flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors",
                                      f.completed
                                        ? "border-primary bg-primary text-primary-foreground"
                                        : "border-border hover:border-primary/50",
                                    )}
                                    onClick={async () => {
                                      const next = !f.completed
                                      setFiles((prev) => prev.map((p) => (p.id === f.id ? { ...p, completed: next } : p)))
                                      setSummary((prev) => prev ? {
                                        ...prev,
                                        completed: prev.completed + (next ? 1 : -1),
                                        [cat === "lecture" ? "lectures" : "exercises"]: {
                                          ...prev[cat === "lecture" ? "lectures" : "exercises"],
                                          completed: prev[cat === "lecture" ? "lectures" : "exercises"].completed + (next ? 1 : -1),
                                        },
                                      } : prev)
                                      await toggleFileProgress(course.dataset_name, f.id, next, STUDENT_ID).catch(() => {
                                        setFiles((prev) => prev.map((p) => (p.id === f.id ? { ...p, completed: !next } : p)))
                                      })
                                    }}
                                  >
                                    {f.completed && <Check className="h-3 w-3" />}
                                  </button>
                                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                                  <span className={cn("truncate text-sm", f.completed && "line-through text-muted-foreground")}>
                                    {f.display_name}
                                  </span>
                                </div>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="shrink-0"
                                  onClick={async () => {
                                    const res = await getFileUrl(course.dataset_name, f.filename)
                                    window.open(res.url, "_blank")
                                  }}
                                >
                                  <Download className="h-3.5 w-3.5" />
                                </Button>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              {!filesLoading && files.length === 0 && (
                <div className="text-sm text-muted-foreground">
                  No files uploaded yet. Run the Moodle sync to pull lecture slides.
                </div>
              )}
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      <ContentConfigDialog
        open={configOpen}
        onClose={() => setConfigOpen(null)}
        onLaunch={handleLaunch}
        loading={loadingContent}
      />

      <LiveQuizDialog
        open={quizOpen}
        onClose={() => setQuizOpen(false)}
        questions={quizQuestions}
        courseCode={course?.course_code ?? course?.display_name ?? ""}
        courseId={course?.dataset_name ?? ""}
        onMasteryUpdate={(m) => setMastery(Math.round(m * 100))}
      />

      <FlashcardDialog
        open={flashcardOpen}
        onClose={() => setFlashcardOpen(false)}
        cards={flashcards}
        courseCode={course?.course_code ?? course?.display_name ?? ""}
        courseId={course?.dataset_name ?? ""}
        onMasteryUpdate={(m) => setMastery(Math.round(m * 100))}
      />
    </>
  )
}

function CourseDetailDialog({ course, onClose }: { course: Course | null; onClose: () => void }) {
  const [quizOpen, setQuizOpen] = React.useState(false)
  const [reviewed, setReviewed] = React.useState<Record<number, boolean>>({})
  const [files, setFiles] = React.useState<CourseFile[]>([])
  const [filesLoading, setFilesLoading] = React.useState(false)

  const datasetName = course ? course.code.toLowerCase().replace(/[^a-z0-9]/g, "") : ""

  React.useEffect(() => {
    if (course) {
      const init: Record<number, boolean> = {}
      course.lectures.forEach((l) => (init[l.id] = l.reviewed))
      setReviewed(init)

      setFilesLoading(true)
      listCourseFiles(datasetName)
        .then((res) => setFiles(res.files))
        .catch(() => setFiles([]))
        .finally(() => setFilesLoading(false))
    } else {
      setFiles([])
    }
  }, [course])

  return (
    <>
      <Dialog open={!!course} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-2xl">
          {course ? (
            <>
              <DialogHeader>
                <div className="font-mono text-xs text-primary">{course.code}</div>
                <DialogTitle className="text-xl">{course.name}</DialogTitle>
                <DialogDescription>
                  {course.professor} · {course.chair} · {course.credits} ECTS
                </DialogDescription>
              </DialogHeader>

              <div className="flex items-center justify-between rounded-lg border border-border bg-muted/40 p-3">
                <div>
                  <div className="text-xs text-muted-foreground">Mastery</div>
                  <div className="text-lg font-semibold tabular-nums">{course.mastery}%</div>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" className="gap-1.5">
                    <Layers className="h-3.5 w-3.5" />
                    Flashcards (28)
                  </Button>
                  <Button size="sm" className="gap-1.5" onClick={() => setQuizOpen(true)}>
                    <Sparkles className="h-3.5 w-3.5" />
                    Generate quiz
                  </Button>
                </div>
              </div>

              <div>
                <div className="mb-2 text-sm font-medium">Slide summaries</div>
                <Accordion type="single" collapsible className="w-full">
                  {course.lectures.map((l) => (
                    <AccordionItem key={l.id} value={`l-${l.id}`}>
                      <div className="flex items-center gap-3">
                        <AccordionTrigger className="flex-1 gap-3">
                          <span className="text-left text-sm font-medium">{l.title}</span>
                        </AccordionTrigger>
                        <div
                          className="flex items-center gap-2 pr-3 text-xs text-muted-foreground"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <span>Reviewed</span>
                          <Switch
                            checked={!!reviewed[l.id]}
                            onCheckedChange={(v) =>
                              setReviewed((prev) => ({ ...prev, [l.id]: v }))
                            }
                            aria-label={`Mark ${l.title} reviewed`}
                          />
                        </div>
                      </div>
                      <AccordionContent className="text-sm text-muted-foreground">
                        {l.summary}
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>
              </div>

              {files.length > 0 && (
                <div>
                  <div className="mb-2 text-sm font-medium">Uploaded files (S3)</div>
                  <div className="flex flex-col gap-1.5">
                    {files.map((f) => {
                      const filename = f.key.split("/").pop() ?? f.key
                      return (
                        <div
                          key={f.key}
                          className="flex items-center justify-between rounded-lg border border-border p-2.5"
                        >
                          <div className="flex items-center gap-2 text-sm">
                            <FileText className="h-4 w-4 text-muted-foreground" />
                            <span>{filename}</span>
                            <span className="text-xs text-muted-foreground">
                              ({(f.size / 1024).toFixed(0)} KB)
                            </span>
                          </div>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="gap-1.5"
                            onClick={async () => {
                              const res = await getFileUrl(datasetName, filename)
                              window.open(res.url, "_blank")
                            }}
                          >
                            <Download className="h-3.5 w-3.5" />
                            Download
                          </Button>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
              {filesLoading && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading files…
                </div>
              )}
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      <QuizDialog open={quizOpen} onClose={() => setQuizOpen(false)} course={course} />
    </>
  )
}

const sampleQuiz = [
  {
    q: "What is the average time complexity of hash table lookup with chaining under a good hash function?",
    options: ["O(log n)", "O(1)", "O(n)", "O(n log n)"],
    correct: 1,
  },
  {
    q: "Which sorting algorithm has worst-case O(n log n) and is in-place?",
    options: ["Merge sort", "Quicksort", "Heapsort", "Insertion sort"],
    correct: 2,
  },
  {
    q: "In BFS on an unweighted graph, the first time a node is dequeued…",
    options: [
      "…we know the shortest path length",
      "…it may still change later",
      "…depends on the start node only",
      "…only if the graph is a tree",
    ],
    correct: 0,
  },
]

function QuizDialog({ open, onClose, course }: { open: boolean; onClose: () => void; course: Course | null }) {
  const [answers, setAnswers] = React.useState<Record<number, number>>({})
  const [submitted, setSubmitted] = React.useState(false)

  React.useEffect(() => {
    if (open) {
      setAnswers({})
      setSubmitted(false)
    }
  }, [open])

  const score = Object.entries(answers).filter(([i, v]) => sampleQuiz[Number(i)].correct === v).length

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            Quiz · {course?.code}
          </DialogTitle>
          <DialogDescription>Auto-generated from your unreviewed lectures.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-5">
          {sampleQuiz.map((item, i) => (
            <div key={i}>
              <div className="mb-2 text-sm font-medium">
                {i + 1}. {item.q}
              </div>
              <div className="flex flex-col gap-1.5">
                {item.options.map((opt, oi) => {
                  const picked = answers[i] === oi
                  const correct = submitted && item.correct === oi
                  const wrong = submitted && picked && item.correct !== oi
                  return (
                    <label
                      key={oi}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded-lg border border-border p-2.5 text-sm transition-colors",
                        picked && !submitted && "border-primary bg-primary/5",
                        correct && "border-career bg-career-soft",
                        wrong && "border-destructive bg-destructive/10",
                      )}
                    >
                      <input
                        type="radio"
                        name={`q-${i}`}
                        className="accent-primary"
                        checked={picked}
                        onChange={() => setAnswers((a) => ({ ...a, [i]: oi }))}
                        disabled={submitted}
                      />
                      {opt}
                    </label>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
        <DialogFooter className="sm:justify-between">
          <div className="text-sm text-muted-foreground">
            {submitted ? `Score: ${score} / ${sampleQuiz.length}` : `${Object.keys(answers).length} / ${sampleQuiz.length} answered`}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
            <Button onClick={() => setSubmitted(true)} disabled={submitted}>
              Submit
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ContentConfigDialog({
  open,
  onClose,
  onLaunch,
  loading,
}: {
  open: "quiz" | "flashcard" | null
  onClose: () => void
  onLaunch: (type: "quiz" | "flashcard", count: number, concept: string) => void
  loading: boolean
}) {
  const [count, setCount] = React.useState(open === "quiz" ? 10 : 15)
  const [mode, setMode] = React.useState<"auto" | "mix" | "specific">("auto")
  const [concept, setConcept] = React.useState("")

  React.useEffect(() => {
    if (open) {
      setCount(open === "quiz" ? 10 : 15)
      setMode("auto")
      setConcept("")
    }
  }, [open])

  const isQuiz = open === "quiz"
  const min = 5
  const max = isQuiz ? 30 : 50

  return (
    <Dialog open={!!open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isQuiz ? <Sparkles className="h-4 w-4 text-primary" /> : <Layers className="h-4 w-4 text-primary" />}
            {isQuiz ? "Quiz settings" : "Flashcard settings"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium">
              {isQuiz ? "Number of questions" : "Number of cards"}
            </label>
            <div className="flex items-center gap-3">
              <Input
                type="number"
                min={min}
                max={max}
                value={count}
                onChange={(e) => setCount(Math.max(min, Math.min(max, Number(e.target.value) || min)))}
                className="w-20"
              />
              <span className="text-xs text-muted-foreground">{min}–{max}</span>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium">Focus area</label>
            <div className="flex flex-col gap-1.5">
              {(
                [
                  ["auto", "Weakest areas", "Auto-picks concepts you struggle with most"],
                  ["mix", "Mix all concepts", "Pulls from all available concepts evenly"],
                  ["specific", "Specific concept", "Choose a single concept to focus on"],
                ] as const
              ).map(([value, label, desc]) => (
                <label
                  key={value}
                  className={cn(
                    "flex cursor-pointer items-start gap-2.5 rounded-lg border border-border p-2.5 text-sm transition-colors",
                    mode === value && "border-primary bg-primary/5",
                  )}
                >
                  <input
                    type="radio"
                    name="mode"
                    className="mt-0.5 accent-primary"
                    checked={mode === value}
                    onChange={() => setMode(value)}
                  />
                  <div>
                    <div className="font-medium">{label}</div>
                    <div className="text-xs text-muted-foreground">{desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {mode === "specific" && (
            <div>
              <label className="mb-1.5 block text-sm font-medium">Concept name</label>
              <Input
                placeholder="e.g. Introduction to AI"
                value={concept}
                onChange={(e) => setConcept(e.target.value)}
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              const conceptArg = mode === "specific" ? concept : ""
              onLaunch(open!, count, conceptArg)
            }}
            disabled={loading || (mode === "specific" && !concept.trim())}
          >
            {loading ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
            {isQuiz ? "Start quiz" : "Start flashcards"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function LiveQuizDialog({
  open,
  onClose,
  questions,
  courseCode,
  courseId,
  onMasteryUpdate,
}: {
  open: boolean
  onClose: () => void
  questions: QuizQuestion[]
  courseCode: string
  courseId: string
  onMasteryUpdate: (mastery: number) => void
}) {
  const [answers, setAnswers] = React.useState<Record<number, number>>({})
  const [submitted, setSubmitted] = React.useState(false)
  React.useEffect(() => {
    if (open) {
      setAnswers({})
      setSubmitted(false)
    }
  }, [open])

  const handleSubmit = async () => {
    setSubmitted(true)
    const payload = questions
      .map((q, i) => ({
        question_id: q.id,
        selected: String.fromCharCode(65 + (answers[i] ?? 0)),
      }))
      .filter((_, i) => answers[i] !== undefined)
    try {
      const result = await submitQuiz("demo", courseId, payload)
      toast.success(`Score: ${result.correct}/${result.total}`)
      const vals = Object.values(result.mastery_updates)
      if (vals.length > 0) onMasteryUpdate(vals.reduce((a, b) => a + b, 0) / vals.length)
    } catch {
      toast.error("Failed to submit quiz to server")
    }
  }

  const getCorrectIndex = (q: QuizQuestion): number => {
    if (!q.correct) return -1
    const letter = q.correct.trim().toUpperCase()
    return letter.charCodeAt(0) - 65
  }

  const score = submitted
    ? questions.filter((q, i) => answers[i] === getCorrectIndex(q)).length
    : 0

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            Quiz · {courseCode}
          </DialogTitle>
          <DialogDescription>
            {questions.length} questions across{" "}
            {[...new Set(questions.map((q) => q.core_concept))].length} concepts
          </DialogDescription>
        </DialogHeader>
        {questions.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            No quiz questions available. Run Moodle sync + Cognify first.
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {questions.map((item, i) => {
              const picked = answers[i]
              return (
                <div key={item.id}>
                  <div className="mb-1 flex items-center gap-2">
                    <Badge variant="secondary" className="text-[10px] font-normal">
                      {item.core_concept}
                    </Badge>
                    <Badge variant="outline" className="text-[10px] font-normal">
                      {item.difficulty}
                    </Badge>
                  </div>
                  <div className="mb-2 text-sm font-medium">
                    {i + 1}. {item.question}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {item.options.map((opt, oi) => {
                      const isPicked = picked === oi
                      const correctIdx = getCorrectIndex(item)
                      const isCorrectOption = submitted && oi === correctIdx
                      const isWrong = submitted && isPicked && oi !== correctIdx
                      return (
                        <label
                          key={oi}
                          className={cn(
                            "flex cursor-pointer items-center gap-2 rounded-lg border border-border p-2.5 text-sm transition-colors",
                            !submitted && isPicked && "border-primary bg-primary/5",
                            isCorrectOption && "border-career bg-career-soft",
                            isWrong && "border-destructive bg-destructive/10",
                          )}
                        >
                          <input
                            type="radio"
                            name={`lq-${i}`}
                            className="accent-primary"
                            checked={isPicked}
                            onChange={() => setAnswers((a) => ({ ...a, [i]: oi }))}
                            disabled={submitted}
                          />
                          {opt}
                          {isCorrectOption && submitted && (
                            <span className="ml-auto text-xs font-medium text-career">Correct</span>
                          )}
                          {isWrong && (
                            <span className="ml-auto text-xs font-medium text-destructive">Wrong</span>
                          )}
                        </label>
                      )
                    })}
                    {submitted && item.explanation && (
                      <div className="mt-1 rounded-lg bg-muted/50 p-2.5 text-xs text-muted-foreground">
                        {item.explanation}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
        <DialogFooter className="sm:justify-between">
          <div className="text-sm text-muted-foreground">
            {submitted
              ? `Score: ${score} / ${questions.length} correct`
              : `${Object.keys(answers).length} / ${questions.length} answered`}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
            {!submitted && questions.length > 0 && (
              <Button
                onClick={handleSubmit}
                disabled={Object.keys(answers).length === 0}
              >
                Submit
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FlashcardDialog({
  open,
  onClose,
  cards,
  courseCode,
  courseId,
  onMasteryUpdate,
}: {
  open: boolean
  onClose: () => void
  cards: FlashcardItem[]
  courseCode: string
  courseId: string
  onMasteryUpdate: (mastery: number) => void
}) {
  const [currentIndex, setCurrentIndex] = React.useState(0)
  const [flipped, setFlipped] = React.useState(false)
  const [ratings, setRatings] = React.useState<Record<string, string>>({})
  const [submitted, setSubmitted] = React.useState(false)

  React.useEffect(() => {
    if (open) {
      setCurrentIndex(0)
      setFlipped(false)
      setRatings({})
      setSubmitted(false)
    }
  }, [open])

  const card = cards[currentIndex]
  const done = currentIndex >= cards.length

  React.useEffect(() => {
    if (done && !submitted && Object.keys(ratings).length > 0) {
      setSubmitted(true)
      const payload = Object.entries(ratings).map(([card_id, rating]) => ({ card_id, rating }))
      submitFlashcards("demo", courseId, payload)
        .then((result) => {
          const vals = Object.values(result.mastery_updates)
          if (vals.length > 0) onMasteryUpdate(vals.reduce((a, b) => a + b, 0) / vals.length)
        })
        .catch(() => {})
    }
  }, [done])

  const handleRate = (rating: string) => {
    if (!card) return
    setRatings((prev) => ({ ...prev, [card.id]: rating }))
    setFlipped(false)
    setCurrentIndex((i) => i + 1)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-primary" />
            Flashcards · {courseCode}
          </DialogTitle>
          <DialogDescription>
            {cards.length} cards · {done ? "Done!" : `${currentIndex + 1} / ${cards.length}`}
          </DialogDescription>
        </DialogHeader>

        {cards.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            No flashcards available. Run Moodle sync + Cognify first.
          </div>
        ) : done ? (
          <div className="py-8 text-center">
            <div className="text-2xl font-semibold">Session complete!</div>
            <div className="mt-2 text-sm text-muted-foreground">
              {Object.values(ratings).filter((r) => r === "easy").length} easy ·{" "}
              {Object.values(ratings).filter((r) => r === "medium").length} medium ·{" "}
              {Object.values(ratings).filter((r) => r === "hard").length} hard
            </div>
          </div>
        ) : card ? (
          <>
            <div className="mb-1 flex items-center gap-2">
              <Badge variant="secondary" className="text-[10px] font-normal">
                {card.core_concept}
              </Badge>
              <Badge variant="outline" className="text-[10px] font-normal">
                {card.difficulty}
              </Badge>
            </div>

            <button
              onClick={() => setFlipped(!flipped)}
              className="min-h-[180px] w-full rounded-xl border border-border bg-muted/30 p-6 text-left transition-all hover:shadow-sm"
            >
              {!flipped ? (
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Question
                  </div>
                  <div className="text-base font-medium">{card.front}</div>
                  <div className="mt-4 text-xs text-primary">Click to reveal answer</div>
                </div>
              ) : (
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Answer
                  </div>
                  <div className="text-base">{card.back}</div>
                </div>
              )}
            </button>

            {flipped && (
              <div className="flex items-center justify-center gap-3">
                <div className="text-xs text-muted-foreground">How well did you know this?</div>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-destructive/50 text-destructive hover:bg-destructive/10"
                  onClick={() => handleRate("hard")}
                >
                  Hard
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleRate("medium")}
                >
                  Medium
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-career/50 text-career hover:bg-career-soft"
                  onClick={() => handleRate("easy")}
                >
                  Easy
                </Button>
              </div>
            )}
          </>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {done ? "Done" : "Close"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function _studySlots(dueDate: string): { label: string; starts_at: string; ends_at: string }[] {
  const due = new Date(dueDate + "T23:59:00")
  const slots: { label: string; starts_at: string; ends_at: string }[] = []
  const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
  const blockHours = [
    [9, 11],
    [14, 16],
    [16, 18],
  ]

  for (let dayOffset = -5; dayOffset <= -1; dayOffset++) {
    const day = new Date(due)
    day.setDate(due.getDate() + dayOffset)
    if (day <= new Date()) continue
    for (const [startH, endH] of blockHours) {
      const start = new Date(day)
      start.setHours(startH, 0, 0, 0)
      const end = new Date(day)
      end.setHours(endH, 0, 0, 0)
      const pad = (n: number) => String(n).padStart(2, "0")
      slots.push({
        label: `${dayNames[day.getDay()]} ${pad(startH)}:00 – ${pad(endH)}:00`,
        starts_at: start.toISOString(),
        ends_at: end.toISOString(),
      })
      if (slots.length >= 5) return slots
    }
  }
  return slots
}

function ScheduleStudyBlockDialog({
  deadline,
  onClose,
}: {
  deadline: Deadline
  onClose: () => void
}) {
  const slots = React.useMemo(() => _studySlots(deadline.due), [deadline.due])
  const [selected, setSelected] = React.useState(0)
  const [syncing, setSyncing] = React.useState(false)

  const handleConfirm = async () => {
    const slot = slots[selected]
    if (!slot) return
    setSyncing(true)
    try {
      await createCalendarEvent({
        title: `Study block: ${deadline.course} — ${deadline.task}`,
        starts_at: slot.starts_at,
        ends_at: slot.ends_at,
        location: "MI Library",
        agent: "academic",
      })
      toast.success("Study block synced to Google Calendar")
      onClose()
    } catch (err) {
      toast.error(
        `Failed to sync: ${err instanceof Error ? err.message : "Unknown error"}`,
      )
    } finally {
      setSyncing(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Schedule study block</DialogTitle>
          <DialogDescription>
            {deadline.course} — {deadline.task}
          </DialogDescription>
        </DialogHeader>
        {slots.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            No available slots before the due date.
          </p>
        ) : (
          <div className="space-y-2">
            {slots.map((slot, i) => (
              <label
                key={slot.starts_at}
                className={cn(
                  "flex cursor-pointer items-center justify-between rounded-lg border p-3 transition-colors hover:bg-muted/50",
                  selected === i ? "border-primary bg-primary/5" : "border-border",
                )}
              >
                <div className="flex items-center gap-3">
                  <input
                    type="radio"
                    name="slot"
                    checked={selected === i}
                    onChange={() => setSelected(i)}
                    className="accent-primary"
                  />
                  <div>
                    <div className="text-sm font-medium">{slot.label}</div>
                    <div className="text-xs text-muted-foreground">
                      MI Library
                    </div>
                  </div>
                </div>
                <AgentBadge agent="academic" />
              </label>
            ))}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleConfirm} disabled={syncing || slots.length === 0}>
            {syncing ? (
              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
            ) : (
              <CalendarIcon className="mr-2 h-3.5 w-3.5" />
            )}
            Sync to Calendar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DeadlinesTab() {
  const [sortBy, setSortBy] = React.useState<"priority" | "due" | "weight">("priority")
  const [scheduleOpen, setScheduleOpen] = React.useState<Deadline | null>(null)
  const [deadlines, setDeadlines] = React.useState<Deadline[]>([])
  const [loading, setLoading] = React.useState(true)
  const [syncingAll, setSyncingAll] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    setLoading(true)
    listDeadlines()
      .then((data) => { if (!cancelled) setDeadlines(data) })
      .catch(() => { if (!cancelled) toast.error("Failed to load deadlines") })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const handleSyncAll = async () => {
    setSyncingAll(true)
    let synced = 0
    try {
      for (const d of deadlines) {
        await createCalendarEvent({
          title: `📅 Deadline: ${d.course} — ${d.task}`,
          starts_at: `${d.due}T08:00:00`,
          ends_at: `${d.due}T08:30:00`,
          location: "",
          agent: "academic",
        })
        synced++
      }
      toast.success(`${synced} deadline${synced !== 1 ? "s" : ""} synced to Google Calendar`)
    } catch (err) {
      toast.error(
        `Synced ${synced}/${deadlines.length} — ${err instanceof Error ? err.message : "error"}`,
      )
    } finally {
      setSyncingAll(false)
    }
  }

  const sorted = [...deadlines].sort((a, b) => {
    if (sortBy === "priority") return b.priority - a.priority
    if (sortBy === "due") return new Date(a.due).getTime() - new Date(b.due).getTime()
    return parseInt(b.weight) - parseInt(a.weight)
  })

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base">Unified deadlines</CardTitle>
            <CardDescription>Moodle + TUMonline, sorted by {sortBy}</CardDescription>
          </div>
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              className="h-8 gap-1.5"
              onClick={handleSyncAll}
              disabled={syncingAll || deadlines.length === 0}
            >
              {syncingAll ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <CalendarIcon className="h-3 w-3" />
              )}
              Sync to Calendar
            </Button>
            {(["priority", "due", "weight"] as const).map((k) => (
              <Button
                key={k}
                size="sm"
                variant={sortBy === k ? "default" : "outline"}
                onClick={() => setSortBy(k)}
                className="h-8 capitalize"
              >
                <ArrowUpDown className="mr-1 h-3 w-3" />
                {k}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="px-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Course</TableHead>
                <TableHead>Task</TableHead>
                <TableHead>Due</TableHead>
                <TableHead>Weight</TableHead>
                <TableHead>Mastery gap</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="font-mono text-xs text-primary">{d.course}</TableCell>
                  <TableCell className="font-medium">{d.task}</TableCell>
                  <TableCell className="text-muted-foreground">{d.due}</TableCell>
                  <TableCell>{d.weight}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Progress value={d.masteryGap} className="h-1.5 w-20" />
                      <span className="text-xs tabular-nums text-muted-foreground">{d.masteryGap}%</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span
                      className={cn(
                        "inline-flex h-6 min-w-8 items-center justify-center rounded-md px-2 text-xs font-semibold",
                        d.priority >= 85
                          ? "bg-destructive/10 text-destructive"
                          : d.priority >= 70
                            ? "bg-academic-soft text-academic"
                            : "bg-muted text-muted-foreground",
                      )}
                    >
                      {d.priority}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setScheduleOpen(d)}>
                      <CalendarIcon className="h-3.5 w-3.5" />
                      Schedule study block
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          )}
        </CardContent>
      </Card>

      {scheduleOpen && (
        <ScheduleStudyBlockDialog
          deadline={scheduleOpen}
          onClose={() => setScheduleOpen(null)}
        />
      )}
    </>
  )
}

function ThesisTab() {
  const [theses, setTheses] = React.useState<ThesisOpportunity[]>([])
  const [loading, setLoading] = React.useState(true)
  const [emailOpen, setEmailOpen] = React.useState<ThesisOpportunity | null>(null)

  React.useEffect(() => {
    let cancelled = false
    setLoading(true)
    listTheses()
      .then((data) => {
        if (!cancelled) setTheses(data)
      })
      .catch(() => {
        if (!cancelled) toast.error("Failed to load thesis opportunities")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Matching thesis topics to your profile…</span>
      </div>
    )
  }

  if (theses.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        No thesis opportunities found. Try again later.
      </div>
    )
  }

  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        {theses.map((t) => (
          <Card key={t.id}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-medium text-muted-foreground">{t.chair}</div>
                  <CardTitle className="mt-0.5 text-base leading-snug">{t.topic}</CardTitle>
                  <div className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">
                    <UsersIcon className="h-3 w-3" />
                    {t.professor}
                  </div>
                </div>
                <MatchScore value={t.match_score} />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{t.reasoning}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {t.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="font-normal">
                    {tag}
                  </Badge>
                ))}
              </div>
              <div className="mt-4 flex items-center justify-between">
                {t.source_url ? (
                  <a
                    href={t.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ExternalLink className="h-3 w-3" />
                    View listing
                  </a>
                ) : <span />}
                <Button size="sm" className="gap-1.5" onClick={() => setEmailOpen(t)}>
                  <Mail className="h-3.5 w-3.5" />
                  Draft outreach email
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <EmailComposer thesis={emailOpen} onClose={() => setEmailOpen(null)} />
    </>
  )
}

function MatchScore({ value }: { value: number }) {
  const tone =
    value >= 90 ? "text-career bg-career-soft" : value >= 80 ? "text-academic bg-academic-soft" : "text-muted-foreground bg-muted"
  return (
    <div className={cn("flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-lg text-center", tone)}>
      <div className="text-sm font-semibold leading-none">{value}</div>
      <div className="mt-0.5 text-[9px] uppercase tracking-wide opacity-80">match</div>
    </div>
  )
}

function EmailComposer({ thesis, onClose }: { thesis: ThesisOpportunity | null; onClose: () => void }) {
  const [body, setBody] = React.useState("")

  React.useEffect(() => {
    if (thesis) {
      setBody(
        `Dear ${thesis.professor},

I am Alex Müller, a 4th-semester Informatics student at TUM. I came across your current thesis topic "${thesis.topic}" at the ${thesis.chair} and would love to discuss a potential Bachelor's thesis under your supervision.

My coursework in Machine Learning (IN2064, 1.3) and Distributed Systems (IN2086) aligns well with this direction, and I have a small Rust side project exploring related ideas (github.com/amueller/raft-visualizer).

Would you have 20 minutes for a short meeting in the coming weeks? I'm flexible around these slots:

  • Tue, Apr 22, 14:00 – 14:30
  • Thu, Apr 24, 10:00 – 10:30
  • Mon, Apr 28, 15:00 – 15:30

Thank you for your time.

Best regards,
Alex Müller
alex.mueller@tum.de`,
      )
    }
  }, [thesis])

  return (
    <Dialog open={!!thesis} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-primary" />
            Outreach draft — review before sending
          </DialogTitle>
          <DialogDescription>
            Human review required. Nothing is sent until you click Send.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid grid-cols-[70px_1fr] items-center gap-2 text-sm">
            <span className="text-muted-foreground">To</span>
            <Input readOnly value={thesis ? `${thesis.professor.toLowerCase().replace(/prof\. dr\. /, "").replace(/\s/g, ".")}@tum.de` : ""} />
          </div>
          <div className="grid grid-cols-[70px_1fr] items-center gap-2 text-sm">
            <span className="text-muted-foreground">Subject</span>
            <Input defaultValue={`Thesis interest — ${thesis?.topic ?? ""}`} />
          </div>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={14}
            className="w-full rounded-lg border border-input bg-background p-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Edit later
          </Button>
          <Button
            onClick={() => {
              toast.success("Email sent to " + thesis?.professor)
              onClose()
            }}
          >
            Send
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function StudyRoomTab() {
  const [branches, setBranches] = React.useState<LibraryBranch[]>([])
  const [selectedBranch, setSelectedBranch] = React.useState("mathematics-informatics")
  const [data, setData] = React.useState<RoomSearchResult | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [booking, setBooking] = React.useState<string | null>(null)
  const [selectedStart, setSelectedStart] = React.useState<string | null>(null)
  const [selectedEnd, setSelectedEnd] = React.useState<string | null>(null)
  const [selectedRoom, setSelectedRoom] = React.useState<string | null>(null)
  const [selectedDate, setSelectedDate] = React.useState<string | null>(null)

  React.useEffect(() => {
    listLibraryBranches()
      .then(setBranches)
      .catch(() => {})
  }, [])

  const loadRooms = React.useCallback((branch: string, date?: string) => {
    setLoading(true)
    setData(null)
    searchLibraryRooms({ branch, target_date: date ?? undefined })
      .then((result) => {
        setData(result)
        const defStart = result.startTimes.find((t) => t.selected)
        const defEnd = result.endTimes.find((t) => t.selected)
        const defRoom = result.rooms.find((r) => r.selected)
        setSelectedStart(defStart?.time ?? result.startTimes[0]?.time ?? null)
        setSelectedEnd(defEnd?.time ?? result.endTimes[0]?.time ?? null)
        setSelectedRoom(defRoom?.name ?? result.rooms[0]?.name ?? null)
        setSelectedDate(result.selectedDate)
      })
      .catch(() => toast.error("Failed to load room availability"))
      .finally(() => setLoading(false))
  }, [])

  React.useEffect(() => {
    loadRooms(selectedBranch)
  }, [selectedBranch, loadRooms])

  const handleBook = async () => {
    if (!data || !selectedRoom || !selectedStart || !selectedEnd || !selectedDate) return
    setBooking(selectedRoom)
    try {
      const result = await bookLibraryRoom({
        branch: data.branch_slug,
        room_name: selectedRoom,
        date_day: selectedDate,
        start_time: selectedStart,
        end_time: selectedEnd,
      })
      if (result.status === "error") {
        toast.error(result.message)
      } else {
        toast.success(result.message || `${selectedRoom} booked ${selectedStart} – ${selectedEnd}`)
      }
    } catch {
      toast.error("Booking failed — check TUM credentials")
    } finally {
      setBooking(null)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Library Branch</label>
              <select
                value={selectedBranch}
                onChange={(e) => setSelectedBranch(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {branches.map((b) => (
                  <option key={b.slug} value={b.slug}>{b.name}</option>
                ))}
                {branches.length === 0 && <option value={selectedBranch}>Loading…</option>}
              </select>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              disabled={loading}
              onClick={() => loadRooms(selectedBranch)}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              Refresh
            </Button>
          </div>
          {data && (
            <div className="mt-2 text-xs text-muted-foreground">
              <MapPin className="mr-1 inline h-3 w-3" />
              {data.branch_address}
              {data.description && <> — {data.description}</>}
            </div>
          )}
        </CardContent>
      </Card>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">Scraping live availability from anny.eu…</span>
        </div>
      )}

      {!loading && data && (
        <>
          {/* Date picker */}
          <Card>
            <CardContent className="pt-6">
              <label className="mb-2 block text-xs font-medium text-muted-foreground">
                <CalendarIcon className="mr-1 inline h-3 w-3" />
                Date {data.monthText && `— ${data.monthText}`}
              </label>
              <div className="flex flex-wrap gap-2">
                {data.dates.filter((d) => !d.disabled).map((d) => (
                  <Button
                    key={d.day}
                    size="sm"
                    variant={d.day === selectedDate ? "default" : "outline"}
                    className="h-9 w-12"
                    onClick={() => {
                      setSelectedDate(d.day)
                      loadRooms(selectedBranch, d.day)
                    }}
                  >
                    {d.day}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Time selection */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardContent className="pt-6">
                <label className="mb-2 block text-xs font-medium text-muted-foreground">
                  <Clock className="mr-1 inline h-3 w-3" />
                  Start Time
                </label>
                <div className="flex max-h-48 flex-wrap gap-1.5 overflow-y-auto">
                  {data.startTimes.map((t) => (
                    <Button
                      key={t.time}
                      size="sm"
                      variant={t.time === selectedStart ? "default" : "outline"}
                      className="h-8 px-2.5 text-xs"
                      onClick={() => setSelectedStart(t.time)}
                    >
                      {t.time}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <label className="mb-2 block text-xs font-medium text-muted-foreground">
                  <Clock className="mr-1 inline h-3 w-3" />
                  End Time
                </label>
                <div className="flex max-h-48 flex-wrap gap-1.5 overflow-y-auto">
                  {data.endTimes.map((t) => (
                    <Button
                      key={t.time}
                      size="sm"
                      variant={t.time === selectedEnd ? "default" : "outline"}
                      className="h-8 px-2.5 text-xs"
                      onClick={() => setSelectedEnd(t.time)}
                    >
                      {t.time}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Features */}
          {data.features.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {data.features.map((f) => (
                <Badge key={f} variant="secondary" className="font-normal">{f}</Badge>
              ))}
            </div>
          )}

          {/* Room cards */}
          <div className="grid gap-3">
            {data.rooms.length === 0 && (
              <div className="py-8 text-center text-sm text-muted-foreground">
                No rooms available for this date/time. Try a different day.
              </div>
            )}
            {data.rooms.map((r) => (
              <Card
                key={r.name}
                className={cn(
                  "cursor-pointer transition-colors",
                  r.name === selectedRoom && "ring-2 ring-primary",
                )}
                onClick={() => setSelectedRoom(r.name)}
              >
                <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-academic-soft text-academic">
                      <BookOpen className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="font-medium">{r.name}</div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <MapPin className="h-3 w-3" />
                          {data.branch_name}
                        </span>
                        <span>
                          <UsersIcon className="mr-0.5 inline h-3 w-3" />
                          {r.capacity_text || `Capacity ${r.capacity}`}
                        </span>
                      </div>
                    </div>
                  </div>
                  <Button
                    className="gap-1.5 sm:self-center"
                    disabled={booking !== null || r.name !== selectedRoom}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleBook()
                    }}
                  >
                    {booking === r.name ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <>Book <ArrowRight className="h-3.5 w-3.5" /></>
                    )}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* anny.eu link */}
          {data.url && (
            <div className="text-center">
              <a
                href={data.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <ExternalLink className="h-3 w-3" />
                Open on anny.eu
              </a>
            </div>
          )}
        </>
      )}
    </div>
  )
}

