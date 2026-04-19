"use client"

import { useEffect, useState } from "react"
import { PageHeader } from "@/components/page-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Check, Loader2 } from "lucide-react"
import { fetchTumStudent, getProfile, saveProfile, type ProfileFormData } from "@/lib/api"

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

const EMPTY_FORM: ProfileFormData = {
  first_name: "",
  last_name: "",
  email: "",
  program: "",
  semester: 1,
  matriculation_number: "",
}

export default function SettingsPage() {
  const [tumUsername, setTumUsername] = useState("")
  const [form, setForm] = useState<ProfileFormData>(EMPTY_FORM)
  const [fetching, setFetching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fetchError, setFetchError] = useState("")
  const [saveStatus, setSaveStatus] = useState<"idle" | "success" | "error">("idle")

  useEffect(() => {
    getProfile()
      .then(setForm)
      .catch(() => {})
  }, [])

  async function handleFetchTum() {
    if (!tumUsername.match(/^[a-z]{2}[0-9]{2}[a-z]{3}$/)) {
      setFetchError("Username must be 7 characters (e.g. go93wis)")
      return
    }
    setFetching(true)
    setFetchError("")
    try {
      const data = await fetchTumStudent(tumUsername)
      setForm((prev) => ({
        ...prev,
        first_name: data.firstname,
        last_name: data.lastname,
        email: data.email,
        matriculation_number: data.matriculation_number,
        program: data.program || prev.program,
      }))
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : "Failed to fetch from TUMonline")
    } finally {
      setFetching(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    setSaveStatus("idle")
    try {
      await saveProfile(form)
      setSaveStatus("success")
      setTimeout(() => setSaveStatus("idle"), 2000)
    } catch {
      setSaveStatus("error")
    } finally {
      setSaving(false)
    }
  }

  function updateField(field: keyof ProfileFormData, value: string | number) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  return (
    <div>
      <PageHeader title="Settings" description="Profile, connections, and agent autonomy." />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Profile</CardTitle>
            <CardDescription>Auto-fill from TUMonline or enter manually</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div>
                <Label htmlFor="tum-username" className="text-xs">TUM Username</Label>
                <div className="mt-1 flex gap-2">
                  <Input
                    id="tum-username"
                    placeholder="go93wis"
                    maxLength={7}
                    value={tumUsername}
                    onChange={(e) => setTumUsername(e.target.value.toLowerCase())}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    disabled={fetching || tumUsername.length !== 7}
                    onClick={handleFetchTum}
                  >
                    {fetching ? <Loader2 className="h-4 w-4 animate-spin" /> : "Fetch"}
                  </Button>
                </div>
                {fetchError && (
                  <p className="mt-1 text-xs text-destructive">{fetchError}</p>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label htmlFor="first-name" className="text-xs">First name</Label>
                  <Input
                    id="first-name"
                    value={form.first_name}
                    onChange={(e) => updateField("first_name", e.target.value)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="last-name" className="text-xs">Last name</Label>
                  <Input
                    id="last-name"
                    value={form.last_name}
                    onChange={(e) => updateField("last_name", e.target.value)}
                    className="mt-1"
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="email" className="text-xs">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={form.email}
                  onChange={(e) => updateField("email", e.target.value)}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="program" className="text-xs">Program</Label>
                <Input
                  id="program"
                  value={form.program}
                  onChange={(e) => updateField("program", e.target.value)}
                  className="mt-1"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label htmlFor="semester" className="text-xs">Semester</Label>
                  <Input
                    id="semester"
                    type="number"
                    min={1}
                    max={20}
                    value={form.semester}
                    onChange={(e) => updateField("semester", parseInt(e.target.value, 10) || 1)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="matrikel" className="text-xs">Matriculation</Label>
                  <Input
                    id="matrikel"
                    value={form.matriculation_number}
                    onChange={(e) => updateField("matriculation_number", e.target.value)}
                    className="mt-1"
                  />
                </div>
              </div>
            </div>
            <Button className="mt-4 w-full" disabled={saving} onClick={handleSave}>
              {saving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : saveStatus === "success" ? (
                <Check className="mr-2 h-4 w-4" />
              ) : null}
              {saveStatus === "success" ? "Saved" : "Save profile"}
            </Button>
            {saveStatus === "error" && (
              <p className="mt-2 text-center text-xs text-destructive">Failed to save profile</p>
            )}
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
