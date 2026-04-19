"use client"

import * as React from "react"
import { Sheet, SheetContent } from "@/components/ui/sheet"
import { AppSidebar } from "@/components/app-sidebar"
import { Topbar } from "@/components/topbar"
import { ChatProvider } from "@/components/chat-context"
import { ChatDrawer } from "@/components/chat-drawer"
import { ActivityTicker } from "@/components/activity-ticker"

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = React.useState(false)

  return (
    <ChatProvider>
      <div className="flex min-h-screen">
        <div className="hidden md:block">
          <AppSidebar />
        </div>

        <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
          <SheetContent side="left" className="w-64 p-0">
            <AppSidebar onNavigate={() => setMobileNavOpen(false)} />
          </SheetContent>
        </Sheet>

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onToggleSidebar={() => setMobileNavOpen(true)} />
          <ActivityTicker />
          <main className="flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
        </div>

        <ChatDrawer />
      </div>
    </ChatProvider>
  )
}
