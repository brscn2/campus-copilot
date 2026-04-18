import { cn } from "@/lib/utils"
import type { AgentType } from "@/lib/mock-data"
import { agentLabel } from "@/lib/mock-data"

const styles: Record<AgentType, string> = {
  academic: "bg-academic-soft text-academic border-academic/20",
  career: "bg-career-soft text-career border-career/20",
  social: "bg-social-soft text-social-foreground border-social/30",
  orchestrator: "bg-primary/10 text-primary border-primary/20",
}

const dots: Record<AgentType, string> = {
  academic: "bg-academic",
  career: "bg-career",
  social: "bg-social",
  orchestrator: "bg-primary",
}

export function AgentBadge({
  agent,
  className,
  withDot = true,
  label,
  thinking = false,
}: {
  agent: AgentType
  className?: string
  withDot?: boolean
  label?: string
  thinking?: boolean
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        styles[agent],
        className,
      )}
    >
      {withDot ? (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            dots[agent],
            thinking && "animate-pulse",
          )}
          aria-hidden
        />
      ) : null}
      <span className="inline-flex items-center">
        {label ?? agentLabel[agent]}
        {thinking ? (
          <span className="ml-0.5 inline-flex" aria-hidden>
            <Dot delay="0ms" />
            <Dot delay="150ms" />
            <Dot delay="300ms" />
          </span>
        ) : null}
      </span>
    </span>
  )
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="animate-pulse"
      style={{ animationDelay: delay, animationDuration: "1.2s" }}
    >
      .
    </span>
  )
}

export function AgentDot({ agent, className }: { agent: AgentType; className?: string }) {
  return <span className={cn("h-2 w-2 rounded-full", dots[agent], className)} aria-hidden />
}

export function agentBorder(agent: AgentType) {
  const map: Record<AgentType, string> = {
    academic: "border-l-academic",
    career: "border-l-career",
    social: "border-l-social",
    orchestrator: "border-l-primary",
  }
  return map[agent]
}
