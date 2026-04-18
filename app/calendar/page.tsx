"use client"

import * as React from "react"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { AgentBadge } from "@/components/agent-badge"
import { calendarEvents, weekDays } from "@/lib/mock-data"
import type { AgentType } from "@/lib/mock-data"
import { AlertTriangle, GripVertical, Settings2 } from "lucide-react"
import { cn } from "@/lib/utils"

const HOUR_START = 8
const HOUR_END = 20
const HOURS = Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, i) => HOUR_START + i)

const agentBg: Record<AgentType, string> = {
  academic: "bg-academic-soft border-academic/30 text-academic",
  career: "bg-career-soft border-career/30 text-career",
  social: "bg-social-soft border-social/40 text-social-foreground",
}

export default function CalendarPage() {
  const [conflictOpen, setConflictOpen] = React.useState<(typeof calendarEvents)[number] | null>(null)
  const [priorities, setPriorities] = React.useState(["Exam prep", "Academic lectures", "Career", "Sports", "Social"])

  const move = (idx: number, dir: -1 | 1) => {
    setPriorities((p) => {
      const next = [...p]
      const to = idx + dir
      if (to < 0 || to >= next.length) return p
      ;[next[idx], next[to]] = [next[to], next[idx]]
      return next
    })
  }

  return (
    <div>
      <PageHeader
        title="Calendar"
        description="Unified week view. Conflicts between agents are auto-resolved — you stay in control."
        actions={
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" className="gap-1.5">
                <Settings2 className="h-4 w-4" />
                Priorities
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-full sm:max-w-md">
              <SheetHeader>
                <SheetTitle>Orchestrator priorities</SheetTitle>
                <SheetDescription>
                  When agents propose overlapping bookings, higher items win. Drag to reorder.
                </SheetDescription>
              </SheetHeader>
              <ul className="mt-5 space-y-2">
                {priorities.map((p, i) => (
                  <li
                    key={p}
                    className="flex items-center gap-3 rounded-lg border border-border bg-card p-3"
                  >
                    <GripVertical className="h-4 w-4 text-muted-foreground" />
                    <span className="flex h-6 w-6 items-center justify-center rounded bg-primary/10 text-xs font-semibold text-primary">
                      {i + 1}
                    </span>
                    <span className="flex-1 text-sm font-medium">{p}</span>
                    <div className="flex gap-1">
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => move(i, -1)} disabled={i === 0}>
                        ↑
                      </Button>
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => move(i, 1)} disabled={i === priorities.length - 1}>
                        ↓
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </SheetContent>
          </Sheet>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <LegendItem agent="academic" label="Academic" />
        <LegendItem agent="career" label="Career" />
        <LegendItem agent="social" label="Social" />
        <div className="flex items-center gap-1.5">
          <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
          <span>Conflict</span>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-border bg-card">
        <div className="min-w-[880px]">
          {/* Header row */}
          <div className="grid grid-cols-[60px_repeat(7,1fr)] border-b border-border">
            <div className="border-r border-border" />
            {weekDays.map((d, i) => (
              <div
                key={d}
                className={cn(
                  "border-r border-border px-3 py-2 text-xs font-medium last:border-r-0",
                  i === 0 && "bg-primary/5",
                )}
              >
                <div>{d}</div>
                <div className="text-muted-foreground">Apr {20 + i}</div>
              </div>
            ))}
          </div>

          {/* Body */}
          <div className="relative grid grid-cols-[60px_repeat(7,1fr)]">
            {/* Hour labels */}
            <div className="border-r border-border">
              {HOURS.map((h) => (
                <div key={h} className="h-14 border-b border-border px-2 pt-1 text-[10px] text-muted-foreground last:border-b-0">
                  {String(h).padStart(2, "0")}:00
                </div>
              ))}
            </div>

            {/* Day columns */}
            {weekDays.map((_, dayIdx) => (
              <div key={dayIdx} className="relative border-r border-border last:border-r-0">
                {HOURS.map((h) => (
                  <div key={h} className="h-14 border-b border-border last:border-b-0" />
                ))}

                {calendarEvents
                  .filter((e) => e.day === dayIdx)
                  .map((e) => {
                    const top = (e.start - HOUR_START) * 56
                    const height = Math.max(28, (e.end - e.start) * 56 - 4)
                    return (
                      <button
                        key={e.id}
                        onClick={() => e.conflict && setConflictOpen(e)}
                        className={cn(
                          "absolute left-1 right-1 overflow-hidden rounded-lg border p-1.5 text-left text-xs shadow-sm transition-shadow hover:shadow-md",
                          agentBg[e.agent],
                          e.conflict && "ring-2 ring-destructive",
                        )}
                        style={{ top, height }}
                      >
                        <div className="flex items-center gap-1">
                          {e.conflict ? <AlertTriangle className="h-3 w-3 shrink-0 text-destructive" /> : null}
                          <span className="truncate font-medium leading-tight">{e.title}</span>
                        </div>
                        <div className="mt-0.5 truncate text-[10px] opacity-75">{e.location}</div>
                      </button>
                    )
                  })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <Dialog open={!!conflictOpen} onOpenChange={(o) => !o && setConflictOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-destructive" />
              Scheduling conflict
            </DialogTitle>
            <DialogDescription>
              Two agents proposed overlapping bookings for Tuesday 14:00 – 16:00.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <div className="rounded-lg border border-academic/30 bg-academic-soft/50 p-3 text-sm">
              <div className="flex items-center gap-2">
                <AgentBadge agent="academic" />
                <span className="font-medium">Study block: IN2086</span>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">Midterm in 7 days · mastery gap 59%</div>
            </div>
            <div className="rounded-lg border border-social/30 bg-social-soft/40 p-3 text-sm">
              <div className="flex items-center gap-2">
                <AgentBadge agent="social" />
                <span className="font-medium">ESN Welcome Drinks RSVP</span>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">Free reschedule · 3 friends also going</div>
            </div>
            <div className="rounded-lg border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Orchestrator rationale: </span>
              Your priority list places &ldquo;Exam prep&rdquo; above &ldquo;Social&rdquo;, and the ESN event has 2 other
              slots this week. Kept the study block; rescheduled RSVP to Fri.
            </div>
          </div>
          <DialogFooter className="sm:justify-between">
            <Button variant="outline" onClick={() => setConflictOpen(null)}>
              Accept resolution
            </Button>
            <Button variant="secondary" onClick={() => setConflictOpen(null)}>
              Override — keep both
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function LegendItem({ agent, label }: { agent: AgentType; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn("h-3 w-3 rounded border", agentBg[agent])} />
      {label}
    </div>
  )
}
