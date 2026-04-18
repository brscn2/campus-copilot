"use client"

import * as React from "react"
import { PageHeader } from "@/components/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { AgentBadge } from "@/components/agent-badge"
import { jobs, profile as mockProfile, user } from "@/lib/mock-data"
import {
  getStudentProfile,
  listCareerEvents,
  uploadCvForAudit,
  type CareerEvent,
  type CvAuditResult,
  type CvFlag,
  type CvSuggestion,
  type StudentProfile,
} from "@/lib/api"
import {
  Building2,
  Calendar,
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  Loader2,
  MapPin,
  Pencil,
  Sparkles,
  Upload,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

export default function CareerPage() {
  return (
    <div>
      <PageHeader
        title="Career"
        description="Profile, CV audit, jobs, and workshops — coordinated by your Career Agent."
        actions={<AgentBadge agent="career" className="px-2.5 py-1" />}
      />

      <Tabs defaultValue="profile" className="w-full">
        <TabsList className="mb-5 w-full max-w-xl">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="cv">CV Audit</TabsTrigger>
          <TabsTrigger value="jobs">Job Scout</TabsTrigger>
          <TabsTrigger value="events">Events</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <ProfileTab />
        </TabsContent>
        <TabsContent value="cv">
          <CvAuditTab />
        </TabsContent>
        <TabsContent value="jobs">
          <JobScoutTab />
        </TabsContent>
        <TabsContent value="events">
          <EventsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

const SKILLS_COLLAPSED = 6
const NOISE_TITLES = ["fachschaftsvollversammlung", "vollversammlung", "studentische vertretung"]

function isRealLecture(lec: { title: string; code: string; type: string }): boolean {
  const lower = lec.title.toLowerCase()
  return !NOISE_TITLES.some((n) => lower.includes(n)) && lec.code !== "" && lec.code !== "IN"
}

function ProfileTab() {
  const [profile, setProfile] = React.useState<StudentProfile | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [showAllSkills, setShowAllSkills] = React.useState(false)

  React.useEffect(() => {
    getStudentProfile()
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setLoading(false))
  }, [])

  const displayProfile = profile ?? {
    name: user.name,
    headline: mockProfile.headline,
    summary: mockProfile.summary,
    skills: mockProfile.skills,
    gpa: null,
    grades: [],
    current_lectures: [],
  }

  const filteredLectures = (profile?.current_lectures ?? []).filter(isRealLecture)
  const visibleSkills = showAllSkills
    ? displayProfile.skills
    : displayProfile.skills.slice(0, SKILLS_COLLAPSED)
  const hasMoreSkills = displayProfile.skills.length > SKILLS_COLLAPSED

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader className="flex flex-row items-start justify-between">
          <div>
            <div className="flex items-center gap-2.5">
              <CardTitle className="text-base">{displayProfile.name}</CardTitle>
              {profile?.gpa != null && (
                <Badge variant="secondary" className="font-mono text-xs">
                  GPA {profile.gpa}
                </Badge>
              )}
            </div>
            <CardDescription>{profile?.headline ?? mockProfile.headline}</CardDescription>
          </div>
          <Button variant="outline" size="sm" className="gap-1.5">
            <Pencil className="h-3.5 w-3.5" />
            Edit
          </Button>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">
            {profile?.summary ?? mockProfile.summary}
          </div>

          {filteredLectures.length > 0 && (
            <div className="mt-4">
              <div className="mb-2 text-sm font-medium">Current Semester</div>
              <div className="flex flex-wrap gap-1.5">
                {filteredLectures.map((lec, i) => (
                  <Badge key={`${lec.code}-${i}`} variant="secondary" className="font-normal">
                    {lec.code} — {lec.title}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          <div className="mt-5">
            <div className="mb-2 text-sm font-medium">
              Skills (inferred from coursework)
              {loading && <span className="ml-2 text-xs text-muted-foreground">Loading...</span>}
            </div>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {visibleSkills.map((s) => (
                <div key={s.name} className="rounded-lg border border-border p-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{s.name}</span>
                    <span className="text-xs tabular-nums text-muted-foreground">{s.level}%</span>
                  </div>
                  <Progress value={s.level} className="mt-1.5 h-1.5" />
                  <div className="mt-1.5 text-xs text-muted-foreground">{s.source}</div>
                </div>
              ))}
            </div>
            {hasMoreSkills && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-2 w-full gap-1.5 text-xs text-muted-foreground"
                onClick={() => setShowAllSkills((p) => !p)}
              >
                {showAllSkills ? (
                  <>
                    <ChevronUp className="h-3.5 w-3.5" />
                    Show fewer skills
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3.5 w-3.5" />
                    Show {displayProfile.skills.length - SKILLS_COLLAPSED} more skills
                  </>
                )}
              </Button>
            )}
          </div>

          {profile && profile.grades.length > 0 && (
            <div className="mt-5">
              <div className="mb-2 text-sm font-medium">Exam Results</div>
              <div className="rounded-lg border border-border">
                <div className="flex flex-col">
                  {profile.grades.map((g, i) => (
                    <div
                      key={`${g.course_code}-${g.semester}-${i}`}
                      className="flex items-center justify-between border-b border-border p-2.5 last:border-b-0"
                    >
                      <div className="flex items-center gap-2 text-sm">
                        <span className="font-mono text-xs text-primary">{g.course_code}</span>
                        <span className="truncate">{g.title}</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{g.credits} ECTS</span>
                        <span
                          className={cn(
                            "font-mono font-medium",
                            parseFloat(g.grade.replace(",", ".")) <= 2.0
                              ? "text-career"
                              : parseFloat(g.grade.replace(",", ".")) >= 5.0
                                ? "text-destructive"
                                : "text-foreground"
                          )}
                        >
                          {g.grade}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Projects</CardTitle>
          <CardDescription>Pulled from your GitHub</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-3">
            {mockProfile.projects.map((p) => (
              <li key={p.name} className="rounded-lg border border-border p-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm font-medium">{p.name}</span>
                  <Badge variant="secondary" className="font-normal">★ {p.stars}</Badge>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{p.desc}</div>
              </li>
            ))}
          </ul>
          <Button variant="outline" size="sm" className="mt-4 w-full">
            Sync GitHub
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

function CvAuditTab() {
  const [auditResult, setAuditResult] = React.useState<CvAuditResult | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [accepted, setAccepted] = React.useState<Record<number, boolean>>({})
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  const handleFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please upload a PDF file.")
      return
    }
    setLoading(true)
    setError(null)
    setAuditResult(null)
    setAccepted({})
    try {
      const result = await uploadCvForAudit(file)
      setAuditResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setLoading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="lg:col-span-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Upload CV</CardTitle>
            <CardDescription>PDF only. Audited against your real TUMonline transcript.</CardDescription>
          </CardHeader>
          <CardContent>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleFile(file)
              }}
            />

            {!auditResult && !loading ? (
              <button
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                className="flex w-full flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-muted/30 px-6 py-10 text-center transition-colors hover:bg-muted/60"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Upload className="h-5 w-5" />
                </div>
                <div className="mt-3 text-sm font-medium">Drop your CV here</div>
                <div className="mt-1 text-xs text-muted-foreground">or click to browse</div>
              </button>
            ) : loading ? (
              <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-muted/30 px-6 py-10 text-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <div className="mt-3 text-sm font-medium">Analyzing your CV...</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Cross-referencing with TUMonline transcript
                </div>
              </div>
            ) : auditResult ? (
              <div className="rounded-lg border border-border p-4">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-primary" />
                  <div className="flex-1">
                    <div className="text-sm font-medium">{auditResult.filename}</div>
                    <div className="text-xs text-muted-foreground">
                      Audited · {auditResult.flags.length} findings · {auditResult.suggestions.length} suggestions
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setAuditResult(null)
                      setAccepted({})
                    }}
                  >
                    Re-upload
                  </Button>
                </div>
              </div>
            ) : null}

            {error && (
              <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {auditResult && auditResult.flags.length > 0 && (
              <div className="mt-4 space-y-2">
                {auditResult.flags.map((f, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex items-start gap-3 rounded-lg border p-3",
                      f.level === "critical" && "border-destructive/30 bg-destructive/5",
                      f.level === "warning" && "border-social/30 bg-social-soft/50",
                      f.level === "good" && "border-career/30 bg-career-soft/50",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 h-2 w-2 shrink-0 rounded-full",
                        f.level === "critical" && "bg-destructive",
                        f.level === "warning" && "bg-social",
                        f.level === "good" && "bg-career",
                      )}
                    />
                    <div className="text-sm">{f.text}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Original vs Suggested</CardTitle>
          <CardDescription>
            {auditResult
              ? "Accept or reject each change individually."
              : "Upload a CV to see AI-powered suggestions."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {auditResult && auditResult.suggestions.length > 0 ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <CvPanel label="Original">
                  {auditResult.suggestions.map((s, i) => (
                    <div key={i} className={i > 0 ? "mt-3" : ""}>
                      <div className="text-xs text-muted-foreground">{s.label}</div>
                      <div className="text-sm line-through text-muted-foreground">{s.original}</div>
                    </div>
                  ))}
                </CvPanel>
                <CvPanel label="Suggested">
                  {auditResult.suggestions.map((s, i) => (
                    <div key={i} className={i > 0 ? "mt-3" : ""}>
                      <div className="text-xs text-muted-foreground">{s.label}</div>
                      <div className="text-sm font-medium">{s.suggested}</div>
                    </div>
                  ))}
                </CvPanel>
              </div>

              <div className="mt-4 space-y-2">
                {auditResult.suggestions.map((s, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-border p-3">
                    <div className="text-sm">{s.label}</div>
                    <div className="flex gap-1.5">
                      <Button
                        size="sm"
                        variant={accepted[i] === false ? "default" : "outline"}
                        className={cn("gap-1", accepted[i] === false && "bg-destructive hover:bg-destructive/90")}
                        onClick={() => setAccepted((p) => ({ ...p, [i]: false }))}
                      >
                        <X className="h-3.5 w-3.5" />
                        Reject
                      </Button>
                      <Button
                        size="sm"
                        variant={accepted[i] === true ? "default" : "outline"}
                        className="gap-1"
                        onClick={() => setAccepted((p) => ({ ...p, [i]: true }))}
                      >
                        <Check className="h-3.5 w-3.5" />
                        Accept
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : !auditResult ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
              <FileText className="h-10 w-10 opacity-30" />
              <div className="mt-3 text-sm">Upload your CV to get started</div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}

function CvPanel({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      {children}
    </div>
  )
}

function JobScoutTab() {
  const [type, setType] = React.useState<"working-student" | "internship" | "new-grad">("working-student")
  const [detail, setDetail] = React.useState<(typeof jobs)[number] | null>(null)
  const [optimizeOpen, setOptimizeOpen] = React.useState(false)
  const filtered = jobs.filter((j) => j.type === type)

  return (
    <>
      <Tabs value={type} onValueChange={(v) => setType(v as typeof type)} className="mb-4">
        <TabsList>
          <TabsTrigger value="working-student">Working Student</TabsTrigger>
          <TabsTrigger value="internship">Internship</TabsTrigger>
          <TabsTrigger value="new-grad">New Grad</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="grid gap-3 md:grid-cols-2">
        {filtered.map((j) => (
          <Card key={j.id} className="transition-all hover:-translate-y-0.5 hover:shadow-sm">
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <Building2 className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-muted-foreground">{j.company}</div>
                  <div className="font-medium leading-snug">{j.title}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3 w-3" />
                      {j.location}
                    </span>
                    <span>·</span>
                    <span>{j.salary}</span>
                    <span>·</span>
                    <span>{j.posted}</span>
                  </div>
                </div>
                <div className="flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-lg bg-career-soft text-center text-career">
                  <div className="text-xs font-semibold leading-none">{j.matchScore}</div>
                  <div className="mt-0.5 text-[9px] uppercase tracking-wide">match</div>
                </div>
              </div>
              <p className="mt-3 text-sm text-muted-foreground">{j.reasoning}</p>
              <div className="mt-3 flex justify-end">
                <Button size="sm" variant="outline" onClick={() => setDetail(j)}>
                  View details
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-2xl">
          {detail ? (
            <>
              <DialogHeader>
                <div className="text-xs text-muted-foreground">{detail.company}</div>
                <DialogTitle>{detail.title}</DialogTitle>
                <DialogDescription>
                  {detail.location} · {detail.salary} · posted {detail.posted}
                </DialogDescription>
              </DialogHeader>
              <div className="rounded-lg bg-career-soft/50 p-3 text-sm text-career">
                <span className="font-medium">Match: {detail.matchScore}% — </span>
                {detail.reasoning}
              </div>
              <div className="text-sm text-muted-foreground">
                We&apos;re looking for a working student to help scale our ML infrastructure. You&apos;ll work on
                distributed training pipelines, feature stores, and model serving. Must be comfortable with Python and
                cloud-native tooling.
              </div>
              <DialogFooter className="sm:justify-between">
                <Button variant="outline">Save</Button>
                <Button
                  onClick={() => setOptimizeOpen(true)}
                  className="gap-1.5"
                >
                  <Sparkles className="h-4 w-4" />
                  Optimize my CV for this role
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={optimizeOpen} onOpenChange={setOptimizeOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              Tailored CV — diff preview
            </DialogTitle>
            <DialogDescription>
              Reordered experience, surfaced relevant courses, and keyword alignment for {detail?.company}.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-border p-4">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Original
              </div>
              <div className="space-y-2 text-xs">
                <div className="line-through text-muted-foreground">Java, Python, HTML</div>
                <div className="line-through text-muted-foreground">Tetris Clone (2022)</div>
                <div className="text-muted-foreground">Coursework: IN0007, MA0901</div>
              </div>
            </div>
            <div className="rounded-lg border border-career/40 bg-career-soft/30 p-4">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-career">Tailored</div>
              <div className="space-y-2 text-xs">
                <div>
                  <span className="rounded bg-career-soft px-1 text-career">Python, PyTorch, Kubernetes, TypeScript</span>
                </div>
                <div>raft-visualizer — distributed consensus demo (58★)</div>
                <div>
                  Coursework: IN2064 <span className="text-career">ML (1.3)</span>, IN2086{" "}
                  <span className="text-career">Distributed Systems</span>, IN0007, MA0901
                </div>
              </div>
            </div>
          </div>
          <DialogFooter className="sm:justify-between">
            <Button variant="outline" onClick={() => setOptimizeOpen(false)}>
              Close
            </Button>
            <Button
              className="gap-1.5"
              onClick={() => {
                toast.success("Tailored CV downloaded")
                setOptimizeOpen(false)
              }}
            >
              <Download className="h-4 w-4" />
              Download PDF
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function EventsTab() {
  const [events, setEvents] = React.useState<CareerEvent[]>([])
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    listCareerEvents()
      .then(setEvents)
      .catch(() => setEvents([]))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin" />
        <div className="mt-3 text-sm">Finding Munich events and scoring relevance...</div>
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <Calendar className="h-10 w-10 opacity-30" />
        <div className="mt-3 text-sm">No upcoming events found</div>
      </div>
    )
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      {events.map((e, i) => (
        <Card key={`${e.url}-${i}`} className="overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-sm">
          {e.image && (
            <div className="relative w-full overflow-hidden bg-muted">
              <img
                src={e.image.replace(/width=\d+,height=\d+/, "width=400,height=400")}
                alt={e.title}
                className="w-full"
              />
              <div
                className={cn(
                  "absolute right-2 top-2 flex h-10 w-10 flex-col items-center justify-center rounded-lg text-center shadow-sm",
                  e.fit_score >= 70 && "bg-career-soft text-career",
                  e.fit_score >= 40 && e.fit_score < 70 && "bg-social-soft text-social",
                  e.fit_score < 40 && "bg-destructive/10 text-destructive",
                )}
              >
                <div className="text-xs font-semibold leading-none">{e.fit_score}</div>
                <div className="mt-0.5 text-[9px] uppercase tracking-wide">fit</div>
              </div>
            </div>
          )}
          <CardContent className={e.image ? "pt-3" : "pt-6"}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="secondary" className="font-normal">Luma</Badge>
                  {e.status && (
                    <Badge
                      variant={e.status === "Sold Out" ? "destructive" : "outline"}
                      className="font-normal text-[10px]"
                    >
                      {e.status}
                    </Badge>
                  )}
                </div>
                <div className="mt-1.5 text-base font-medium leading-snug">{e.title}</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    {e.date}{e.time ? ` · ${e.time}` : ""}
                  </span>
                  {e.location && (
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3 w-3" />
                      {e.location}
                    </span>
                  )}
                </div>
                {e.organizer && (
                  <div className="mt-1 text-xs text-muted-foreground">By {e.organizer}</div>
                )}
                {e.reason && (
                  <div className="mt-2 text-xs text-muted-foreground italic">{e.reason}</div>
                )}
              </div>
              {!e.image && (
                <div
                  className={cn(
                    "flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-lg text-center",
                    e.fit_score >= 70 && "bg-career-soft text-career",
                    e.fit_score >= 40 && e.fit_score < 70 && "bg-social-soft text-social",
                    e.fit_score < 40 && "bg-destructive/10 text-destructive",
                  )}
                >
                  <div className="text-xs font-semibold leading-none">{e.fit_score}</div>
                  <div className="mt-0.5 text-[9px] uppercase tracking-wide">fit</div>
                </div>
              )}
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => toast.success("Dismissed")}>
                Dismiss
              </Button>
              <Button
                size="sm"
                onClick={() => window.open(e.url, "_blank")}
              >
                View on Luma
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
