import { motion } from 'framer-motion'
import { Play } from 'lucide-react'
import { useData } from '../lib/DataContext'
import { STATUS_LABEL, cx, money, statusColor, stepLabel } from '../lib/format'
import { DataBadge } from './Badges'
import { LogoMark, Wordmark } from './Logo'

export type TabId = 'overview' | 'match' | 'evolution' | 'final'

export const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'match', label: 'Live Match' },
  { id: 'evolution', label: 'Evolution' },
  { id: 'final', label: 'Final Exam' },
]

export function StatusPill({ compact = false }: { compact?: boolean }) {
  const { state } = useData()
  const status = state?.status ?? 'idle'
  const running = status === 'running'
  const color = statusColor(status)
  return (
    <div
      className="inline-flex items-center gap-2 whitespace-nowrap rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300"
      title={state?.message ?? ''}
    >
      <span className="relative flex h-2 w-2">
        {running && <span className="absolute inline-flex h-full w-full rounded-full motion-safe:animate-pulse-ring" style={{ background: color }} />}
        <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: color, boxShadow: `0 0 10px ${color}` }} />
      </span>
      <span className="font-medium text-white">{STATUS_LABEL[status] ?? status}</span>
      {!compact && state && state.round > 0 && (
        <>
          <span className="text-slate-600">·</span>
          <span className="num">R{state.round}</span>
          {state.step && state.step !== 'done' && (
            <>
              <span className="text-slate-600">·</span>
              <span className="text-slate-400">{stepLabel(state.step)}</span>
            </>
          )}
        </>
      )}
    </div>
  )
}

export function SpendMeter() {
  const { state } = useData()
  const spend = state?.spend_usd ?? 0
  const cap = state?.spend_cap_usd ?? 0
  const frac = cap > 0 ? Math.min(1, spend / cap) : 0
  const hot = frac > 0.85
  const warm = frac > 0.65
  return (
    <div className="flex items-center gap-2 text-xs" title="LLM spend against the hard cap">
      <div className="flex flex-col items-end leading-tight">
        <span className="num text-slate-200">
          {money(spend)}
          <span className="text-slate-500"> / {cap ? `$${cap.toFixed(0)}` : '–'}</span>
        </span>
        <div className="mt-1 h-1 w-20 overflow-hidden rounded-full bg-white/[0.07]">
          <motion.div
            className={cx('h-full rounded-full', hot ? 'bg-breaker' : warm ? 'bg-amber-300' : 'bg-pass')}
            initial={{ width: 0 }}
            animate={{ width: `${frac * 100}%` }}
            transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          />
        </div>
      </div>
    </div>
  )
}

/** `fill`: four equal columns that always fit the row (phones and tablets); otherwise a compact pill row. */
function Tabs({ tab, onTab, id, fill = false }: { tab: TabId; onTab: (t: TabId) => void; id: string; fill?: boolean }) {
  return (
    <nav className={fill ? 'w-full' : 'flex'} aria-label="Views">
      <div className={cx('rounded-xl border border-white/[0.06] bg-white/[0.02] p-1', fill ? 'grid w-full grid-cols-4 gap-0.5 sm:max-w-md' : 'flex gap-1')}>
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => onTab(t.id)}
            className={cx(
              'relative whitespace-nowrap rounded-lg font-medium transition-colors',
              fill ? 'px-1 py-1.5 text-[13px]' : 'px-3 py-1.5 text-sm',
              tab === t.id ? 'text-white' : 'text-slate-400 hover:text-slate-200',
            )}
            aria-current={tab === t.id ? 'page' : undefined}
          >
            {tab === t.id && (
              <motion.span
                layoutId={`tab-pill-${id}`}
                className="absolute inset-0 rounded-lg border border-white/10 bg-white/[0.08]"
                transition={{ type: 'spring', stiffness: 400, damping: 34 }}
              />
            )}
            <span className="relative">{t.label}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}

function DemoButton({ onDemo }: { onDemo: () => void }) {
  return (
    <motion.button
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      onClick={onDemo}
      className="group relative inline-flex shrink-0 items-center gap-2 overflow-hidden rounded-xl px-3.5 py-2 text-sm font-semibold text-white"
      style={{
        background: 'linear-gradient(135deg, rgba(56,189,248,0.9), rgba(251,113,133,0.9))',
        boxShadow: '0 0 0 1px rgba(255,255,255,0.15) inset, 0 10px 30px -10px rgba(251,113,133,0.6), 0 10px 30px -10px rgba(56,189,248,0.6)',
      }}
      title="Play the 60-second demo (→ next, ← back, P pause, Esc exit)"
    >
      <span className="absolute inset-0 bg-[linear-gradient(110deg,transparent_25%,rgba(255,255,255,0.35)_50%,transparent_75%)] bg-[length:200%_100%] opacity-0 transition-opacity group-hover:opacity-100 motion-safe:animate-shimmer" />
      <Play className="relative h-3.5 w-3.5 fill-white" />
      <span className="relative">Demo</span>
    </motion.button>
  )
}

export function TopBar({ tab, onTab, onDemo }: { tab: TabId; onTab: (t: TabId) => void; onDemo: () => void }) {
  const { state, source } = useData()
  const badges = (compact: boolean) => (
    <div className="flex items-center gap-1.5">
      {state?.mode === 'mock' && <DataBadge kind="mock" compact={compact} />}
      {source === 'fixtures' && <DataBadge kind="fixtures" compact={compact} />}
      {source === 'offline' && <DataBadge kind="offline" compact={compact} />}
    </div>
  )
  const brand = (
    <button onClick={() => onTab('overview')} className="flex shrink-0 items-center gap-2.5" aria-label="Shadowbox home">
      <LogoMark size={28} />
      <Wordmark className="text-sm" />
    </button>
  )
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-[#07080c]/75 backdrop-blur-xl">
      {/* desktop */}
      <div className="mx-auto hidden max-w-[1400px] items-center gap-4 px-6 py-3 xl:flex">
        {brand}
        {badges(false)}
        <div className="ml-2">
          <Tabs tab={tab} onTab={onTab} id="lg" />
        </div>
        <div className="ml-auto flex items-center gap-3">
          <StatusPill />
          <SpendMeter />
          <DemoButton onDemo={onDemo} />
        </div>
      </div>
      {/* mobile / tablet */}
      <div className="mx-auto max-w-[1400px] space-y-2 px-4 py-2.5 sm:px-6 xl:hidden">
        <div className="flex items-center gap-3">
          {brand}
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden sm:block">
              <SpendMeter />
            </div>
            <DemoButton onDemo={onDemo} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          {badges(true)}
          <div className="ml-auto">
            <StatusPill compact />
          </div>
        </div>
        <Tabs tab={tab} onTab={onTab} id="sm" fill />
      </div>
    </header>
  )
}
