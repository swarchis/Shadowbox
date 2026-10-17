import { motion } from 'framer-motion'
import { Bug } from 'lucide-react'
import { useState } from 'react'
import { useData } from '../lib/DataContext'
import { cx } from '../lib/format'
import type { MatchProblem } from '../types'
import { Card, CardHeader } from './Card'
import { EmptyState } from './EmptyState'

function classify(p: MatchProblem): 'pass' | 'subtle' | 'fail' {
  if (!p.official?.passed) return 'fail'
  if (p.attack?.valid_bug) return 'subtle'
  return 'pass'
}

export function MatchGrid() {
  const { latestMatch } = useData()
  const [hover, setHover] = useState<MatchProblem | null>(null)

  if (!latestMatch || !latestMatch.problems?.length) {
    return (
      <Card className="p-5">
        <CardHeader eyebrow="Latest match" title="Builder vs Breaker, problem by problem" />
        <EmptyState compact />
      </Card>
    )
  }
  const s = latestMatch.summary
  // summary fields are null until the engine writes them: count from the problem list instead
  const total = s?.problems ?? latestMatch.problems.length
  const passed = s?.train_pass != null ? Math.round(s.train_pass * total) : latestMatch.problems.filter((p) => p.official?.passed).length
  const bugs = s?.bugs_found ?? latestMatch.problems.filter((p) => p.attack?.valid_bug).length
  const subtle = s?.subtle_bugs ?? latestMatch.problems.filter((p) => p.official?.passed && p.attack?.valid_bug).length
  const vs = (n: number | null) => (typeof n === 'number' ? `v${n}` : '')
  const shown = hover ?? latestMatch.problems.find((p) => classify(p) === 'subtle') ?? latestMatch.problems[0]
  const kind = classify(shown)

  return (
    <Card className="p-5">
      <CardHeader
        eyebrow={`Round ${latestMatch.round} match · Builder ${vs(latestMatch.builder_version)} vs Breaker ${vs(latestMatch.breaker_version)}`.replace(/ +/g, ' ')}
        title="Every train problem, one tile each"
        right={
          <div className="hidden items-center gap-3 text-[11px] text-slate-400 sm:flex">
            <Legend className="bg-pass/70" label="pass" />
            <Legend className="bg-amber-300/80" label="passed tests, Breaker found a bug" />
            <Legend className="bg-breaker/70" label="fail" />
          </div>
        }
      />
      <div className="mt-4 grid gap-5 md:grid-cols-[1fr_260px]">
        <motion.div
          className="grid content-start gap-1.5 [grid-template-columns:repeat(auto-fill,minmax(34px,1fr))]"
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.018 } } }}
          onMouseLeave={() => setHover(null)}
        >
          {latestMatch.problems.map((p) => {
            const k = classify(p)
            return (
              <motion.button
                key={p.problem_id}
                variants={{ hidden: { opacity: 0, scale: 0.6 }, show: { opacity: 1, scale: 1 } }}
                onMouseEnter={() => setHover(p)}
                onFocus={() => setHover(p)}
                onClick={() => setHover(p)}
                className={cx(
                  'relative aspect-square rounded-md border transition-transform hover:z-10 hover:scale-110',
                  k === 'pass' && 'border-pass/40 bg-pass/25',
                  k === 'subtle' && 'border-amber-300/50 bg-amber-300/25',
                  k === 'fail' && 'border-breaker/40 bg-breaker/25',
                  shown.problem_id === p.problem_id && 'ring-2 ring-white/60',
                )}
                aria-label={`${p.problem_id}: ${k}`}
              >
                {p.attack?.valid_bug && <Bug className="absolute inset-0 m-auto h-3 w-3 text-white/70" />}
              </motion.button>
            )
          })}
        </motion.div>
        <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3 text-xs">
          <div className="truncate font-mono text-[12px] text-white">{shown.problem_id}</div>
          <div
            className={cx(
              'mt-1 font-medium',
              kind === 'pass' && 'text-pass',
              kind === 'subtle' && 'text-amber-300',
              kind === 'fail' && 'text-breaker',
            )}
          >
            {kind === 'pass' ? 'Passed, Breaker found nothing' : kind === 'subtle' ? 'Passed the official tests, but the Breaker found a real bug' : `Failed (${shown.official?.kind ?? 'mismatch'})`}
          </div>
          {shown.attack?.first_mismatch && (
            <div className="mt-2 space-y-0.5 font-mono text-[11px] text-slate-400">
              <div>
                cycle {shown.attack.first_mismatch.cycle} · {shown.attack.first_mismatch.signal}
              </div>
              <div>
                expected <span className="text-pass">{shown.attack.first_mismatch.expected}</span> got{' '}
                <span className="text-breaker">{shown.attack.first_mismatch.got}</span>
              </div>
            </div>
          )}
          <div className="mt-2 text-slate-500">
            {shown.build?.attempts ?? 1} attempt{(shown.build?.attempts ?? 1) === 1 ? '' : 's'}
            {shown.build?.tool_reports?.some((t) => t.fired) && ' · lint fired'}
          </div>
          <div className="mt-3 grid grid-cols-3 gap-1.5 border-t border-white/[0.06] pt-3 text-center">
            <Mini label="pass" value={`${passed}/${total}`} color="#34d399" />
            <Mini label="bugs" value={String(bugs)} color="#fb7185" />
            <Mini label="subtle" value={String(subtle)} color="#fcd34d" />
          </div>
        </div>
      </div>
    </Card>
  )
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cx('h-2.5 w-2.5 rounded-sm', className)} />
      {label}
    </span>
  )
}

function Mini({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div className="num text-sm font-semibold" style={{ color }}>
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
    </div>
  )
}
