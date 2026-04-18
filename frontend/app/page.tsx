"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { AgentBadge, agentBorder } from "@/components/agent-badge"
import { MasteryChart } from "@/components/mastery-chart"
import { PageHeader } from "@/components/page-header"
import { useChat } from "@/components/chat-context"
import {
  agentActivity as mockAgentActivity,
  deadlines,
  todayEvents,
  user,
} from "@/lib/mock-data"
import type { AgentType } from "@/lib/mock-data"
import { listActivity } from "@/lib/api"
import {
  ArrowRight,
  BookOpen,
  Briefcase,
  Clock,
  Dumbbell,
  MapPin,
  FileText,
} from "lucide-react"
import { cn } from "@/lib/utils"

const quickActions = [
  { icon: MapPin, label: "Book study room", prompt: "Find me a quiet study room near Mathematik for 2pm" },
  { icon: FileText, label: "Find thesis", prompt: "Find me thesis topics matching my ML background" },
  { icon: Dumbbell, label: "Book ZHS slot", prompt: "Book a ZHS climbing slot for Tuesday 18:00" },
  { icon: Briefcase, label: "Optimize CV for job", prompt: "Optimize my CV for the BMW ML Infrastructure role" },
]

function daysUntil(dateStr: string) {
  const d = new Date(dateStr).getTime()
  const now = Date.now()
  const diff = Math.ceil((d - now) / (1000 * 60 * 60 * 24))
  if (diff <= 0) return "today"
  if (diff === 1) return "tomorrow"
  return `in ${diff}d`
}

interface ActivityEntry {
  id: string | number
  icon: string
  text: string
  time: string
  agent: AgentType
}

function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return "yesterday"
  return `${days}d ago`
}

export default function DashboardPage() {
  const { openWithPrompt } = useChat()
  const [activities, setActivities] = useState<ActivityEntry[]>(
    mockAgentActivity.map((a) => ({ ...a, agent: a.agent as AgentType })),
  )

  const fetchActivities = useCallback(async () => {
    try {
      const { activities: items } = await listActivity(6)
      if (items.length > 0) {
        setActivities(
          items.map((item) => ({
            id: item.id,
            icon: item.icon,
            text: item.text,
            time: formatRelativeTime(item.created_at),
            agent: item.agent as AgentType,
          })),
        )
      }
    } catch {
      // keep mock data on failure
    }
  }, [])

  useEffect(() => {
    fetchActivities()
    const interval = setInterval(fetchActivities, 30_000)
    return () => clearInterval(interval)
  }, [fetchActivities])

  const sortedDeadlines = [...deadlines].sort((a, b) => b.priority - a.priority).slice(0, 5)

  return (
    <div>
      <PageHeader
        title={`Welcome back, ${user.name.split(" ")[0]}`}
        description="Your agents coordinated 6 autonomous actions today. Here's what's happening."
      />

      {/* Quick actions */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {quickActions.map((a) => {
          const Icon = a.icon
          return (
            <button
              key={a.label}
              onClick={() => openWithPrompt(a.prompt)}
              className="group flex items-center gap-3 rounded-xl border border-border bg-card p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-sm"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{a.label}</div>
                <div className="truncate text-xs text-muted-foreground">Delegate to agent</div>
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
            </button>
          )
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Today summary */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Today</CardTitle>
              <CardDescription>Next 3 events across all agents</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/calendar">
                Open calendar <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {todayEvents.map((e) => (
                <li
                  key={e.id}
                  className={cn(
                    "flex items-center gap-3 rounded-lg border border-border border-l-4 bg-card p-3",
                    agentBorder(e.agent),
                  )}
                >
                  <div className="flex min-w-[92px] items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <Clock className="h-3.5 w-3.5" />
                    {e.time}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{e.title}</div>
                    <div className="truncate text-xs text-muted-foreground">{e.location}</div>
                  </div>
                  <AgentBadge agent={e.agent} />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Agent activity */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Agent activity</CardTitle>
            <CardDescription>Recent autonomous actions</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-3">
              {activities.slice(0, 6).map((a) => (
                <li key={a.id} className="flex items-start gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-base">
                    {a.icon}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm leading-snug">{a.text}</div>
                    <div className="mt-0.5 flex items-center gap-2">
                      <AgentBadge agent={a.agent} />
                      <span className="text-xs text-muted-foreground">{a.time}</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Deadline queue */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Deadline queue</CardTitle>
              <CardDescription>Top 5 by priority · Moodle + TUMonline</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/academic">
                All deadlines <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y divide-border">
              {sortedDeadlines.map((d) => (
                <li key={d.id} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
                  <div className="w-16 shrink-0 font-mono text-xs font-medium text-primary">{d.course}</div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{d.task}</div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">Due {daysUntil(d.due)} · {d.weight}</span>
                    </div>
                  </div>
                  <div className="hidden w-32 sm:block">
                    <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wide text-muted-foreground">
                      <span>Gap</span>
                      <span>{d.masteryGap}%</span>
                    </div>
                    <Progress value={d.masteryGap} className="h-1.5" />
                  </div>
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-xs font-semibold text-primary">
                    {d.priority}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Mastery */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-primary" />
              Mastery overview
            </CardTitle>
            <CardDescription>% reviewed across enrolled courses</CardDescription>
          </CardHeader>
          <CardContent>
            <MasteryChart />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
