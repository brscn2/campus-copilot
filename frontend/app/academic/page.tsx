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
import { deadlines, theses, studyRooms } from "@/lib/mock-data"
import { runFullPipeline, listSyncedCourses, type SyncedCourse } from "@/lib/api"
import { AgentBadge } from "@/components/agent-badge"
import {
  ArrowRight,
  ArrowUpDown,
  BookOpen,
  Calendar as CalendarIcon,
  Loader2,
  Mail,
  MapPin,
  RefreshCw,
  Search,
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
  const [syncing, setSyncing] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [syncedCourses, setSyncedCourses] = React.useState<SyncedCourse[]>([])

  React.useEffect(() => {
    listSyncedCourses()
      .then((res) => setSyncedCourses(res.courses))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = await runFullPipeline()
      const ingested = result.ingestions?.filter((i) => i.status === "ingesting").length ?? 0
      toast.success(`Pipeline complete: ${ingested} courses ingested to S3 + Cognee`)
      const synced = await listSyncedCourses()
      setSyncedCourses(synced.courses)
    } catch (err) {
      toast.error(`Pipeline failed: ${err instanceof Error ? err.message : "Unknown error"}`)
    } finally {
      setSyncing(false)
    }
  }

  const groups = React.useMemo(() => groupCoursesBySemester(syncedCourses), [syncedCourses])

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">
          {syncedCourses.length > 0
            ? `${syncedCourses.length} course${syncedCourses.length === 1 ? "" : "s"} synced from Moodle`
            : loading
              ? "Loading your Moodle courses…"
              : "No Moodle courses synced yet."}
        </div>
        <Button onClick={handleSync} disabled={syncing} className="gap-2">
          {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {syncing ? "Syncing from Moodle…" : "Sync from Moodle"}
        </Button>
      </div>

      {!loading && syncedCourses.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
            <div className="text-sm font-medium">No courses yet</div>
            <div className="max-w-sm text-xs text-muted-foreground">
              Click <span className="font-medium">Sync from Moodle</span> to pull your enrolled
              courses, slides, and uploads into Campus Co-Pilot.
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-6">
        {groups.map((group) => (
          <section key={group.semester}>
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="text-sm font-medium">{group.semester}</h2>
              <span className="text-xs text-muted-foreground">
                {group.items.length} course{group.items.length === 1 ? "" : "s"}
              </span>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {group.items.map((sc) => (
                <Card
                  key={sc.dataset_name}
                  className="h-full transition-all hover:-translate-y-0.5 hover:shadow-sm"
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-2">
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
                    {(() => {
                      let hash = 0
                      for (let i = 0; i < sc.dataset_name.length; i++) {
                        hash = ((hash << 5) - hash + sc.dataset_name.charCodeAt(i)) | 0
                      }
                      const mastery = 30 + (Math.abs(hash) % 55)
                      return (
                        <>
                          <div className="mt-3 flex items-center justify-between text-xs">
                            <span className="text-muted-foreground">Mastery</span>
                            <span className="font-medium tabular-nums">{mastery}%</span>
                          </div>
                          <Progress value={mastery} className="mt-1.5 h-1.5" />
                        </>
                      )
                    })()}
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  )
}

function DeadlinesTab() {
  const [sortBy, setSortBy] = React.useState<"priority" | "due" | "weight">("priority")
  const [scheduleOpen, setScheduleOpen] = React.useState<(typeof deadlines)[number] | null>(null)

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
        </CardContent>
      </Card>

      <Dialog open={!!scheduleOpen} onOpenChange={(o) => !o && setScheduleOpen(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Schedule study block</DialogTitle>
            <DialogDescription>
              {scheduleOpen?.course} — {scheduleOpen?.task}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {["Tue 14:00 – 16:00", "Wed 09:00 – 11:00", "Thu 16:00 – 18:00"].map((slot, i) => (
              <label
                key={slot}
                className="flex cursor-pointer items-center justify-between rounded-lg border border-border p-3 transition-colors hover:bg-muted/50"
              >
                <div className="flex items-center gap-3">
                  <input
                    type="radio"
                    name="slot"
                    defaultChecked={i === 0}
                    className="accent-primary"
                  />
                  <div>
                    <div className="text-sm font-medium">{slot}</div>
                    <div className="text-xs text-muted-foreground">MI Library · no conflicts</div>
                  </div>
                </div>
                <AgentBadge agent="academic" />
              </label>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setScheduleOpen(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                toast.success("Study block added to calendar")
                setScheduleOpen(null)
              }}
            >
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function ThesisTab() {
  const [emailOpen, setEmailOpen] = React.useState<(typeof theses)[number] | null>(null)

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
                <MatchScore value={t.matchScore} />
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
              <div className="mt-4 flex justify-end">
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

function EmailComposer({ thesis, onClose }: { thesis: (typeof theses)[number] | null; onClose: () => void }) {
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
  const [query, setQuery] = React.useState("quiet room near Mathematik, 2–5pm")

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="pt-6">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-9"
              placeholder="Describe what you need…"
            />
          </div>
          <div className="mt-2 text-xs text-muted-foreground">
            Try: &ldquo;quiet room near MI with whiteboard&rdquo;, &ldquo;group room for 6 tomorrow morning&rdquo;
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3">
        {studyRooms.map((r) => (
          <Card key={r.id}>
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
                      {r.building}
                    </span>
                    <span>Capacity {r.capacity}</span>
                    <span>Available until {r.availableUntil}</span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {r.amenities.map((a) => (
                      <Badge key={a} variant="secondary" className="font-normal">
                        {a}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
              <Button
                className="gap-1.5 sm:self-center"
                onClick={() => toast.success(`${r.name} booked for 14:00 – 17:00`)}
              >
                Book <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

