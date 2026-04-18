"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  GraduationCap,
  Briefcase,
  Users,
  Calendar as CalendarIcon,
  Settings,
  Sparkles,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { user } from "@/lib/mock-data"

const nav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/academic", label: "Academic", icon: GraduationCap, accent: "academic" as const },
  { href: "/career", label: "Career", icon: Briefcase, accent: "career" as const },
  { href: "/social", label: "Social", icon: Users, accent: "social" as const },
  { href: "/calendar", label: "Calendar", icon: CalendarIcon },
  { href: "/settings", label: "Settings", icon: Settings },
]

const accentDot: Record<string, string> = {
  academic: "bg-academic",
  career: "bg-career",
  social: "bg-social",
}

export function AppSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()

  return (
    <aside className="flex h-full w-64 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <Sparkles className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight">Campus Co-Pilot</div>
          <div className="text-xs text-muted-foreground">TUM AI Agent Suite</div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-2">
        <ul className="flex flex-col gap-1">
          {nav.map((item) => {
            const Icon = item.icon
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  className={cn(
                    "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="flex-1">{item.label}</span>
                  {item.accent ? (
                    <span
                      aria-hidden
                      className={cn("h-2 w-2 rounded-full", accentDot[item.accent])}
                    />
                  ) : null}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="m-3 rounded-xl border border-sidebar-border bg-card p-3">
        <div className="flex items-center gap-3">
          <Avatar className="h-9 w-9">
            <AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">
              {user.initials}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{user.name}</div>
            <div className="truncate text-xs text-muted-foreground">
              {user.program} — {user.semester}
            </div>
          </div>
        </div>
      </div>
    </aside>
  )
}
