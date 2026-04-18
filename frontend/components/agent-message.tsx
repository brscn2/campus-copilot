"use client"

import * as React from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"

import { cn } from "@/lib/utils"

const components: Components = {
  p: ({ className, ...props }) => (
    <p
      className={cn("leading-relaxed [&:not(:first-child)]:mt-2", className)}
      {...props}
    />
  ),
  ul: ({ className, ...props }) => (
    <ul
      className={cn(
        "my-1 list-disc space-y-0.5 pl-4 [&:not(:first-child)]:mt-2",
        className,
      )}
      {...props}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      className={cn(
        "my-1 list-decimal space-y-0.5 pl-4 [&:not(:first-child)]:mt-2",
        className,
      )}
      {...props}
    />
  ),
  li: ({ className, ...props }) => (
    <li className={cn("leading-relaxed", className)} {...props} />
  ),
  strong: ({ className, ...props }) => (
    <strong className={cn("font-semibold", className)} {...props} />
  ),
  em: ({ className, ...props }) => (
    <em className={cn("italic", className)} {...props} />
  ),
  code: ({ className, children, ...props }) => {
    const isInline = !/\n/.test(String(children ?? ""))
    if (isInline) {
      return (
        <code
          className={cn(
            "rounded bg-foreground/10 px-1 py-0.5 font-mono text-[0.85em]",
            className,
          )}
          {...props}
        >
          {children}
        </code>
      )
    }
    return (
      <code className={cn("font-mono text-xs", className)} {...props}>
        {children}
      </code>
    )
  },
  pre: ({ className, ...props }) => (
    <pre
      className={cn(
        "my-2 overflow-x-auto rounded-md bg-foreground/10 p-2 text-xs",
        className,
      )}
      {...props}
    />
  ),
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn(
        "my-2 border-l-2 border-primary/40 pl-2 text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => (
    <hr className={cn("my-2 border-border", className)} {...props} />
  ),
  a: ({ className, ...props }) => (
    <a
      className={cn(
        "underline underline-offset-2 hover:text-primary",
        className,
      )}
      target="_blank"
      rel="noreferrer"
      {...props}
    />
  ),
  h1: ({ className, ...props }) => (
    <h1
      className={cn("mt-2 text-base font-semibold", className)}
      {...props}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      className={cn("mt-2 text-sm font-semibold", className)}
      {...props}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3
      className={cn("mt-2 text-sm font-semibold", className)}
      {...props}
    />
  ),
  h4: ({ className, ...props }) => (
    <h4
      className={cn("mt-2 text-sm font-semibold", className)}
      {...props}
    />
  ),
  table: ({ className, ...props }) => (
    <div className="my-2 overflow-x-auto">
      <table
        className={cn("w-full border-collapse text-xs", className)}
        {...props}
      />
    </div>
  ),
  th: ({ className, ...props }) => (
    <th
      className={cn(
        "border border-border bg-muted/50 px-2 py-1 text-left font-semibold",
        className,
      )}
      {...props}
    />
  ),
  td: ({ className, ...props }) => (
    <td
      className={cn("border border-border px-2 py-1", className)}
      {...props}
    />
  ),
}

export function AgentMessage({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  )
}
