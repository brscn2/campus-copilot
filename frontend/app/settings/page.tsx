"use client"

import { PageHeader } from "@/components/page-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { user } from "@/lib/mock-data"
import { Check } from "lucide-react"

const connections = [
  { name: "TUMonline", status: "connected", desc: "Grades, exams, enrolment" },
  { name: "Moodle", status: "connected", desc: "Slides, assignments, forums" },
  { name: "ZHS Portal", status: "connected", desc: "Sports bookings" },
  { name: "GitHub", status: "connected", desc: "Projects for your profile" },
  { name: "Google Calendar", status: "connected", desc: "Two-way sync" },
  { name: "Matrix / WhatsApp", status: "pending", desc: "For social coordination" },
]

const autonomy = [
  { key: "auto-summarize", label: "Auto-summarize new slides", desc: "Generate summaries and flashcards when Moodle updates", on: true },
  { key: "auto-book-zhs", label: "Auto-book ZHS slots", desc: "Book when watched slots open", on: true },
  { key: "auto-send-email", label: "Auto-send outreach emails", desc: "Skip human review for drafts", on: false },
  { key: "auto-reschedule", label: "Auto-resolve calendar conflicts", desc: "Apply priority rules silently", on: true },
]

export default function SettingsPage() {
  return (
    <div>
      <PageHeader title="Settings" description="Profile, connections, and agent autonomy." />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Profile</CardTitle>
            <CardDescription>Pulled from TUMonline</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <Avatar className="h-14 w-14">
                <AvatarFallback className="bg-primary text-primary-foreground text-sm font-semibold">
                  {user.initials}
                </AvatarFallback>
              </Avatar>
              <div>
                <div className="font-medium">{user.name}</div>
                <div className="text-xs text-muted-foreground">
                  {user.program} — {user.semester}
                </div>
              </div>
            </div>
            <div className="mt-4 space-y-3">
              <div>
                <Label htmlFor="email" className="text-xs">Email</Label>
                <Input id="email" defaultValue={user.email} className="mt-1" />
              </div>
              <div>
                <Label htmlFor="matrikel" className="text-xs">Matriculation</Label>
                <Input id="matrikel" defaultValue="03712845" className="mt-1" />
              </div>
            </div>
            <Button className="mt-4 w-full">Save profile</Button>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Connections</CardTitle>
            <CardDescription>Services your agents can access</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border">
              {connections.map((c) => (
                <li key={c.name} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                  <div>
                    <div className="text-sm font-medium">{c.name}</div>
                    <div className="text-xs text-muted-foreground">{c.desc}</div>
                  </div>
                  {c.status === "connected" ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-career-soft px-2 py-0.5 text-xs font-medium text-career">
                      <Check className="h-3 w-3" />
                      Connected
                    </span>
                  ) : (
                    <Button size="sm" variant="outline">Connect</Button>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">Agent autonomy</CardTitle>
            <CardDescription>Decide what happens without your approval</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-3 sm:grid-cols-2">
              {autonomy.map((a) => (
                <li
                  key={a.key}
                  className="flex items-center justify-between rounded-lg border border-border p-3"
                >
                  <div className="min-w-0 pr-3">
                    <div className="text-sm font-medium">{a.label}</div>
                    <div className="text-xs text-muted-foreground">{a.desc}</div>
                  </div>
                  <Switch defaultChecked={a.on} />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
