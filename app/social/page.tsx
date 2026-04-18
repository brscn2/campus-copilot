"use client"

import * as React from "react"
import { PageHeader } from "@/components/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { AgentBadge } from "@/components/agent-badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { friends, mensaMenu, socialEvents, zhsTrackers } from "@/lib/mock-data"
import {
  Calendar,
  Check,
  Dumbbell,
  MapPin,
  Plus,
  Send,
  Timer,
  UtensilsCrossed,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

export default function SocialPage() {
  return (
    <div>
      <PageHeader
        title="Social"
        description="ZHS bookings, student events, and lunch coordination — coordinated by your Social Agent."
        actions={<AgentBadge agent="social" className="px-2.5 py-1" />}
      />

      <Tabs defaultValue="zhs" className="w-full">
        <TabsList className="mb-5 w-full max-w-xl">
          <TabsTrigger value="zhs">ZHS Sniper</TabsTrigger>
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="lunch">Lunch Coordinator</TabsTrigger>
        </TabsList>

        <TabsContent value="zhs">
          <ZhsTab />
        </TabsContent>
        <TabsContent value="events">
          <EventsTab />
        </TabsContent>
        <TabsContent value="lunch">
          <LunchTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function ZhsTab() {
  const [addOpen, setAddOpen] = React.useState(false)

  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setAddOpen(true)} className="gap-1.5">
          <Plus className="h-4 w-4" />
          Add tracker
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {zhsTrackers.map((t) => (
          <Card key={t.id}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-social-soft text-social-foreground">
                    <Dumbbell className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="font-medium">{t.sport}</div>
                    <div className="text-xs text-muted-foreground">{t.venue}</div>
                    <div className="mt-1 text-xs text-muted-foreground">Preferred: {t.preferred}</div>
                  </div>
                </div>
                <StatusBadge status={t.status} />
              </div>
              <div className="mt-4 flex items-center justify-between rounded-lg bg-muted/50 p-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Timer className="h-3.5 w-3.5" />
                  Opens in
                </div>
                <div className="font-mono text-sm font-semibold tabular-nums">{t.opensIn}</div>
              </div>
              <div className="mt-3 flex items-center justify-between">
                <div className="text-xs text-muted-foreground">
                  Priority:{" "}
                  <span
                    className={cn(
                      "font-medium capitalize",
                      t.priority === "high" && "text-destructive",
                      t.priority === "medium" && "text-social-foreground",
                      t.priority === "low" && "text-muted-foreground",
                    )}
                  >
                    {t.priority}
                  </span>
                </div>
                <Button variant="outline" size="sm">Configure</Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add ZHS tracker</DialogTitle>
            <DialogDescription>
              We&apos;ll watch the registration portal and auto-book when it opens.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div>
              <div className="mb-1 text-xs text-muted-foreground">Sport</div>
              <Select defaultValue="climbing">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="climbing">Climbing</SelectItem>
                  <SelectItem value="bouldering">Bouldering</SelectItem>
                  <SelectItem value="badminton">Badminton</SelectItem>
                  <SelectItem value="swimming">Swimming</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-foreground">Preferred time slots</div>
              <Input defaultValue="Tue/Thu 18:00 – 20:00" />
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-foreground">Priority</div>
              <Select defaultValue="high">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button
              onClick={() => {
                toast.success("Tracker added — watching now")
                setAddOpen(false)
              }}
            >
              Start watching
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function StatusBadge({ status }: { status: "watching" | "booked" | "missed" }) {
  const map = {
    watching: { label: "Watching", cls: "bg-social-soft text-social-foreground" },
    booked: { label: "Booked ✓", cls: "bg-career-soft text-career" },
    missed: { label: "Missed", cls: "bg-destructive/10 text-destructive" },
  }
  const s = map[status]
  return <Badge className={cn("font-normal", s.cls)}>{s.label}</Badge>
}

function EventsTab() {
  const [category, setCategory] = React.useState<string>("all")
  const [freeOnly, setFreeOnly] = React.useState(false)

  const filtered = socialEvents.filter((e) => {
    if (category !== "all" && e.category !== category) return false
    if (freeOnly && !e.free) return false
    return true
  })

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            <SelectItem value="Social">Social</SelectItem>
            <SelectItem value="Outdoor">Outdoor</SelectItem>
            <SelectItem value="Food">Food</SelectItem>
            <SelectItem value="Nightlife">Nightlife</SelectItem>
          </SelectContent>
        </Select>
        <Button
          variant={freeOnly ? "default" : "outline"}
          size="sm"
          onClick={() => setFreeOnly((v) => !v)}
        >
          Free slot only
        </Button>
        <div className="ml-auto text-xs text-muted-foreground">
          {filtered.length} of {socialEvents.length} events
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {filtered.map((e) => (
          <Card key={e.id} className="overflow-hidden">
            <div className="flex h-24 items-end bg-gradient-to-br from-social-soft to-academic-soft p-3 text-social-foreground">
              <Badge variant="secondary" className="font-normal">{e.category}</Badge>
            </div>
            <CardContent className="pt-4">
              <div className="font-medium leading-snug">{e.title}</div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  {e.date} · {e.time}
                </span>
                <span className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {e.location}
                </span>
              </div>
              <Button
                size="sm"
                className="mt-3 w-full"
                onClick={() => toast.success(`${e.title} added to calendar`)}
              >
                Book & add to calendar
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  )
}

function LunchTab() {
  const [selected, setSelected] = React.useState<number[]>([1, 2])
  const [messageOpen, setMessageOpen] = React.useState(false)
  const [channel, setChannel] = React.useState<"matrix" | "whatsapp">("matrix")

  const toggle = (id: number) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  const slots = [
    { day: "Today", time: "12:30 – 13:15", mensa: "Mensa Garching" },
    { day: "Tomorrow", time: "12:00 – 12:45", mensa: "Mensa Stammgelände" },
  ]

  return (
    <>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Invite friends</CardTitle>
            <CardDescription>Tap chips to add to the lunch group</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {friends.map((f) => {
                const on = selected.includes(f.id)
                return (
                  <button
                    key={f.id}
                    onClick={() => toggle(f.id)}
                    className={cn(
                      "flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs transition-colors",
                      on
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card text-muted-foreground hover:bg-muted",
                    )}
                  >
                    <Avatar className="h-5 w-5">
                      <AvatarFallback className="bg-muted text-[9px]">{f.initials}</AvatarFallback>
                    </Avatar>
                    {f.name}
                    {on ? <Check className="h-3 w-3" /> : null}
                  </button>
                )
              })}
            </div>

            <div className="mt-6">
              <div className="mb-2 text-sm font-medium">Shared free slots</div>
              <div className="space-y-2">
                {slots.map((s, i) => (
                  <label
                    key={i}
                    className="flex cursor-pointer items-center justify-between rounded-lg border border-border p-3"
                  >
                    <div className="flex items-center gap-3">
                      <input type="radio" name="slot" defaultChecked={i === 0} className="accent-primary" />
                      <div>
                        <div className="text-sm font-medium">
                          {s.day} · {s.time}
                        </div>
                        <div className="text-xs text-muted-foreground">{s.mensa}</div>
                      </div>
                    </div>
                    <AgentBadge agent="social" />
                  </label>
                ))}
              </div>
            </div>

            <Button className="mt-4 w-full gap-1.5" onClick={() => setMessageOpen(true)}>
              <Send className="h-4 w-4" />
              Propose to group
            </Button>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <UtensilsCrossed className="h-4 w-4 text-primary" />
              Today&apos;s Mensa menu
            </CardTitle>
            <CardDescription>Mensa Garching · updated 09:30</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2">
              {mensaMenu.map((dish) => (
                <div key={dish.id} className="rounded-lg border border-border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-medium text-sm leading-snug">{dish.name}</div>
                    <div className="font-mono text-xs font-semibold tabular-nums text-primary">{dish.price}</div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {dish.tags.map((t) => (
                      <Badge
                        key={t}
                        variant="secondary"
                        className={cn(
                          "font-normal capitalize",
                          t === "vegan" && "bg-career-soft text-career",
                          t === "vegetarian" && "bg-academic-soft text-academic",
                        )}
                      >
                        {t}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Dialog open={messageOpen} onOpenChange={setMessageOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Message preview</DialogTitle>
            <DialogDescription>Review before sending to your group.</DialogDescription>
          </DialogHeader>
          <div className="flex gap-1">
            {(["matrix", "whatsapp"] as const).map((c) => (
              <Button
                key={c}
                size="sm"
                variant={channel === c ? "default" : "outline"}
                onClick={() => setChannel(c)}
                className="capitalize"
              >
                {c}
              </Button>
            ))}
          </div>
          <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm">
            <div className="text-xs text-muted-foreground">
              To: {friends.filter((f) => selected.includes(f.id)).map((f) => f.name).join(", ") || "—"} · via {channel}
            </div>
            <div className="mt-2">
              Hey! Lunch today 12:30 at Mensa Garching? They&apos;ve got Schweinebraten (€4.20) and a solid vegan
              Linseneintopf (€2.90). 🍽️
            </div>
          </div>
          <DialogFooter className="sm:justify-between">
            <Button variant="outline" onClick={() => setMessageOpen(false)} className="gap-1">
              <X className="h-3.5 w-3.5" />
              Cancel
            </Button>
            <Button
              onClick={() => {
                toast.success("Sent to group")
                setMessageOpen(false)
              }}
            >
              Send
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
