import type { ReactNode } from 'react'
import { Card } from './Card'
import { CountUp } from './CountUp'

interface Props {
  label: string
  value: number | null
  format?: (v: number) => string
  sub?: ReactNode
  color: string
  icon: ReactNode
  delay?: number
}

export function StatTile({ label, value, format, sub, color, icon, delay = 0 }: Props) {
  return (
    <Card className="group p-4 sm:p-5">
      <div
        className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-25 blur-2xl transition-opacity duration-500 group-hover:opacity-40"
        style={{ background: color }}
      />
      <div className="relative flex items-center justify-between">
        <span className="eyebrow">{label}</span>
        <span className="grid h-7 w-7 place-items-center rounded-lg border border-white/10 bg-white/[0.04]" style={{ color }}>
          {icon}
        </span>
      </div>
      <div className="relative mt-3 font-mono text-3xl font-semibold tracking-tight text-white sm:text-4xl">
        {value === null ? <span className="text-slate-600">–</span> : <CountUp value={value} format={format} delay={delay} />}
      </div>
      {sub && <div className="relative mt-1.5 text-xs text-slate-500">{sub}</div>}
    </Card>
  )
}
