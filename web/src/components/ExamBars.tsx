import { motion, useReducedMotion } from 'framer-motion'
import { cx, pts } from '../lib/format'
import type { FinalMetric } from '../types'
import { CountUp } from './CountUp'

export interface BarSpec {
  key: string
  metric: FinalMetric
  fill: string
  glow: string
  sub?: string
}

const pctFmt = (v: number) => `${(v * 100).toFixed(1)}%`

/** Vertical bars with 95% CI whiskers, growing in sequence with count-up labels. */
export function ExamBars({
  bars,
  height = 320,
  size = 'md',
  stepDelay = 0.45,
  startDelay = 0.2,
  showDeltas = true,
}: {
  bars: BarSpec[]
  height?: number
  size?: 'md' | 'xl'
  stepDelay?: number
  startDelay?: number
  showDeltas?: boolean
}) {
  const reduce = useReducedMotion()
  const xl = size === 'xl'
  const maxV = Math.max(0.5, ...bars.map((b) => Math.max(b.metric.pass, b.metric.ci?.[1] ?? 0)))
  const top = Math.min(1, Math.ceil((maxV + 0.08) * 10) / 10)
  const y = (v: number) => (1 - v / top) * height
  const ticks = [0, 0.25, 0.5, 0.75, 1].filter((t) => t <= top + 1e-9)

  return (
    <div className="relative w-full">
      <div className="relative" style={{ height }}>
        {/* grid */}
        {ticks.map((t) => (
          <div key={t} className="absolute inset-x-0 flex items-center" style={{ top: y(t) }}>
            <span className={cx('num -translate-y-1/2 pr-2 text-right text-slate-500', xl ? 'w-14 text-sm' : 'w-10 text-[10px]')}>{Math.round(t * 100)}%</span>
            <span className={cx('h-px flex-1 -translate-y-1/2', t === 0 ? 'bg-white/[0.12]' : 'bg-white/[0.045]')} />
          </div>
        ))}
        <div className={cx('absolute inset-y-0 right-0 flex items-end justify-around', xl ? 'left-14 gap-10' : 'left-10 gap-4 sm:gap-8')}>
          {bars.map((b, i) => {
            const delay = startDelay + i * stepDelay
            const h = (b.metric.pass / top) * height
            const ci = b.metric.ci
            return (
              <div key={b.key} className="relative flex h-full min-w-0 flex-1 flex-col items-center justify-end" style={{ maxWidth: xl ? 260 : 150 }}>
                {/* value label */}
                <motion.div
                  className={cx('num absolute font-semibold text-white', xl ? 'text-6xl' : 'text-2xl sm:text-3xl')}
                  style={{ bottom: h + (ci ? Math.max(0, (ci[1] - b.metric.pass) / top) * height : 0) + (xl ? 22 : 12), textShadow: `0 0 30px ${b.glow}` }}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: reduce ? 0 : delay + 0.2, duration: 0.4 }}
                >
                  <CountUp value={b.metric.pass} format={pctFmt} delay={reduce ? 0 : delay} duration={1.3} />
                </motion.div>
                {/* bar */}
                <motion.div
                  className="relative w-full overflow-hidden rounded-t-xl"
                  style={{ background: b.fill, boxShadow: `0 0 50px -10px ${b.glow}, inset 0 1px 0 rgba(255,255,255,0.35)` }}
                  initial={{ height: reduce ? h : 0 }}
                  animate={{ height: h }}
                  transition={{ delay: reduce ? 0 : delay, duration: 1.3, ease: [0.16, 1, 0.3, 1] }}
                >
                  <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.18),transparent_40%)]" />
                  {/* one highlight sweeps up the bar as it lands */}
                  {!reduce && (
                    <motion.div
                      className="pointer-events-none absolute inset-x-0 h-1/3 bg-[linear-gradient(180deg,transparent,rgba(255,255,255,0.28),transparent)]"
                      initial={{ top: '110%' }}
                      animate={{ top: '-40%' }}
                      transition={{ delay: delay + 0.9, duration: 0.9, ease: 'easeInOut' }}
                    />
                  )}
                </motion.div>
                {/* CI whisker */}
                {ci && (
                  <motion.div
                    className="pointer-events-none absolute left-1/2 -translate-x-1/2"
                    style={{ bottom: (ci[0] / top) * height, height: ((ci[1] - ci[0]) / top) * height, width: xl ? 40 : 24 }}
                    initial={{ opacity: 0, scaleY: 0 }}
                    animate={{ opacity: 1, scaleY: 1 }}
                    transition={{ delay: reduce ? 0 : delay + 1.0, duration: 0.4 }}
                    title={`95% CI ${pctFmt(ci[0])} – ${pctFmt(ci[1])}`}
                  >
                    <span className="absolute inset-x-0 top-0 h-[2px] rounded bg-white/80" />
                    <span className="absolute bottom-0 left-1/2 top-0 w-[2px] -translate-x-1/2 bg-white/70" />
                    <span className="absolute inset-x-0 bottom-0 h-[2px] rounded bg-white/80" />
                  </motion.div>
                )}
                {/* delta from previous */}
                {showDeltas && i > 0 && (
                  <motion.div
                    className={cx(
                      'absolute z-10 -translate-x-1/2 rounded-full border font-mono font-semibold',
                      xl ? '-left-5 px-3 py-1 text-lg' : '-left-2 px-2 py-0.5 text-[11px] sm:-left-4',
                      b.metric.pass >= bars[i - 1].metric.pass ? 'border-pass/40 bg-[#07130e] text-pass' : 'border-breaker/40 bg-[#14070a] text-breaker',
                    )}
                    style={{ bottom: Math.max(h, (bars[i - 1].metric.pass / top) * height) / 2 }}
                    initial={{ opacity: 0, scale: 0.6 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: reduce ? 0 : delay + 1.1, type: 'spring', stiffness: 300, damping: 18 }}
                  >
                    {pts(b.metric.pass - bars[i - 1].metric.pass)}
                  </motion.div>
                )}
              </div>
            )
          })}
        </div>
      </div>
      {/* labels */}
      <div className={cx('flex justify-around', xl ? 'ml-14 mt-5 gap-10' : 'ml-10 mt-3 gap-4 sm:gap-8')}>
        {bars.map((b, i) => (
          <motion.div
            key={b.key}
            className="min-w-0 flex-1 text-center"
            style={{ maxWidth: xl ? 260 : 150 }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: reduce ? 0 : startDelay + i * stepDelay }}
          >
            <div className={cx('font-semibold text-white', xl ? 'text-2xl' : 'text-xs sm:text-sm')}>{b.metric.label}</div>
            {b.sub && <div className={cx('mt-0.5 text-slate-500', xl ? 'text-base' : 'text-[10px] sm:text-[11px]')}>{b.sub}</div>}
          </motion.div>
        ))}
      </div>
    </div>
  )
}
