"use client"

import * as React from "react"
import { useTheme } from "next-themes"
import { Bell, Menu, Moon, Search, Sparkles, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useChat } from "@/components/chat-context"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export function Topbar({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)
  const { setOpen } = useChat()

  React.useEffect(() => setMounted(true), [])
  const isDark = mounted && (theme === "dark" || resolvedTheme === "dark")

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur md:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onToggleSidebar}
        aria-label="Toggle navigation"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <div className="relative hidden max-w-md flex-1 sm:block">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          placeholder="Search courses, rooms, jobs, events…"
          className="h-10 w-full rounded-lg border border-input bg-card pl-9 pr-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      <div className="flex-1 sm:hidden" />

      <div className="flex items-center gap-1.5 sm:gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
              <Bell className="h-5 w-5" />
              <Badge className="absolute -right-0.5 -top-0.5 h-5 min-w-5 rounded-full bg-destructive px-1.5 text-[10px] text-destructive-foreground">
                3
              </Badge>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80">
            <DropdownMenuLabel>Notifications</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="flex-col items-start gap-0.5">
              <div className="text-sm font-medium">New slides in IN0007</div>
              <div className="text-xs text-muted-foreground">Hash Tables — summarized by Academic Agent</div>
            </DropdownMenuItem>
            <DropdownMenuItem className="flex-col items-start gap-0.5">
              <div className="text-sm font-medium">ZHS slot opens in 2h 14m</div>
              <div className="text-xs text-muted-foreground">Climbing — Boulderwelt Ost</div>
            </DropdownMenuItem>
            <DropdownMenuItem className="flex-col items-start gap-0.5">
              <div className="text-sm font-medium">Draft email to Prof. Schmidt</div>
              <div className="text-xs text-muted-foreground">Awaiting your review</div>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button
          variant="ghost"
          size="icon"
          aria-label="Toggle theme"
          onClick={() => setTheme(isDark ? "light" : "dark")}
        >
          {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </Button>

        <Button
          onClick={() => setOpen(true)}
          className="ml-1 h-9 gap-2 rounded-lg"
        >
          <Sparkles className="h-4 w-4" />
          <span className="hidden sm:inline">Ask Co-Pilot</span>
          <span className="sm:hidden">Ask</span>
        </Button>
      </div>
    </header>
  )
}
