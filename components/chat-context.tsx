"use client"

import * as React from "react"

type ChatContextValue = {
  open: boolean
  setOpen: (open: boolean) => void
  openWithPrompt: (prompt: string) => void
  initialPrompt: string | null
  consumeInitialPrompt: () => void
}

const ChatContext = React.createContext<ChatContextValue | null>(null)

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false)
  const [initialPrompt, setInitialPrompt] = React.useState<string | null>(null)

  const openWithPrompt = React.useCallback((prompt: string) => {
    setInitialPrompt(prompt)
    setOpen(true)
  }, [])

  const consumeInitialPrompt = React.useCallback(() => {
    setInitialPrompt(null)
  }, [])

  return (
    <ChatContext.Provider value={{ open, setOpen, openWithPrompt, initialPrompt, consumeInitialPrompt }}>
      {children}
    </ChatContext.Provider>
  )
}

export function useChat() {
  const ctx = React.useContext(ChatContext)
  if (!ctx) throw new Error("useChat must be used within ChatProvider")
  return ctx
}
