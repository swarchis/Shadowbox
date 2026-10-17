import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  Bug,
  Flag,
  GraduationCap,
  Lightbulb,
  Rocket,
  ShieldCheck,
  ShieldX,
  Sparkles,
  Swords,
  TriangleAlert,
  Trophy,
  Wrench,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useData } from '../lib/DataContext'
import { clockTime, teamColor } from '../lib/format'
import type { RunEvent } from '../types'
import { Card, CardHeader } from './Card'
import { EmptyState } from './EmptyState'

/**
 * Gate verdict. The engine adds an `accepted` flag to gate_result events (not in the contract) and
 * words its messages "Builder change rejected: ..." / "Builder v2 accepted: ..."; the contract example
 * is "Accepted: +4 net". Prefer the flag, else look for the word anywhere in the message.
 */
function rejected(e: RunEvent): boolean {
  const flag = (e as RunEvent & { accepted?: unknown }).accepted
  if (typeof flag === 'boolean') return !flag
  return /\brejected\b/i.test(e.message) && !/\baccepted\b/i.test(e.message)
}

const WARN_TYPES = new Set(['time_budget', 'hard_stop', 'spend_cap', 'proposal_invalid', 'llm_retry'])

function iconFor(e: RunEvent): ReactNode {
  const cls = 'h-3.5 w-3.5'
  switch (e.type) {
    case 'run_start':
      return <Rocket className={cls} />
    case 'baseline':
      return <Flag className={cls} />
    case 'bug_pool':
      return <Bug className={cls} />
    case 'round_start':
    case 'match_start':
    case 'match_done':
    case 'round_done':
      return <Swords className={cls} />
    case 'proposal':
      return <Lightbulb className={cls} />
    case 'gate_result':
      return rejected(e) ? <ShieldX className={cls} /> : <ShieldCheck className={cls} />
    case 'tool_born':
      return <Wrench className={cls} />
    case 'final_start':
    case 'final_step':
      return <GraduationCap className={cls} />
    case 'final_result':
    case 'final_done':
      return <Trophy className={cls} />
    case 'run_done':
      return <Sparkles className={cls} />
    case 'error':
      return <TriangleAlert className={cls} />
    default:
      return WARN_TYPES.has(e.type) ? <TriangleAlert className={cls} /> : <Activity className={cls} />
  }
}

function tone(e: RunEvent): string {
  if (e.type === 'gate_result') return rejected(e) ? '#64748b' : '#34d399'
  if (e.type === 'error') return '#fb7185'
  if (WARN_TYPES.has(e.type)) return '#fbbf24'
  if (e.type === 'final_result' || e.type === 'final_done' || e.type === 'run_done') return '#fbbf24'
  return teamColor(e.team)
}

export function EventFeed({ maxHeight = 420 }: { maxHeight?: number }) {
  const { events, state } = useData()
  const live = state?.status === 'running'
  return (
    <Card className="flex h-full flex-col p-5">
      <CardHeader
        eyebrow="Event feed"
        title="What the agents just did"
        right={
          <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <span className={`h-1.5 w-1.5 rounded-full ${live ? 'bg-pass shadow-[0_0_8px_#34d399] motion-safe:animate-pulse' : 'bg-slate-600'}`} />
            {live ? 'live' : `${events.length} events`}
          </span>
        }
      />
      <div className="relative mt-4 min-h-0 flex-1 overflow-y-auto pr-1" style={{ maxHeight }}>
        {events.length === 0 ? (
          <EmptyState compact title="Waiting for the first round..." hint="Events stream in as the coaches propose changes and the gatekeeper rules on them." />
        ) : (
          <ul className="relative space-y-1.5">
            <AnimatePresence initial={true}>
              {events.map((e, i) => {
                const c = tone(e)
                return (
                  <motion.li
                    key={e.seq}
                    layout
                    initial={{ opacity: 0, x: -12, scale: 0.98 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.35, delay: Math.min(i, 12) * 0.03, ease: [0.16, 1, 0.3, 1] }}
                    className="group flex gap-3 rounded-xl border border-transparent px-2 py-2 transition-colors hover:border-white/[0.06] hover:bg-white/[0.02]"
                  >
                    <span
                      className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg border"
                      style={{ color: c, borderColor: `${c}33`, background: `${c}14` }}
                    >
                      {iconFor(e)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] leading-snug text-slate-200">{e.message}</p>
                      <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-slate-500">
                        <span>{clockTime(e.ts)}</span>
                        {e.round !== null && e.round !== undefined && e.round > 0 && <span>R{e.round}</span>}
                        <span className="opacity-60">#{e.seq}</span>
                      </div>
                    </div>
                  </motion.li>
                )
              })}
            </AnimatePresence>
          </ul>
        )}
      </div>
      <div className="pointer-events-none absolute inset-x-5 bottom-5 h-8 bg-gradient-to-t from-[#0b0c11] to-transparent" />
    </Card>
  )
}
