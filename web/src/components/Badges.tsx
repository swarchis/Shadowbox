import { Check, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { cx } from '../lib/format'
import type { Team } from '../types'

const BADGES = {
  mock: { style: 'border-amber-400/30 bg-amber-400/10 text-amber-300', dot: 'bg-amber-300', short: 'Mock', long: 'Mock data',
          title: 'The engine is running in mock mode: no real LLM calls, numbers are meaningless' },
  fixtures: { style: 'border-violet-400/30 bg-violet-400/10 text-violet-300', dot: 'bg-violet-300', short: 'Fixtures', long: 'Fixture data',
              title: '?fixtures=1: showing bundled sample data, not a real run' },
  offline: { style: 'border-rose-400/30 bg-rose-400/10 text-rose-300', dot: 'bg-rose-300 animate-pulse', short: 'Offline', long: 'API offline · retrying',
             title: 'Cannot reach the Shadowbox API. Showing the last data received; retrying every few seconds.' },
} as const

export function DataBadge({ kind, compact = false }: { kind: keyof typeof BADGES; compact?: boolean }) {
  const b = BADGES[kind]
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider',
        b.style,
      )}
      title={b.title}
    >
      <span className={cx('h-1.5 w-1.5 rounded-full', b.dot)} />
      {compact ? b.short : b.long}
    </span>
  )
}

export function TeamDot({ team, className }: { team: Team | null | undefined; className?: string }) {
  return (
    <span
      className={cx('inline-block h-2 w-2 shrink-0 rounded-full', team === 'breaker' ? 'bg-breaker' : team === 'builder' ? 'bg-builder' : 'bg-slate-500', className)}
    />
  )
}

export function TeamChip({ team }: { team: Team }) {
  return (
    <span
      className={cx(
        'chip',
        team === 'builder' ? 'border-builder/30 bg-builder/10 text-builder' : 'border-breaker/30 bg-breaker/10 text-breaker',
      )}
    >
      <TeamDot team={team} className="h-1.5 w-1.5" />
      {team === 'builder' ? 'Builder' : 'Breaker'}
    </span>
  )
}

export function NetFlips({ n, size = 'sm' }: { n: number; size?: 'sm' | 'lg' }) {
  const pos = n > 0
  const zero = n === 0
  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full border font-mono font-semibold tabular-nums',
        size === 'lg' ? 'px-2.5 py-1 text-sm' : 'px-2 py-0.5 text-xs',
        pos ? 'border-pass/30 bg-pass/10 text-pass' : zero ? 'border-white/10 bg-white/5 text-slate-400' : 'border-breaker/30 bg-breaker/10 text-breaker',
      )}
      title="Net problems flipped on the gate"
    >
      {pos ? '+' : ''}
      {n}
    </span>
  )
}

export function ProblemChip({ id, tone = 'neutral' }: { id: string; tone?: 'gain' | 'loss' | 'neutral' }) {
  return (
    <span
      className={cx(
        'inline-flex max-w-full items-center truncate rounded-md border px-1.5 py-0.5 font-mono text-[11px]',
        tone === 'gain' && 'border-pass/25 bg-pass/[0.08] text-pass-soft',
        tone === 'loss' && 'border-breaker/25 bg-breaker/[0.08] text-breaker-soft',
        tone === 'neutral' && 'border-white/10 bg-white/[0.04] text-slate-300',
      )}
    >
      {id}
    </span>
  )
}

export function Verdict({ pass, size = 'md', children }: { pass: boolean; size?: 'md' | 'lg'; children?: ReactNode }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full border font-semibold uppercase tracking-wider',
        size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2 py-0.5 text-[11px]',
        pass ? 'border-pass/40 bg-pass/10 text-pass' : 'border-breaker/40 bg-breaker/10 text-breaker',
      )}
    >
      {pass ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
      {children ?? (pass ? 'Pass' : 'Fail')}
    </span>
  )
}
