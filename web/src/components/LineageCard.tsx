import { AnimatePresence, motion } from 'framer-motion'
import { BookMarked, Check, ChevronDown, FileText, ListPlus, ListX, MessageSquareText, SlidersHorizontal, Wrench, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { CHANGE_TYPE_LABEL, cx, money, pct, teamColor } from '../lib/format'
import type { ChangeType, LineageEntry } from '../types'
import { NetFlips, ProblemChip } from './Badges'

const TYPE_ICON: Record<ChangeType, ReactNode> = {
  prompt_edit: <MessageSquareText className="h-3 w-3" />,
  rule_add: <ListPlus className="h-3 w-3" />,
  rule_remove: <ListX className="h-3 w-3" />,
  tool_add: <Wrench className="h-3 w-3" />,
  tool_remove: <Wrench className="h-3 w-3" />,
  param: <SlidersHorizontal className="h-3 w-3" />,
  memory_add: <BookMarked className="h-3 w-3" />,
}

export function LineageCard({ e, onTool, index = 0 }: { e: LineageEntry; onTool?: (name: string) => void; index?: number }) {
  const [open, setOpen] = useState(false)
  const color = teamColor(e.team)
  const metric = e.team === 'builder' ? 'val pass' : 'pool catch'
  const delta = e.score_after !== null && e.score_before !== null ? e.score_after - e.score_before : null
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      whileInView={{ opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.5, delay: (index % 4) * 0.06, ease: [0.16, 1, 0.3, 1] }}
      className={cx('glass relative overflow-hidden pl-4', !e.accepted && 'opacity-[0.72] saturate-[0.6]')}
      style={e.accepted ? { boxShadow: `0 0 0 1px ${color}22, 0 20px 50px -30px ${color}66` } : undefined}
    >
      <span className="absolute inset-y-0 left-0 w-1" style={{ background: e.accepted ? color : `${color}55`, boxShadow: e.accepted ? `0 0 14px ${color}` : undefined }} />
      <div className="p-4 pl-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="chip border-white/10 bg-white/[0.04] text-slate-300">
            {TYPE_ICON[e.change_type] ?? <FileText className="h-3 w-3" />}
            {CHANGE_TYPE_LABEL[e.change_type] ?? (e.change_type ? e.change_type.replace(/_/g, ' ') : 'Change')}
          </span>
          {e.tool_name && (
            <button
              onClick={() => onTool?.(e.tool_name as string)}
              className="chip border-white/10 bg-white/[0.04] font-mono text-slate-200 hover:border-white/25"
              title="View tool source"
            >
              <Wrench className="h-3 w-3" style={{ color }} />
              {e.tool_name}
            </button>
          )}
          <span className="ml-auto flex items-center gap-1.5">
            {e.net_flips === null ? (
              <span className="chip border-white/10 bg-white/[0.03] text-slate-500" title="The proposal was invalid, so it was never gated">
                not gated
              </span>
            ) : (
              <NetFlips n={e.net_flips} />
            )}
            <span
              className={cx('chip font-semibold', e.accepted ? 'border-pass/30 bg-pass/10 text-pass' : 'border-white/10 bg-white/[0.03] text-slate-500')}
            >
              {e.accepted ? <Check className="h-3 w-3" strokeWidth={3} /> : <X className="h-3 w-3" strokeWidth={3} />}
              {e.accepted ? 'Kept' : 'Rejected'}
            </span>
          </span>
        </div>

        <h4
          className={cx(
            'mt-2.5 text-[15px] font-medium leading-snug',
            e.accepted ? 'text-white' : 'text-slate-400 line-through decoration-slate-600/70 decoration-1',
          )}
        >
          {e.summary}
        </h4>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-slate-500">
          <span>
            {metric} {pct(e.score_before, 1)} →{' '}
            <span className={delta === null ? '' : delta > 0 ? 'text-pass' : delta < 0 ? 'text-breaker' : ''}>{pct(e.score_after, 1)}</span>
          </span>
          <span>
            {e.accepted && e.new_version !== null ? (
              <>
                v{e.from_version} → <span style={{ color }}>v{e.new_version}</span>
              </>
            ) : (
              <>stays v{e.from_version}</>
            )}
          </span>
          <span>{money(e.cost_usd)}</span>
        </div>

        <button
          onClick={() => setOpen((o) => !o)}
          className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-slate-400 hover:text-white"
          aria-expanded={open}
        >
          <ChevronDown className={cx('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
          {open ? 'Hide' : 'Coach reasoning & evidence'}
        </button>

        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="overflow-hidden"
            >
              <div className="mt-3 space-y-3 border-t border-white/[0.06] pt-3">
                <p className="text-[13px] leading-relaxed text-slate-300">{e.reasoning}</p>
                {e.evidence_problems?.length > 0 && (
                  <ChipRow label="Evidence (train)">
                    {e.evidence_problems.map((p) => (
                      <ProblemChip key={p} id={p} />
                    ))}
                  </ChipRow>
                )}
                {e.gained?.length > 0 && (
                  <ChipRow label={`Gained (${e.gained.length})`}>
                    {e.gained.map((p) => (
                      <ProblemChip key={p} id={p} tone="gain" />
                    ))}
                  </ChipRow>
                )}
                {e.lost?.length > 0 && (
                  <ChipRow label={`Lost (${e.lost.length})`}>
                    {e.lost.map((p) => (
                      <ProblemChip key={p} id={p} tone="loss" />
                    ))}
                  </ChipRow>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.article>
  )
}

function ChipRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="flex flex-wrap gap-1">{children}</div>
    </div>
  )
}
