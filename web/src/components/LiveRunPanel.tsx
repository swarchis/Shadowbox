import { AnimatePresence, motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { Cpu, Hand, Timer } from 'lucide-react'
import { useData } from '../lib/DataContext'
import { PHASE_LABEL, STEP_LABEL, STEP_ORDER, cx, duration, money, stepIndex } from '../lib/format'
import { useNow } from '../lib/hooks'
import { Card, CardHeader } from './Card'
import { CountUp } from './CountUp'
import { EmptyState } from './EmptyState'
import { StatusPill } from './TopBar'

export function LiveRunPanel() {
  const { state } = useData()
  const now = useNow(1000)

  if (!state) {
    return (
      <Card className="p-5">
        <CardHeader eyebrow="Live run" title="Self-play engine" />
        <EmptyState compact title="Connecting to the engine..." />
      </Card>
    )
  }

  const running = state.status === 'running'
  const start = state.started_at ? Date.parse(state.started_at) : NaN
  const deadline = state.deadline_at ? Date.parse(state.deadline_at) : NaN
  const endRef = running ? now : state.updated_at ? Date.parse(state.updated_at) : now
  const hasBudget = Number.isFinite(start) && Number.isFinite(deadline) && deadline > start
  const timeFrac = hasBudget ? Math.min(1, Math.max(0, (endRef - start) / (deadline - start))) : null
  const remaining = hasBudget ? deadline - (running ? now : endRef) : null
  // step is null before the run and a non-round string ("baseline", "final", ...) outside rounds
  const stepIdx = stepIndex(state.step)
  const done = state.status === 'finished' || state.phase === 'done'
  const roundsOver = done || state.phase === 'final'
  const progress = state.status === 'idle' ? 0 : (timeFrac ?? (done ? 1 : stepIdx >= 0 ? (stepIdx + 1) / STEP_ORDER.length : 0))

  return (
    <Card className="flex h-full flex-col p-5" glow={running ? '#34d399' : undefined}>
      <CardHeader eyebrow="Live run" title={PHASE_LABEL[state.phase] ?? state.phase} right={<StatusPill compact />} />

      <div className="mt-4 flex items-baseline gap-2">
        <span className="font-mono text-5xl font-semibold tracking-tight text-white">
          <CountUp value={state.round} />
        </span>
        <span className="text-sm text-slate-500">{state.round === 1 ? 'round' : 'rounds'}</span>
      </div>

      {/* step tracker */}
      <div className="mt-4 grid grid-cols-5 gap-1" aria-label="Round steps">
        {STEP_ORDER.slice(0, 5).map((s, i) => {
          const isCur = s === state.step && !roundsOver
          const past = roundsOver || (stepIdx >= 0 && i < stepIdx)
          const team = s.startsWith('builder') ? '#38bdf8' : s.startsWith('breaker') ? '#fb7185' : '#cbd5e1'
          return (
            <div key={s} className="min-w-0">
              <div className="relative h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                {(past || isCur) && (
                  <motion.div
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{ background: team, boxShadow: isCur ? `0 0 12px ${team}` : undefined }}
                    initial={{ width: 0 }}
                    animate={{ width: past ? '100%' : '55%', opacity: isCur ? [0.6, 1, 0.6] : 1 }}
                    transition={isCur ? { width: { duration: 0.8 }, opacity: { duration: 1.6, repeat: Infinity } } : { duration: 0.6, delay: i * 0.06 }}
                  />
                )}
              </div>
              <div className={cx('mt-1.5 truncate text-[10px]', isCur ? 'text-white' : 'text-slate-500')}>{STEP_LABEL[s]}</div>
            </div>
          )
        })}
      </div>

      <div className="mt-4 min-h-[2.5rem] text-sm leading-relaxed text-slate-300">
        <AnimatePresence mode="wait">
          <motion.p key={state.message} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.3 }}>
            {state.message || <span className="text-slate-500">Waiting for the first round...</span>}
          </motion.p>
        </AnimatePresence>
      </div>

      <div className="mt-4">
        <div className="mb-1.5 flex items-center justify-between text-[11px] text-slate-500">
          <span>{hasBudget ? 'Time budget' : 'Progress'}</span>
          <span className="num">{Math.round(progress * 100)}%</span>
        </div>
        <div className="relative h-2 overflow-hidden rounded-full bg-white/[0.06]">
          <motion.div
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ background: `linear-gradient(90deg, #38bdf8, ${running ? '#34d399' : '#fb7185'})` }}
            initial={{ width: 0 }}
            animate={{ width: `${progress * 100}%` }}
            transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          />
          {running && (
            <div className="absolute inset-0 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.25),transparent)] bg-[length:50%_100%] bg-no-repeat motion-safe:animate-shimmer" />
          )}
        </div>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-2">
        <Metric icon={<Timer className="h-3.5 w-3.5" />} label={running ? 'Remaining' : done ? 'Ran for' : 'Remaining'}>
          {running
            ? remaining !== null
              ? duration(Math.max(0, remaining))
              : '–'
            : Number.isFinite(start)
              ? duration(endRef - start)
              : '–'}
        </Metric>
        <Metric icon={<Cpu className="h-3.5 w-3.5" />} label="LLM calls">
          <CountUp value={state.llm_calls} />
        </Metric>
        <Metric icon={<Hand className="h-3.5 w-3.5" />} label="Humans" highlight>
          <CountUp value={state.human_interventions} />
        </Metric>
      </div>
      <div className="mt-3 flex items-center justify-between rounded-xl border border-pass/20 bg-pass/[0.06] px-3 py-2 text-xs">
        <span className="flex items-center gap-2 text-pass">
          <span className="h-1.5 w-1.5 rounded-full bg-pass shadow-[0_0_8px_#34d399]" />
          <span className="num font-semibold">{state.human_interventions}</span> human interventions
        </span>
        <span className="num text-slate-500">{money(state.spend_usd)} spent</span>
      </div>
    </Card>
  )
}

function Metric({ icon, label, children, highlight }: { icon: ReactNode; label: string; children: ReactNode; highlight?: boolean }) {
  return (
    <div className={cx('rounded-xl border px-2.5 py-2', highlight ? 'border-pass/20 bg-pass/[0.05]' : 'border-white/[0.06] bg-white/[0.02]')}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        {icon}
        {label}
      </div>
      <div className={cx('num mt-1 text-base font-semibold', highlight ? 'text-pass' : 'text-white')}>{children}</div>
    </div>
  )
}
