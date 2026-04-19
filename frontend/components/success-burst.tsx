import { toast } from "sonner"

const PARTICLES = [
  { angle: 0, color: "bg-primary" },
  { angle: 60, color: "bg-career" },
  { angle: 120, color: "bg-academic" },
  { angle: 180, color: "bg-primary" },
  { angle: 240, color: "bg-social" },
  { angle: 300, color: "bg-career" },
]

function toXY(angle: number, dist: number) {
  const rad = (angle * Math.PI) / 180
  return `translate(${Math.cos(rad) * dist}px, ${Math.sin(rad) * dist}px)`
}

function SuccessBurst({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 px-1 py-0.5">
      <div className="relative flex h-10 w-10 shrink-0 items-center justify-center">
        <span className="animate-burst-ring absolute inset-0 rounded-full border-2 border-primary" />
        {PARTICLES.map((p) => (
          <span
            key={p.angle}
            className={`animate-burst-particle absolute h-1.5 w-1.5 rounded-full ${p.color}`}
            style={{ "--particle-to": toXY(p.angle, 18) } as React.CSSProperties}
          />
        ))}
        <svg viewBox="0 0 24 24" className="relative h-5 w-5 text-primary" fill="none">
          <path
            d="M5 13l4 4L19 7"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="animate-burst-check"
            style={{ strokeDasharray: 24, strokeDashoffset: 24 }}
          />
        </svg>
      </div>
      <span className="text-sm font-medium">{message}</span>
    </div>
  )
}

export function successToast(message: string) {
  toast.custom(() => <SuccessBurst message={message} />, { duration: 3000 })
}
