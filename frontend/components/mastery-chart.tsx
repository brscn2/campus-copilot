"use client"

import { Bar, BarChart, CartesianGrid, XAxis, YAxis, Cell } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { courses } from "@/lib/mock-data"

const config = {
  mastery: { label: "Mastery %", color: "var(--color-chart-1)" },
} satisfies ChartConfig

export function MasteryChart() {
  const data = courses.map((c) => ({ course: c.code, mastery: c.mastery, name: c.name }))

  return (
    <ChartContainer config={config} className="h-[220px] w-full">
      <BarChart data={data} layout="vertical" margin={{ left: 4, right: 24, top: 4, bottom: 4 }}>
        <CartesianGrid horizontal={false} strokeDasharray="3 3" className="stroke-border" />
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis
          dataKey="course"
          type="category"
          tickLine={false}
          axisLine={false}
          width={70}
          className="text-xs"
        />
        <ChartTooltip
          cursor={{ fill: "var(--color-muted)" }}
          content={<ChartTooltipContent labelKey="name" />}
        />
        <Bar dataKey="mastery" radius={[0, 6, 6, 0]}>
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={
                d.mastery >= 75
                  ? "var(--color-career)"
                  : d.mastery >= 55
                    ? "var(--color-chart-1)"
                    : "var(--color-chart-4)"
              }
            />
          ))}
        </Bar>
      </BarChart>
    </ChartContainer>
  )
}
