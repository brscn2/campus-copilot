"use client"

import * as React from "react"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { AgentBadge } from "@/components/agent-badge"
import { AgentMessage } from "@/components/agent-message"
import { useChat } from "@/components/chat-context"
import type { AgentType } from "@/lib/mock-data"
import { agentLabel, user } from "@/lib/mock-data"
import { cn } from "@/lib/utils"
import { ArrowUp, Briefcase, CalendarCheck2, CheckCircle2, GraduationCap, Sparkles, Users } from "lucide-react"

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
      routingAgent?: AgentType | null
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
  "Find thesis topics in ML",
]

function parseSSEEvent(raw: string): { event: string; data: string } | null {
  const lines = raw.split("\n")
  let event = ""
  let data = ""
  for (const line of lines) {
    if (line.startsWith("event: ")) event = line.slice(7)
    if (line.startsWith("data: ")) data = line.slice(6)
  }
  if (!event || !data) return null
  return { event, data }
}

async function sendToBackend(
  message: string,
  onThinking: () => void,
  onChunk: (text: string, agent: AgentType) => void,
  onDone: (text: string, agent: AgentType) => void,
  onError: () => void,
) {
  try {
    const res = await fetch("/backend/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: "frontend-default",
        student_id: "00000000-0000-0000-0000-000000000001",
      }),
    })

    if (!res.ok || !res.body) {
      onError()
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let finalText = ""
    let agent: AgentType = "academic"

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split("\n\n")
      buffer = parts.pop() || ""

      for (const part of parts) {
        const parsed = parseSSEEvent(part)
        if (!parsed) continue

        if (parsed.event === "thinking") {
          onThinking()
        } else if (parsed.event === "final") {
          const payload = JSON.parse(parsed.data)
          finalText = payload.message || ""
          agent = payload.agent || "academic"
        }
      }
    }

    if (finalText) {
      onDone(finalText, agent)
    } else {
      onError()
    }
  } catch {
    onError()
  }
}

export function ChatDrawer() {
  const { open, setOpen, initialPrompt, consumeInitialPrompt } = useChat()
  const [messages, setMessages] = React.useState<Message[]>([
    {
      id: "welcome",
      role: "agent",
      agent: "orchestrator",
      text:
        "Hi Alex! I'm **Campus Co-Pilot** — I coordinate your Academic, Career, and Social agents. Ask me anything and I'll route to the right specialist.",
    },
  ])
  const [input, setInput] = React.useState("")
  const [isLoading, setIsLoading] = React.useState(false)
  const scrollRef = React.useRef<HTMLDivElement>(null)

  const send = React.useCallback((text: string) => {
    if (!text.trim()) return
    const trimmed = text.trim()
    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", text: trimmed }
    const orchestratorId = `o-${Date.now()}`
    const specialistId = `s-${Date.now()}`

    setMessages((m) => [
      ...m,
      userMsg,
      {
        id: orchestratorId,
        role: "agent",
        agent: "orchestrator",
        text: "",
        streaming: true,
      },
    ])
    setInput("")
    setIsLoading(true)

    sendToBackend(
      trimmed,
      () => {
        setMessages((m) =>
          m.map((msg) =>
            msg.id === orchestratorId && msg.role === "agent"
              ? { ...msg, text: "__routing__", routingAgent: null }
              : msg,
          ),
        )
      },
      (chunk, agent) => {
        setMessages((m) => {
          const hasSpecialist = m.some((msg) => msg.id === specialistId)
          if (hasSpecialist) {
            return m.map((msg) =>
              msg.id === specialistId && msg.role === "agent"
                ? { ...msg, text: chunk, agent }
                : msg,
            )
          }
          return [
            ...m.map((msg) =>
              msg.id === orchestratorId && msg.role === "agent"
                ? {
                    ...msg,
                    text: `Handing off to **${agentLabel[agent]} Agent**…`,
                    streaming: false,
                    routingAgent: undefined,
                  }
                : msg,
            ),
            {
              id: specialistId,
              role: "agent",
              agent,
              text: chunk,
              streaming: true,
            },
          ]
        })
      },
      (finalText, agent) => {
        if (agent === "orchestrator") {
          setMessages((m) =>
            m.map((msg) =>
              msg.id === orchestratorId && msg.role === "agent"
                ? { ...msg, text: finalText, streaming: false, routingAgent: undefined }
                : msg,
            ),
          )
          setIsLoading(false)
          return
        }

        setMessages((m) =>
          m.map((msg) =>
            msg.id === orchestratorId && msg.role === "agent"
              ? { ...msg, routingAgent: agent }
              : msg,
          ),
        )

        setTimeout(() => {
          setMessages((m) => {
            const updated = m.map((msg) =>
              msg.id === orchestratorId && msg.role === "agent"
                ? {
                    ...msg,
                    text: `Handed off to **${agentLabel[agent]} Agent**.`,
                    streaming: false,
                    routingAgent: undefined,
                  }
                : msg,
            )

            const hasSpecialist = updated.some((msg) => msg.id === specialistId)
            if (hasSpecialist) {
              return updated.map((msg) =>
                msg.id === specialistId && msg.role === "agent"
                  ? { ...msg, text: finalText, agent, streaming: false }
                  : msg,
              )
            }

            return [
              ...updated,
              {
                id: specialistId,
                role: "agent" as const,
                agent,
                text: finalText,
                streaming: false,
              },
            ]
          })
          setIsLoading(false)
        }, 800)
      },
      () => {
        setMessages((m) =>
          m.map((msg) =>
            msg.id === orchestratorId && msg.role === "agent"
              ? {
                  ...msg,
                  text: "Backend is not reachable. Make sure the FastAPI server is running on port 8000.",
                  agent: "orchestrator" as AgentType,
                  streaming: false,
                }
              : msg,
          ),
        )
        setIsLoading(false)
      },
    )
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
            Campus Co-Pilot routes your request to Academic, Career, or Social agents.
          </SheetDescription>
        </SheetHeader>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5">
          <div className="flex flex-col gap-4">
            {messages.map((msg) =>
              msg.role === "user" ? (
                <div
                  key={msg.id}
                  className="flex animate-in fade-in slide-in-from-bottom-2 justify-end gap-2 duration-200"
                >
                  <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                    {msg.text}
                  </div>
                  <Avatar className="h-7 w-7">
                    <AvatarFallback className="bg-muted text-[10px] font-semibold">{user.initials}</AvatarFallback>
                  </Avatar>
                </div>
              ) : (
                <div
                  key={msg.id}
                  className="flex animate-in fade-in slide-in-from-bottom-2 gap-2 duration-300"
                >
                  <div className="relative h-7 w-7 shrink-0">
                    {msg.agent === "orchestrator" && msg.streaming ? (
                      <span
                        className="absolute inset-0 animate-ping rounded-full bg-primary/40 opacity-60"
                        aria-hidden
                      />
                    ) : null}
                    <div
                      className={cn(
                        "relative flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-semibold",
                        msg.agent === "academic" && "bg-academic-soft text-academic",
                        msg.agent === "career" && "bg-career-soft text-career",
                        msg.agent === "social" && "bg-social-soft text-social-foreground",
                        msg.agent === "orchestrator" && "bg-primary/10 text-primary",
                      )}
                    >
                      {msg.agent === "orchestrator" ? (
                        <Sparkles
                          className={cn(
                            "h-3.5 w-3.5 transition-transform",
                            msg.streaming && "animate-pulse",
                          )}
                          aria-hidden
                        />
                      ) : msg.agent === "academic" ? (
                        <GraduationCap className="h-3.5 w-3.5" aria-hidden />
                      ) : msg.agent === "career" ? (
                        <Briefcase className="h-3.5 w-3.5" aria-hidden />
                      ) : (
                        <Users className="h-3.5 w-3.5" aria-hidden />
                      )}
                    </div>
                  </div>
                  <div className="flex max-w-[85%] flex-col gap-2">
                    <AgentBadge
                      agent={msg.agent}
                      thinking={msg.streaming}
                      label={`${agentLabel[msg.agent]}${msg.agent === "orchestrator" ? "" : " Agent"}${msg.streaming ? " is thinking" : ""}`}
                    />
                    <div className="rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2 text-sm text-foreground">
                      {msg.streaming && msg.text === "" ? (
                        <TypingDots />
                      ) : msg.text === "__routing__" ? (
                        <RoutingIndicator resolvedAgent={msg.routingAgent ?? null} />
                      ) : (
                        <>
                          <AgentMessage>{msg.text}</AgentMessage>
                          {msg.streaming ? <span className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse bg-foreground/60 align-middle" /> : null}
                        </>
                      )}
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
                disabled={isLoading}
                className="rounded-full border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
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
              disabled={isLoading}
              placeholder="Ask anything about your week…"
              className="min-h-10 max-h-32 flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
            <Button type="submit" size="icon" className="h-10 w-10 shrink-0" aria-label="Send" disabled={isLoading}>
              <ArrowUp className="h-4 w-4" />
            </Button>
          </form>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function TypingDots() {
  return (
    <span
      className="inline-flex items-center gap-1 py-1"
      aria-label="Thinking"
      role="status"
    >
      <Bounce delay="0ms" />
      <Bounce delay="150ms" />
      <Bounce delay="300ms" />
    </span>
  )
}

function Bounce({ delay }: { delay: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-foreground/50"
      style={{ animationDelay: delay, animationDuration: "1s" }}
    />
  )
}

function RoutingIndicator({ resolvedAgent }: { resolvedAgent: AgentType | null }) {
  const agents: { type: AgentType; icon: typeof GraduationCap; label: string; color: string; bg: string; border: string; check: string }[] = [
    { type: "academic", icon: GraduationCap, label: "Academic", color: "text-academic", bg: "bg-academic-soft", border: "border-academic", check: "bg-academic" },
    { type: "career", icon: Briefcase, label: "Career", color: "text-career", bg: "bg-career-soft", border: "border-career", check: "bg-career" },
    { type: "social", icon: Users, label: "Social", color: "text-social-foreground", bg: "bg-social-soft", border: "border-social", check: "bg-social" },
  ]

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {resolvedAgent ? "Routed to" : "Evaluating agents"}
      </div>
      <div className="flex gap-2">
        {agents.map((a) => {
          const Icon = a.icon
          const isSelected = resolvedAgent === a.type
          const isDimmed = resolvedAgent !== null && resolvedAgent !== a.type
          return (
            <div
              key={a.type}
              className={cn(
                "relative flex flex-1 flex-col items-center gap-1.5 rounded-lg border p-2 transition-all duration-300",
                isSelected && `animate-agent-reveal border-2 ${a.border} ${a.bg}`,
                isDimmed && "scale-95 opacity-30",
                !resolvedAgent && "border-border bg-card",
              )}
            >
              {!resolvedAgent && (
                <span className="absolute inset-0 overflow-hidden rounded-lg">
                  <span className="absolute inset-y-0 w-1/3 animate-routing-scan bg-gradient-to-r from-transparent via-primary/10 to-transparent" />
                </span>
              )}
              <div className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full",
                isSelected ? a.bg : "bg-muted",
                !resolvedAgent && "animate-routing-pulse",
              )}>
                <Icon className={cn("h-3.5 w-3.5", isSelected ? a.color : "text-muted-foreground")} />
              </div>
              <span className={cn(
                "text-[10px] font-medium",
                isSelected ? a.color : "text-muted-foreground",
              )}>
                {a.label}
              </span>
              {isSelected && (
                <span className={cn("absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-bold text-white", a.check)}>
                  ✓
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
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
