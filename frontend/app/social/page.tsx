"use client"

import * as React from "react"
import dynamic from "next/dynamic"
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
import {
  searchZhsCourses,
  searchEsnEvents,
  fetchMensaMenu,
  fetchMensaCanteens,
  fetchZhsCategories,
  fetchZhsSchedule,
  bookZhsCourse,
  type ZhsCourse,
  type ZhsCategory,
  type ZhsSchedule,
  type EsnEvent,
  type MensaDish,
  type MensaCanteen,
} from "@/lib/api"
import {
  Calendar,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Dumbbell,
  ExternalLink,
  Leaf,
  Loader2,
  MapPin,
  Search,
  ShoppingCart,
  Ticket,
  Users,
  UtensilsCrossed,
  Vegan,
} from "lucide-react"

const MensaMap = dynamic(() => import("@/components/mensa-map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[350px] items-center justify-center rounded-lg border border-border bg-muted/30">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
    </div>
  ),
})

export default function SocialPage() {
  return (
    <div>
      <PageHeader
        title="Social"
        description="ZHS sports, ESN TUMi events, and lunch coordination — coordinated by your Social Agent."
        actions={<AgentBadge agent="social" className="px-2.5 py-1" />}
      />

      <Tabs defaultValue="zhs" className="w-full">
        <TabsList className="mb-5 w-full max-w-xl">
          <TabsTrigger value="zhs">ZHS Sports</TabsTrigger>
          <TabsTrigger value="events">ESN Events</TabsTrigger>
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

const LEVEL_COLORS: Record<string, string> = {
  Beginner: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  Intermediate: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  Advanced: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  "All Levels": "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
}

function ZhsTab() {
  const [courses, setCourses] = React.useState<ZhsCourse[]>([])
  const [categories, setCategories] = React.useState<ZhsCategory[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [search, setSearch] = React.useState("")
  const [debouncedSearch, setDebouncedSearch] = React.useState("")
  const [selectedCategory, setSelectedCategory] = React.useState<string | null>(null)
  const [selectedLocation, setSelectedLocation] = React.useState<string | null>(null)
  const [selectedLevel, setSelectedLevel] = React.useState<string | null>(null)
  const [selectedCourse, setSelectedCourse] = React.useState<ZhsCourse | null>(null)
  const [schedule, setSchedule] = React.useState<ZhsSchedule | null>(null)
  const [scheduleLoading, setScheduleLoading] = React.useState(false)
  const [booking, setBooking] = React.useState(false)
  const [bookingResult, setBookingResult] = React.useState<{
    message: string
    status: string
  } | null>(null)

  React.useEffect(() => {
    fetchZhsCategories().then(setCategories).catch(() => {})
  }, [])

  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 400)
    return () => clearTimeout(timer)
  }, [search])

  const handleViewSchedule = async (course: ZhsCourse) => {
    setSelectedCourse(course)
    setSchedule(null)
    setScheduleLoading(true)
    setBookingResult(null)
    try {
      const data = await fetchZhsSchedule(course.name_de || course.name)
      setSchedule(data)
    } catch {
      setSchedule(null)
    } finally {
      setScheduleLoading(false)
    }
  }

  const handleBook = async (opts: {
    courseIndex?: number
    slotId?: string
  }) => {
    if (!selectedCourse) return
    setBooking(true)
    setBookingResult(null)
    try {
      const result = await bookZhsCourse({
        course_name: selectedCourse.name_de || selectedCourse.name,
        course_index: opts.courseIndex,
        slot_id: opts.slotId,
      })
      setBookingResult({ message: result.message, status: result.status })
      // Refresh schedule to reflect updated button states
      if (result.status !== "error") {
        try {
          const updated = await fetchZhsSchedule(selectedCourse.name_de || selectedCourse.name)
          setSchedule(updated)
        } catch { /* keep stale data if refresh fails */ }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Booking failed"
      setBookingResult({ message: msg, status: "error" })
    } finally {
      setBooking(false)
    }
  }

  React.useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    searchZhsCourses({
      keyword: debouncedSearch || undefined,
      category: selectedCategory ?? undefined,
      location: selectedLocation ?? undefined,
      level: selectedLevel ?? undefined,
    })
      .then((data) => {
        if (!cancelled) setCourses(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message ?? "Failed to load courses")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [debouncedSearch, selectedCategory, selectedLocation, selectedLevel])

  const locations = React.useMemo(() => {
    const set = new Set(courses.map((c) => c.location))
    return Array.from(set).sort()
  }, [courses])

  const hasFilters = !!selectedCategory || !!selectedLocation || !!selectedLevel
  const clearFilters = () => {
    setSelectedCategory(null)
    setSelectedLocation(null)
    setSelectedLevel(null)
  }

  return (
    <>
      {/* Category discovery row */}
      {!debouncedSearch && !hasFilters && categories.length > 0 && (
        <div className="mb-5">
          <h3 className="mb-2.5 text-sm font-semibold text-foreground">Browse by Category</h3>
          <div className="flex flex-wrap gap-2">
            {categories.map((cat) => (
              <button
                key={cat.category}
                onClick={() => setSelectedCategory(cat.category)}
                className="group flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-sm transition-all hover:border-primary/40 hover:bg-primary/5 hover:shadow-sm"
              >
                <span className="text-base">{cat.emoji}</span>
                <span className="font-medium">{cat.category}</span>
                <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary">
                  {cat.count}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Search + filter bar */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search sports (yoga, climbing, basketball...)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Active filter pills */}
        {selectedCategory && (
          <Badge
            variant="secondary"
            className="cursor-pointer gap-1 pr-1.5"
            onClick={() => setSelectedCategory(null)}
          >
            {categories.find((c) => c.category === selectedCategory)?.emoji} {selectedCategory}
            <span className="ml-0.5 text-[10px]">×</span>
          </Badge>
        )}
        {selectedLocation && (
          <Badge
            variant="secondary"
            className="cursor-pointer gap-1 pr-1.5"
            onClick={() => setSelectedLocation(null)}
          >
            <MapPin className="h-3 w-3" /> {selectedLocation}
            <span className="ml-0.5 text-[10px]">×</span>
          </Badge>
        )}
        {selectedLevel && (
          <Badge
            variant="secondary"
            className="cursor-pointer gap-1 pr-1.5"
            onClick={() => setSelectedLevel(null)}
          >
            {selectedLevel}
            <span className="ml-0.5 text-[10px]">×</span>
          </Badge>
        )}
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters} className="text-xs text-muted-foreground">
            Clear all
          </Button>
        )}

        <div className="ml-auto text-xs text-muted-foreground">
          {loading ? "Searching..." : `${courses.length} courses`}
        </div>
      </div>

      {/* Level + Location quick filter row */}
      {(courses.length > 0 || hasFilters) && (
        <div className="mb-4 flex flex-wrap gap-2">
          {(["Beginner", "Intermediate", "Advanced", "All Levels"] as const).map((lvl) => (
            <Button
              key={lvl}
              variant={selectedLevel === lvl ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedLevel(selectedLevel === lvl ? null : lvl)}
              className="text-xs"
            >
              {lvl}
            </Button>
          ))}
          <div className="mx-1 h-6 w-px bg-border" />
          {locations.map((loc) => (
            <Button
              key={loc}
              variant={selectedLocation === loc ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedLocation(selectedLocation === loc ? null : loc)}
              className="gap-1 text-xs"
            >
              <MapPin className="h-3 w-3" />
              {loc}
            </Button>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && courses.length === 0 ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading ZHS courses...
        </div>
      ) : courses.length === 0 && !loading ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Dumbbell className="mb-2 h-8 w-8" />
          <div>No courses found{search ? ` for "${search}"` : ""}</div>
          {hasFilters && (
            <Button variant="link" size="sm" onClick={clearFilters} className="mt-2">
              Clear filters
            </Button>
          )}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {courses.map((c, i) => (
            <Card
              key={c.id}
              className="animate-stagger-fade-in cursor-pointer overflow-hidden transition-shadow hover:shadow-md"
              style={{ animationDelay: `${i * 60}ms` }}
              onClick={() => handleViewSchedule(c)}
            >
              {c.poster_url ? (
                <div className="relative h-36 overflow-hidden bg-muted">
                  <img
                    src={c.poster_url}
                    alt={c.name}
                    className="h-full w-full object-cover"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
                  <div className="absolute bottom-2 left-2 flex gap-1.5">
                    <Badge className={`text-[10px] font-normal ${LEVEL_COLORS[c.level] ?? ""}`}>
                      {c.level}
                    </Badge>
                    <Badge variant="secondary" className="bg-white/90 text-[10px] font-normal text-foreground backdrop-blur-sm">
                      <MapPin className="mr-0.5 h-2.5 w-2.5" /> {c.location}
                    </Badge>
                  </div>
                </div>
              ) : (
                <div className="relative flex h-28 items-end bg-gradient-to-br from-social-soft to-academic-soft p-3">
                  <span className="text-3xl">{c.emoji}</span>
                  <div className="absolute bottom-2 right-2 flex gap-1.5">
                    <Badge className={`text-[10px] font-normal ${LEVEL_COLORS[c.level] ?? ""}`}>
                      {c.level}
                    </Badge>
                  </div>
                </div>
              )}
              <CardContent className="pt-3">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-lg leading-none">{c.emoji}</span>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-sm leading-snug">{c.name}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span>{c.category}</span>
                      {!c.poster_url && (
                        <span className="flex items-center gap-0.5">
                          <MapPin className="h-2.5 w-2.5" /> {c.location}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                {c.description && (
                  <p className="mt-2 text-xs text-muted-foreground line-clamp-2">
                    {c.description}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Course detail dialog */}
      <Dialog open={!!selectedCourse} onOpenChange={() => setSelectedCourse(null)}>
        {selectedCourse && (
          <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <span className="text-xl">{selectedCourse.emoji}</span>
                {selectedCourse.name}
              </DialogTitle>
              <DialogDescription>{selectedCourse.category} &middot; {selectedCourse.level} &middot; {selectedCourse.location}</DialogDescription>
            </DialogHeader>

            {selectedCourse.poster_url && (
              <div className="overflow-hidden rounded-lg">
                <img src={selectedCourse.poster_url} alt={selectedCourse.name} className="h-36 w-full object-cover" />
              </div>
            )}

            {selectedCourse.description && (
              <p className="text-sm text-muted-foreground">{selectedCourse.description}</p>
            )}

            {/* Schedule / Timeslots */}
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Calendar className="h-4 w-4" />
                Schedule & Booking
              </h3>

              {scheduleLoading ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Loading timetable from ZHS...
                </div>
              ) : schedule?.type === "weekly_course" && schedule.courses.length > 0 ? (
                <div className="space-y-2">
                  {schedule.courses.map((c, i) => (
                    <div key={i} className="flex items-center justify-between rounded-lg border border-border p-3">
                      <div className="min-w-0 flex-1 space-y-1">
                        {c.name && <div className="text-sm font-medium">{c.name}</div>}
                        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                          {c.schedule && (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" /> {c.schedule}
                            </span>
                          )}
                          {c.date_range && (
                            <span className="flex items-center gap-1">
                              <Calendar className="h-3 w-3" /> {c.date_range}
                            </span>
                          )}
                          {c.location && (
                            <span className="flex items-center gap-1">
                              <MapPin className="h-3 w-3" /> {c.location}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {c.price && <span className="text-xs font-mono font-semibold text-primary">{c.price}</span>}
                          {c.leader && <span className="text-[11px] text-muted-foreground">Leader: {c.leader}</span>}
                          {c.status === "available" && (
                            <Badge className="bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 text-[10px]">Available</Badge>
                          )}
                          {c.status === "join_waiting_list" && (
                            <Badge className="bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 text-[10px]">Waitlist</Badge>
                          )}
                          {c.status === "booked_out" && (
                            <Badge variant="destructive" className="text-[10px]">Sold out</Badge>
                          )}
                          {c.status === "booking_expired" && (
                            <Badge variant="outline" className="text-[10px] text-muted-foreground">Expired</Badge>
                          )}
                          {c.status === "already_on_waitlist" && (
                            <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 text-[10px]">On waitlist</Badge>
                          )}
                          {(c.status === "already_in_cart" || c.status === "in_cart") && (
                            <Badge className="bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 text-[10px]">In cart</Badge>
                          )}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        className="ml-3 shrink-0 gap-1.5"
                        disabled={
                          booking ||
                          c.disabled === true ||
                          c.status === "booked_out" ||
                          c.status === "booking_expired" ||
                          c.status === "already_on_waitlist"
                        }
                        variant={c.status === "booked_out" || c.status === "booking_expired" ? "outline" : "default"}
                        onClick={() => handleBook({ courseIndex: i })}
                      >
                        {booking ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : c.status === "booked_out" ? (
                          "Sold out"
                        ) : c.status === "booking_expired" ? (
                          "Expired"
                        ) : c.status === "already_on_waitlist" ? (
                          <><Check className="h-3.5 w-3.5" /> On waitlist</>
                        ) : c.status === "already_in_cart" || c.status === "in_cart" ? (
                          <><ShoppingCart className="h-3.5 w-3.5" /> In cart — checkout</>
                        ) : c.status === "join_waiting_list" ? (
                          <><ShoppingCart className="h-3.5 w-3.5" /> Join waitlist</>
                        ) : (
                          <><ShoppingCart className="h-3.5 w-3.5" /> Book</>
                        )}
                      </Button>
                    </div>
                  ))}
                </div>
              ) : schedule?.type === "free_play" && schedule.slots.length > 0 ? (
                <div className="space-y-3">
                  {/* Group slots by day */}
                  {Object.entries(
                    schedule.slots.reduce<Record<string, typeof schedule.slots>>((acc, s) => {
                      const key = `${s.day} ${s.date}`
                      if (!acc[key]) acc[key] = []
                      acc[key].push(s)
                      return acc
                    }, {})
                  ).map(([dayLabel, daySlots]) => (
                    <div key={dayLabel}>
                      <div className="mb-1.5 text-xs font-semibold text-muted-foreground">{dayLabel}</div>
                      <div className="grid gap-1.5 sm:grid-cols-2">
                        {daySlots.map((s, i) => (
                          <button
                            key={i}
                            disabled={!s.available || booking}
                            onClick={() => s.id && handleBook({ slotId: s.id })}
                            className={`flex items-center justify-between rounded-lg border p-3 text-left text-sm transition-colors ${
                              s.available
                                ? "border-green-200 bg-green-50 hover:bg-green-100 dark:border-green-800 dark:bg-green-950/30 dark:hover:bg-green-900/40 cursor-pointer"
                                : "border-border bg-muted/30 cursor-not-allowed opacity-60"
                            }`}
                          >
                            <div>
                              <div className="font-semibold">{s.time || "—"}</div>
                              <div className="text-xs text-muted-foreground">{s.description}</div>
                            </div>
                            {s.available && (
                              <Badge className="shrink-0 bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                                <ShoppingCart className="mr-1 h-3 w-3" /> Book
                              </Badge>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : !scheduleLoading && schedule ? (
                <div className="rounded-lg border border-border bg-muted/30 p-4 text-center text-sm text-muted-foreground">
                  {schedule.message
                    ? schedule.message
                    : schedule.type === "free_play"
                      ? "No timeslots available right now. Check back later."
                      : "No schedule data found. Try viewing on ZHS directly."}
                </div>
              ) : null}
            </div>

            {bookingResult && (
              <div className={`rounded-lg border p-3 text-sm ${
                bookingResult.status === "error"
                  ? "border-destructive/50 bg-destructive/10 text-destructive"
                  : bookingResult.status === "in_cart"
                    ? "border-blue-500/50 bg-blue-500/10 text-blue-700 dark:text-blue-400"
                    : bookingResult.status === "joined_waitlist"
                      ? "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                      : "border-green-500/50 bg-green-500/10 text-green-700 dark:text-green-400"
              }`}>
                {bookingResult.status === "error" ? (
                  bookingResult.message
                ) : bookingResult.status === "in_cart" ? (
                  <span className="flex items-center gap-1.5">
                    <ShoppingCart className="h-4 w-4" />
                    {bookingResult.message}
                  </span>
                ) : bookingResult.status === "joined_waitlist" ? (
                  <span className="flex items-center gap-1.5">
                    <Users className="h-4 w-4" />
                    {bookingResult.message}
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <Check className="h-4 w-4" />
                    {bookingResult.message}
                  </span>
                )}
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => { setSelectedCourse(null); setBookingResult(null); setSchedule(null) }}>
                Close
              </Button>
              {selectedCourse.url && (
                <Button variant="outline" size="sm" asChild>
                  <a href={selectedCourse.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                    View on ZHS
                  </a>
                </Button>
              )}
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </>
  )
}

function EventsTab() {
  const [events, setEvents] = React.useState<EsnEvent[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [search, setSearch] = React.useState("")
  const [debouncedSearch, setDebouncedSearch] = React.useState("")
  const [availableOnly, setAvailableOnly] = React.useState(false)
  const [selectedEvent, setSelectedEvent] = React.useState<EsnEvent | null>(null)

  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 400)
    return () => clearTimeout(timer)
  }, [search])

  React.useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    searchEsnEvents({
      keyword: debouncedSearch || undefined,
      available_only: availableOnly || undefined,
    })
      .then((data) => {
        if (!cancelled) setEvents(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message ?? "Failed to load events")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [debouncedSearch, availableOnly])

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search events (party, hiking, culture...)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button
          variant={availableOnly ? "default" : "outline"}
          size="sm"
          onClick={() => setAvailableOnly((v) => !v)}
        >
          <Ticket className="mr-1.5 h-3.5 w-3.5" />
          Available only
        </Button>
        <div className="ml-auto text-xs text-muted-foreground">
          {loading ? "Searching..." : `${events.length} upcoming events`}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && events.length === 0 ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading ESN TUMi events...
        </div>
      ) : events.length === 0 && !loading ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Calendar className="mb-2 h-8 w-8" />
          <div>No upcoming events found{search ? ` for "${search}"` : ""}</div>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {events.map((e, i) => (
            <Card
              key={e.id}
              className="animate-stagger-fade-in cursor-pointer overflow-hidden transition-shadow hover:shadow-md"
              style={{ animationDelay: `${i * 60}ms` }}
              onClick={() => setSelectedEvent(e)}
            >
              <div className="flex h-24 items-end bg-gradient-to-br from-social-soft to-academic-soft p-3 text-social-foreground">
                <div className="flex items-center gap-2">
                  {e.is_full ? (
                    <Badge variant="destructive" className="font-normal">Full</Badge>
                  ) : e.price === "Free" ? (
                    <Badge variant="secondary" className="bg-career-soft text-career font-normal">Free</Badge>
                  ) : (
                    <Badge variant="secondary" className="font-normal">{e.price}</Badge>
                  )}
                  {typeof e.spots_available === "number" && e.spots_available > 0 && e.spots_available <= 10 && (
                    <Badge variant="secondary" className="bg-destructive/10 text-destructive font-normal">
                      {e.spots_available} spots left
                    </Badge>
                  )}
                </div>
              </div>
              <CardContent className="pt-4">
                <div className="font-medium leading-snug">{e.title}</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    {e.date}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {e.time} – {e.end_time}
                  </span>
                  {e.location && (
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3 w-3" />
                      {e.location}
                    </span>
                  )}
                </div>
                <div className="mt-1.5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Users className="h-3 w-3" />
                    {e.organizer}
                  </span>
                </div>
                <Button
                  size="sm"
                  className="mt-3 w-full gap-1.5"
                  disabled={e.is_full}
                  asChild={!e.is_full}
                  onClick={(ev) => ev.stopPropagation()}
                >
                  {e.is_full ? (
                    <span>Fully booked</span>
                  ) : (
                    <a href={e.registration_url} target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="h-3.5 w-3.5" />
                      Register on ESN TUMi
                    </a>
                  )}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!selectedEvent} onOpenChange={() => setSelectedEvent(null)}>
        {selectedEvent && (
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>{selectedEvent.title}</DialogTitle>
              <DialogDescription>{selectedEvent.organizer}</DialogDescription>
            </DialogHeader>
            <div className="space-y-3 text-sm">
              <div className="flex flex-wrap gap-3">
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Calendar className="h-4 w-4" />
                  {selectedEvent.date}
                </div>
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  {selectedEvent.time} – {selectedEvent.end_time}
                </div>
                {selectedEvent.location && (
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <MapPin className="h-4 w-4" />
                    {selectedEvent.location}
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <Badge variant="outline">{selectedEvent.price}</Badge>
                {selectedEvent.is_full ? (
                  <Badge variant="destructive">Full</Badge>
                ) : typeof selectedEvent.spots_available === "number" ? (
                  <Badge variant="secondary">{selectedEvent.spots_available} spots</Badge>
                ) : (
                  <Badge variant="secondary">Unlimited spots</Badge>
                )}
              </div>
              {selectedEvent.description && (
                <p className="text-muted-foreground leading-relaxed">
                  {selectedEvent.description}
                </p>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setSelectedEvent(null)}>
                Close
              </Button>
              <Button
                disabled={selectedEvent.is_full}
                asChild={!selectedEvent.is_full}
              >
                {selectedEvent.is_full ? (
                  <span>Fully booked</span>
                ) : (
                  <a href={selectedEvent.registration_url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                    Register on ESN TUMi
                  </a>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </>
  )
}

function getWeekdayDate(offset: number): string {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  return d.toISOString().split("T")[0]
}

function formatDateLabel(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00")
  const today = new Date()
  today.setHours(12, 0, 0, 0)
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000)
  const weekday = d.toLocaleDateString("en-US", { weekday: "short" })
  const day = d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
  if (diff === 0) return `Today (${day})`
  if (diff === 1) return `Tomorrow (${day})`
  if (diff === -1) return `Yesterday (${day})`
  return `${weekday}, ${day}`
}

const DISH_EMOJI_RULES: [RegExp, string][] = [
  [/pizza/i, "🍕"],
  [/burger/i, "🍔"],
  [/pasta|nudel|spaghet|penne|tagliat|macaron|lasagn|rigatoni|fusilli|tortellini|gnocchi/i, "🍝"],
  [/sushi/i, "🍣"],
  [/suppe|soup|eintopf|brühe|bouillon/i, "🍲"],
  [/salat|salad/i, "🥗"],
  [/pommes|frit|fries|kartoffel|potato|bratkartoffel|kroketten/i, "🍟"],
  [/hähnchen|chicken|hühn|geflügel|hendl|huhn|poultry/i, "🍗"],
  [/steak|rind|beef|rump|filet.*fleisch|braten|roastbeef/i, "🥩"],
  [/schwein|pork|schnitzel|leberkäs|kassler/i, "🥩"],
  [/wurst|sausage|bratwurst|currywurst|weißwurst/i, "🌭"],
  [/fisch|fish|lachs|salmon|forelle|kabeljau|pangasius|seelachs|dorade/i, "🐟"],
  [/reis|rice|risotto|pilaw/i, "🍚"],
  [/kuchen|cake|torte|muffin|brownie/i, "🍰"],
  [/eis\b|ice cream|gelato|sorbet/i, "🍨"],
  [/dessert|pudding|mousse|crème|panna cotta|tiramisu/i, "🍮"],
  [/curry/i, "🍛"],
  [/wrap|burrito|taco/i, "🌯"],
  [/sandwich|panini|ciabatta|baguette|semmel|brötchen/i, "🥪"],
  [/pfannkuchen|pancake|crêpe|kaiserschmarrn/i, "🥞"],
  [/gemüse|vegetable|veggie|brokkoli|blumenkohl|zucchini|aubergine|tofu|seitan|tempeh/i, "🥦"],
  [/pilz|mushroom|champignon/i, "🍄"],
  [/käse|cheese|überback/i, "🧀"],
  [/ei\b|eier|omelette|rührei|spiegelei/i, "🍳"],
  [/apfel|apple/i, "🍎"],
  [/obst|fruit|beeren|berry/i, "🍓"],
  [/brot|bread/i, "🍞"],
  [/teigtasche|maultasche|dumpling|knödel|kloß/i, "🥟"],
  [/bowl/i, "🥙"],
  [/nuss|nut|mandel|almond|erdnuss/i, "🥜"],
]

function dishEmoji(name: string): string {
  for (const [pattern, emoji] of DISH_EMOJI_RULES) {
    if (pattern.test(name)) return emoji
  }
  return "🍽️"
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (v: number) => (v * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function LunchTab() {
  const [canteens, setCanteens] = React.useState<MensaCanteen[]>([])
  const [selectedMensa, setSelectedMensa] = React.useState("mensa-garching")
  const [dateOffset, setDateOffset] = React.useState(0)
  const [dishes, setDishes] = React.useState<MensaDish[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [filter, setFilter] = React.useState<"all" | "vegetarian" | "vegan">("all")
  const [userPos, setUserPos] = React.useState<[number, number] | null>(null)

  const targetDate = getWeekdayDate(dateOffset)

  React.useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setUserPos([pos.coords.latitude, pos.coords.longitude]),
      () => {},
      { enableHighAccuracy: false, timeout: 8000 },
    )
  }, [])

  React.useEffect(() => {
    fetchMensaCanteens()
      .then(setCanteens)
      .catch(() => {})
  }, [])

  React.useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchMensaMenu({
      mensa: selectedMensa,
      target_date: targetDate,
      vegetarian_only: filter === "vegetarian" || undefined,
      vegan_only: filter === "vegan" || undefined,
    })
      .then((data) => {
        if (!cancelled) setDishes(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message ?? "Failed to load menu")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [selectedMensa, targetDate, filter])

  const distanceFn = React.useCallback(
    (lat: number, lng: number): number | null => {
      if (!userPos) return null
      return haversineKm(userPos[0], userPos[1], lat, lng)
    },
    [userPos],
  )

  const sortedCanteens = React.useMemo(() => {
    const withDist = canteens.map((c) => ({
      ...c,
      dist: distanceFn(c.latitude, c.longitude),
    }))
    withDist.sort((a, b) => {
      if (a.dist !== null && b.dist !== null) return a.dist - b.dist
      if (a.dist !== null) return -1
      if (b.dist !== null) return 1
      return a.name.localeCompare(b.name)
    })
    return withDist
  }, [canteens, distanceFn])

  const selectedCanteen = canteens.find((c) => c.canteen_id === selectedMensa)
  const mensaName = selectedCanteen?.name ?? selectedMensa
  const mensaHours = selectedCanteen?.open_hours
  const dayKey = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][new Date(targetDate + "T12:00:00").getDay() === 0 ? 6 : new Date(targetDate + "T12:00:00").getDay() - 1]
  const todayHours = mensaHours?.[dayKey]

  return (
    <div className="space-y-4">
      <MensaMap
        canteens={canteens}
        selectedMensa={selectedMensa}
        userPos={userPos}
        onSelectMensa={setSelectedMensa}
        distanceFn={distanceFn}
      />

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                <UtensilsCrossed className="h-4 w-4 shrink-0 text-primary" />
                <Select value={selectedMensa} onValueChange={setSelectedMensa}>
                  <SelectTrigger className="h-8 w-full max-w-xs text-sm font-semibold">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-h-[300px]">
                    {sortedCanteens.map((c) => (
                      <SelectItem key={c.canteen_id} value={c.canteen_id}>
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate">{c.name}</span>
                          {c.dist !== null && (
                            <span className="shrink-0 text-[10px] text-muted-foreground tabular-nums">
                              {c.dist < 1
                                ? `${Math.round(c.dist * 1000)}m`
                                : `${c.dist.toFixed(1)}km`}
                            </span>
                          )}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <CardDescription className="pl-6">
                {todayHours ? `Open ${todayHours.start} – ${todayHours.end}` : ""}
                {todayHours ? " · " : ""}{formatDateLabel(targetDate)}
              </CardDescription>
            </div>
            <AgentBadge agent="social" />
          </div>
        </CardHeader>
        <CardContent>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDateOffset((d) => d - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="min-w-[140px] text-xs"
                onClick={() => setDateOffset(0)}
              >
                {formatDateLabel(targetDate)}
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDateOffset((d) => d + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex gap-1">
              {(["all", "vegetarian", "vegan"] as const).map((f) => (
                <Button
                  key={f}
                  variant={filter === f ? "default" : "outline"}
                  size="sm"
                  onClick={() => setFilter(f)}
                  className="gap-1 text-xs capitalize"
                >
                  {f === "vegan" && <Vegan className="h-3 w-3" />}
                  {f === "vegetarian" && <Leaf className="h-3 w-3" />}
                  {f}
                </Button>
              ))}
            </div>
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              Loading menu...
            </div>
          ) : dishes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <UtensilsCrossed className="mb-2 h-8 w-8" />
              <div className="font-medium">No menu available</div>
              <div className="mt-1 text-xs">
                {new Date(targetDate + "T12:00:00").getDay() === 0 || new Date(targetDate + "T12:00:00").getDay() === 6
                  ? "Mensa is closed on weekends"
                  : "No dishes found for this day — it may be a holiday"}
              </div>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {dishes.map((dish, i) => (
                <div key={i} className="rounded-lg border border-border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2">
                      <span className="text-lg leading-none mt-0.5">{dishEmoji(dish.name)}</span>
                      <div>
                        <div className="font-medium text-sm leading-snug">{dish.name}</div>
                        {dish.dish_type && (
                          <div className="mt-0.5 text-xs text-muted-foreground">{dish.dish_type}</div>
                        )}
                      </div>
                    </div>
                    <div className="shrink-0 font-mono text-xs font-semibold tabular-nums text-primary">
                      {dish.price}
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {dish.is_vegan && (
                      <Badge variant="secondary" className="bg-career-soft text-career font-normal">
                        vegan
                      </Badge>
                    )}
                    {dish.is_vegetarian && !dish.is_vegan && (
                      <Badge variant="secondary" className="bg-academic-soft text-academic font-normal">
                        vegetarian
                      </Badge>
                    )}
                    {dish.labels
                      .filter((l) => !["vegan", "vegetarian"].includes(l))
                      .slice(0, 4)
                      .map((l) => (
                        <Badge key={l} variant="secondary" className="font-normal capitalize text-[10px]">
                          {l}
                        </Badge>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
