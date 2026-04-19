"use client"

import * as React from "react"
import { listActivity } from "@/lib/api"
import { agentActivity } from "@/lib/mock-data"
import type { AgentType } from "@/lib/mock-data"
import { cn } from "@/lib/utils"

interface TickerItem {
  id: string | number
  icon: string
  text: string
  time: string
  agent: AgentType
}

const agentDot: Record<string, string> = {
  academic: "bg-academic",
  career: "bg-career",
  social: "bg-social",
}

const agentName: Record<string, string> = {
  academic: "Academic",
  career: "Career",
  social: "Social",
}

function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export function ActivityTicker() {
  const [items, setItems] = React.useState<TickerItem[]>(
    agentActivity.slice(0, 5).map((a) => ({ ...a, agent: a.agent as AgentType })),
  )
  const [activeIndex, setActiveIndex] = React.useState(0)
  const [animKey, setAnimKey] = React.useState(0)
  const seenIdsRef = React.useRef<Set<string | number>>(new Set(agentActivity.map((a) => a.id)))

  React.useEffect(() => {
    const poll = async () => {
      try {
        const { activities } = await listActivity(5)
        if (activities.length === 0) return
        const mapped: TickerItem[] = activities.map((a) => ({
          id: a.id,
          icon: a.icon,
          text: a.text,
          time: formatRelativeTime(a.created_at),
          agent: a.agent as AgentType,
        }))
        const hasNew = mapped.some((m) => !seenIdsRef.current.has(m.id))
        if (hasNew) {
          setActiveIndex(0)
          setAnimKey((k) => k + 1)
        }
        seenIdsRef.current = new Set(mapped.map((m) => m.id))
        setItems(mapped)
      } catch {
        // keep existing items on failure
      }
    }

    poll()
    const interval = setInterval(poll, 10_000)
    return () => clearInterval(interval)
  }, [])

  React.useEffect(() => {
    if (items.length <= 1) return
    const cycle = setInterval(() => {
      setActiveIndex((i) => (i + 1) % items.length)
      setAnimKey((k) => k + 1)
    }, 4000)
    return () => clearInterval(cycle)
  }, [items.length])

  const item = items[activeIndex]
  if (!item) return null

  return (
    <div className="flex h-8 items-center gap-2 border-b border-border bg-muted/50 px-4 md:px-6">
      <div
        key={animKey}
        className="animate-ticker-slide-in flex min-w-0 flex-1 items-center gap-2"
      >
        <span className="text-sm leading-none">{item.icon}</span>
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", agentDot[item.agent] ?? "bg-primary")} />
        <span className="truncate text-xs">
          <span className="font-medium">{agentName[item.agent] ?? "Agent"}</span>
          {" — "}
          {item.text}
        </span>
      </div>
      <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">{item.time}</span>
    </div>
  )
}
