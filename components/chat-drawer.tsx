"use client"

import * as React from "react"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { AgentBadge } from "@/components/agent-badge"
import { useChat } from "@/components/chat-context"
import type { AgentType } from "@/lib/mock-data"
import { user } from "@/lib/mock-data"
import { cn } from "@/lib/utils"
import { ArrowUp, CalendarCheck2, CheckCircle2, Sparkles } from "lucide-react"

type Message =
  | {
      id: string
      role: "user"
      text: string
    }
  | {
      id: string
      role: "agent"
      agent: AgentType
      text: string
      streaming?: boolean
      action?: {
        kind: "booking" | "email" | "study-block"
        title: string
        detail: string
      }
    }

const suggestions = [
  "Find me a study room at 2pm",
  "What's due this week?",
  "Book a ZHS climbing slot",
  "Draft email to Prof. Günnemann",
]

function pickAgent(prompt: string): AgentType {
  const p = prompt.toLowerCase()
  if (/zhs|climb|sport|lunch|mensa|friend|event/.test(p)) return "social"
  if (/cv|job|intern|career|thesis|prof\.|email|prof /.test(p)) return "career"
  return "academic"
}

type AgentMessage = Extract<Message, { role: "agent" }>

function craftResponse(prompt: string, _agent: AgentType): { text: string; action?: AgentMessage["action"] } {
  const p = prompt.toLowerCase()
  if (p.includes("study room")) {
    return {
      text:
        "I found 2 quiet rooms near Mathematik-Informatik for 2pm. MI 02.07.023 has a whiteboard and a monitor and is free until 17:00 — I booked it for you.",
      action: { kind: "booking", title: "MI 02.07.023 booked", detail: "Today 14:00 – 17:00 · Mathematik-Informatik" },
    }
  }
  if (p.includes("due") || p.includes("deadline")) {
    return {
      text:
        "You have 3 deliverables this week. Highest priority is IN2064 Assignment 3 (Backpropagation) — due Apr 22, 15% weight, mastery gap 42%. I scheduled a 2h study block tomorrow afternoon.",
      action: { kind: "study-block", title: "Study block scheduled", detail: "Tue 14:00 – 16:00 · IN2064 Backprop" },
    }
  }
  if (p.includes("zhs") || p.includes("climb")) {
    return {
      text:
        "Registration opens in 2h 14m. I'm watching Boulderwelt Ost for Tue 18:00 and will auto-book it as soon as the slot drops.",
      action: { kind: "booking", title: "ZHS Climbing watcher armed", detail: "Boulderwelt Ost · Tue 18:00 · priority high" },
    }
  }
  if (p.includes("email") || p.includes("prof")) {
    return {
      text:
        "Drafted a professional outreach email to Prof. Günnemann with your research interests and 3 suggested meeting slots based on your calendar. It's waiting in your review queue — nothing is sent without your confirmation.",
      action: { kind: "email", title: "Draft ready for review", detail: "To: stephan.guennemann@tum.de · 3 meeting slots proposed" },
    }
  }
  return {
    text:
      "Got it. I'll coordinate with the other agents and surface the result here. Give me a moment to check calendars, Moodle, and TUMonline.",
  }
}

export function ChatDrawer() {
  const { open, setOpen, initialPrompt, consumeInitialPrompt } = useChat()
  const [messages, setMessages] = React.useState<Message[]>([
    {
      id: "welcome",
      role: "agent",
      agent: "academic",
      text:
        "Hi Alex! I coordinate your Academic, Career, and Social agents. Ask me anything — I'll route to the right specialist.",
    },
  ])
  const [input, setInput] = React.useState("")
  const scrollRef = React.useRef<HTMLDivElement>(null)

  const send = React.useCallback((text: string) => {
    if (!text.trim()) return
    const agent = pickAgent(text)
    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", text: text.trim() }
    const streamingMsg: Message = {
      id: `a-${Date.now()}`,
      role: "agent",
      agent,
      text: "",
      streaming: true,
    }
    setMessages((m) => [...m, userMsg, streamingMsg])
    setInput("")

    const { text: response, action } = craftResponse(text, agent)
    let i = 0
    const interval = setInterval(() => {
      i += Math.max(2, Math.round(response.length / 40))
      setMessages((m) =>
        m.map((msg) =>
          msg.id === streamingMsg.id && msg.role === "agent"
            ? { ...msg, text: response.slice(0, i) }
            : msg,
        ),
      )
      if (i >= response.length) {
        clearInterval(interval)
        setMessages((m) =>
          m.map((msg) =>
            msg.id === streamingMsg.id && msg.role === "agent"
              ? { ...msg, text: response, streaming: false, action }
              : msg,
          ),
        )
      }
    }, 35)
  }, [])

  React.useEffect(() => {
    if (open && initialPrompt) {
      send(initialPrompt)
      consumeInitialPrompt()
    }
  }, [open, initialPrompt, send, consumeInitialPrompt])

  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b border-border px-5 py-4">
          <SheetTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-primary" />
            Ask Co-Pilot
          </SheetTitle>
          <SheetDescription className="text-xs">
            Orchestrator routes your request to Academic, Career, or Social agents.
          </SheetDescription>
        </SheetHeader>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5">
          <div className="flex flex-col gap-4">
            {messages.map((msg) =>
              msg.role === "user" ? (
                <div key={msg.id} className="flex justify-end gap-2">
                  <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                    {msg.text}
                  </div>
                  <Avatar className="h-7 w-7">
                    <AvatarFallback className="bg-muted text-[10px] font-semibold">{user.initials}</AvatarFallback>
                  </Avatar>
                </div>
              ) : (
                <div key={msg.id} className="flex gap-2">
                  <div
                    className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                      msg.agent === "academic" && "bg-academic-soft text-academic",
                      msg.agent === "career" && "bg-career-soft text-career",
                      msg.agent === "social" && "bg-social-soft text-social-foreground",
                    )}
                  >
                    {msg.agent === "academic" ? "A" : msg.agent === "career" ? "C" : "S"}
                  </div>
                  <div className="flex max-w-[85%] flex-col gap-2">
                    <AgentBadge agent={msg.agent} label={`${msg.agent === "academic" ? "Academic" : msg.agent === "career" ? "Career" : "Social"} Agent${msg.streaming ? " is on it…" : ""}`} />
                    <div className="rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2 text-sm text-foreground">
                      {msg.text}
                      {msg.streaming ? <span className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse bg-foreground/60 align-middle" /> : null}
                    </div>
                    {msg.action && !msg.streaming ? <ActionCard kind={msg.action.kind} title={msg.action.title} detail={msg.action.detail} /> : null}
                  </div>
                </div>
              ),
            )}
          </div>
        </div>

        <div className="border-t border-border px-4 py-3">
          <div className="mb-2 flex flex-wrap gap-1.5">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                className="rounded-full border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              send(input)
            }}
            className="flex items-end gap-2"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  send(input)
                }
              }}
              rows={1}
              placeholder="Ask anything about your week…"
              className="min-h-10 max-h-32 flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
            />
            <Button type="submit" size="icon" className="h-10 w-10 shrink-0" aria-label="Send">
              <ArrowUp className="h-4 w-4" />
            </Button>
          </form>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function ActionCard({ kind, title, detail }: { kind: "booking" | "email" | "study-block"; title: string; detail: string }) {
  const Icon = kind === "email" ? CheckCircle2 : kind === "study-block" ? CalendarCheck2 : CheckCircle2
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-border bg-card p-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{title}</div>
        <div className="truncate text-xs text-muted-foreground">{detail}</div>
      </div>
    </div>
  )
}
