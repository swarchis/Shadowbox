import { motion } from 'framer-motion'
import { useMemo, type ReactNode } from 'react'
import { cx } from '../lib/format'
import { highlightLines, type Lang } from '../lib/highlight'

interface Props {
  code: string
  lang?: Lang
  title?: ReactNode
  right?: ReactNode
  accent?: string
  marks?: Set<number>
  markTone?: 'add' | 'del'
  maxHeight?: number | string
  active?: boolean
  className?: string
}

export function CodePane({ code, lang = 'verilog', title, right, accent = '#94a3b8', marks, markTone = 'add', maxHeight = 420, active = true, className }: Props) {
  const lines = useMemo(() => highlightLines(code ?? '', lang), [code, lang])
  const markColor = markTone === 'add' ? '52,211,153' : '251,113,133'
  return (
    <motion.div
      animate={{ opacity: active ? 1 : 0.55 }}
      transition={{ duration: 0.4 }}
      className={cx('glass flex min-w-0 flex-col overflow-hidden', className)}
      style={active ? { boxShadow: `0 0 0 1px ${accent}40, 0 0 50px -20px ${accent}80` } : undefined}
    >
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-white">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: accent, boxShadow: `0 0 8px ${accent}` }} />
            <span className="truncate">{title}</span>
          </div>
          {right}
        </div>
      )}
      <div className="overflow-auto py-3 font-mono text-[12.5px] leading-[1.65]" style={{ maxHeight }}>
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((toks, i) => {
              const marked = marks?.has(i)
              return (
                <tr key={i} style={marked ? { background: `rgba(${markColor},0.09)` } : undefined}>
                  <td
                    className="select-none whitespace-nowrap py-0 pl-4 pr-3 text-right align-top text-[11px] text-slate-600"
                    style={marked ? { boxShadow: `inset 2px 0 0 rgba(${markColor},0.9)`, color: `rgba(${markColor},0.9)` } : undefined}
                  >
                    {marked ? (markTone === 'add' ? '+' : '−') : i + 1}
                  </td>
                  <td className="whitespace-pre pr-6 text-slate-300">
                    {toks.length === 0 ? ' ' : toks.map((t, k) => (t.cls ? <span key={k} className={t.cls}>{t.text}</span> : <span key={k}>{t.text}</span>))}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </motion.div>
  )
}
