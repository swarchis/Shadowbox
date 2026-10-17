import { AnimatePresence, motion } from 'framer-motion'
import { useMemo } from 'react'
import { useElementSize } from '../../lib/hooks'
import { COLORS, finite } from '../../lib/format'
import type { Series, SeriesChange, SeriesPoint, Team } from '../../types'

type RateKey = 'builder_val_pass' | 'breaker_pool_catch'
/** A point with a rate for `key` (the engine writes null until that version is scored). */
type Scored = SeriesPoint & { v: number }

/**
 * Arms Race chart that draws itself: `progress` in [0, 1] reveals the lines
 * left to right, round by round. Dots pop in as the pen passes them.
 */
export function ArmsRaceDraw({ series, progress }: { series: Series; progress: number }) {
  const [ref, size] = useElementSize<HTMLDivElement>({ w: 1200, h: 520 })

  const points = useMemo(() => [...(series.points ?? [])].sort((a, b) => a.round - b.round), [series])
  const changesBy = useMemo(() => {
    const m = new Map<string, SeriesChange[]>()
    for (const c of series.changes ?? []) {
      const k = `${c.team}:${c.round}`
      m.set(k, [...(m.get(k) ?? []), c])
    }
    return m
  }, [series])

  const { w, h } = size
  const fs = Math.max(12, Math.min(22, w / 70))
  const padL = fs * 4.2
  const padR = fs * 7
  const padT = fs * 1.4
  const padB = fs * 3
  const plotW = Math.max(10, w - padL - padR)
  const plotH = Math.max(10, h - padT - padB)
  const maxRound = Math.max(1, points[points.length - 1]?.round ?? 1)
  // per-line points that have a value; lines connect across unscored rounds
  const scored = useMemo(() => {
    const pick = (key: RateKey): Scored[] => points.flatMap((p) => (typeof p[key] === 'number' && Number.isFinite(p[key]) ? [{ ...p, v: p[key] as number }] : []))
    return { builder_val_pass: pick('builder_val_pass'), breaker_pool_catch: pick('breaker_pool_catch') }
  }, [points])
  const vals = finite(points.flatMap((p) => [p.builder_val_pass, p.breaker_pool_catch]))
  const lo = Math.max(0, Math.floor((Math.min(...vals, 1) - 0.08) * 10) / 10)
  const hi = Math.min(1, Math.max(lo + 0.2, Math.ceil((Math.max(...vals, 0) + 0.06) * 10) / 10))
  const X = (r: number) => padL + (r / maxRound) * plotW
  const Y = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * plotH
  const headX = padL + progress * plotW

  const line = (key: RateKey) => scored[key].map((p, i) => `${i ? 'L' : 'M'} ${X(p.round).toFixed(1)} ${Y(p.v).toFixed(1)}`).join(' ')
  const area = (key: RateKey) => {
    const pts = scored[key]
    if (!pts.length) return ''
    return `${line(key)} L ${X(pts[pts.length - 1].round)} ${padT + plotH} L ${X(pts[0].round)} ${padT + plotH} Z`
  }

  /** Interpolated value under the pen, or null before this line's first scored point. */
  const valueAt = (key: RateKey): number | null => {
    const pts = scored[key]
    if (!pts.length) return null
    const r = progress * maxRound
    if (r < pts[0].round) return null
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i]
      const b = pts[i + 1]
      if (r >= a.round && r <= b.round) {
        const f = b.round === a.round ? 0 : (r - a.round) / (b.round - a.round)
        return a.v + (b.v - a.v) * f
      }
    }
    return pts[pts.length - 1].v
  }

  // a gridline every 10 points; label every other one when the range is wide
  const ticksY: number[] = []
  for (let v = Math.ceil(lo * 10) / 10; v <= hi + 1e-9; v = Math.round((v + 0.1) * 10) / 10) ticksY.push(v)
  const labelEvery = ticksY.length > 6 ? 2 : 1
  const curRound = progress * maxRound
  const heads: { team: Team; key: RateKey; color: string }[] = [
    { team: 'builder', key: 'builder_val_pass', color: COLORS.builder },
    { team: 'breaker', key: 'breaker_pool_catch', color: COLORS.breaker },
  ]

  return (
    <div ref={ref} className="h-full w-full">
      <svg width={w} height={h} className="block overflow-visible">
        <defs>
          <clipPath id="ard-clip">
            <rect x={0} y={0} width={Math.max(0, headX)} height={h} />
          </clipPath>
          {heads.map((hd) => (
            <linearGradient key={hd.team} id={`ard-area-${hd.team}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={hd.color} stopOpacity="0.22" />
              <stop offset="1" stopColor={hd.color} stopOpacity="0" />
            </linearGradient>
          ))}
          <linearGradient id="ard-scan" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#ffffff" stopOpacity="0" />
            <stop offset="0.5" stopColor="#ffffff" stopOpacity="0.22" />
            <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
          </linearGradient>
          <filter id="ard-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="6" />
          </filter>
        </defs>

        {/* grid: faint horizontal rules, muted axis labels, a slightly stronger baseline */}
        {ticksY.map((v, i) => (
          <g key={v}>
            <line x1={padL} x2={padL + plotW} y1={Y(v)} y2={Y(v)} stroke="rgba(255,255,255,0.045)" strokeDasharray={i % labelEvery ? '2 6' : undefined} />
            {i % labelEvery === 0 && (
              <text x={padL - fs * 0.6} y={Y(v) + fs * 0.35} textAnchor="end" fontSize={fs * 0.8} className="font-mono" fill="#475569">
                {Math.round(v * 100)}%
              </text>
            )}
          </g>
        ))}
        <line x1={padL} x2={padL + plotW} y1={padT + plotH} y2={padT + plotH} stroke="rgba(255,255,255,0.1)" />
        {points.map((p) => {
          const passed = p.round <= curRound + 1e-6
          const current = passed && p.round > curRound - 1 + 1e-6
          return (
            <g key={p.round}>
              <line x1={X(p.round)} x2={X(p.round)} y1={padT + plotH} y2={padT + plotH + fs * 0.4} stroke={passed ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.08)'} />
              <text
                x={X(p.round)}
                y={padT + plotH + fs * 1.8}
                textAnchor="middle"
                fontSize={fs * 0.85}
                fontWeight={current ? 700 : 400}
                className="font-mono"
                fill={current ? '#f8fafc' : passed ? '#94a3b8' : '#334155'}
                style={{ transition: 'fill 0.3s' }}
              >
                {p.round === 0 ? 'v0' : `R${p.round}`}
              </text>
            </g>
          )
        })}

        {/* the pen: a soft vertical scan line that rides with the lines' heads */}
        {progress > 0.001 && (
          <g opacity={progress >= 1 ? 0 : 1} style={{ transition: 'opacity 0.6s' }}>
            <rect x={headX - 0.75} y={padT} width={1.5} height={plotH} fill="url(#ard-scan)" />
          </g>
        )}

        <g clipPath="url(#ard-clip)">
          {heads.map((hd) => (
            <g key={hd.team}>
              <path d={area(hd.key)} fill={`url(#ard-area-${hd.team})`} />
              <path d={line(hd.key)} fill="none" stroke={hd.color} strokeWidth={fs * 0.55} strokeOpacity={0.45} filter="url(#ard-glow)" />
              <path d={line(hd.key)} fill="none" stroke={hd.color} strokeWidth={fs * 0.22} strokeLinejoin="round" strokeLinecap="round" />
            </g>
          ))}
        </g>

        {/* change dots */}
        {heads.map((hd) =>
          points.map((p) => {
            const list = changesBy.get(`${hd.team}:${p.round}`) ?? []
            const pv = p[hd.key]
            if (!list.length || pv === null) return null
            const visible = X(p.round) <= headX + 0.5
            const acc = list.some((c) => c.accepted)
            const rej = list.some((c) => !c.accepted)
            const cx = X(p.round)
            const cy = Y(pv)
            return (
              <AnimatePresence key={`${hd.team}-${p.round}`}>
                {visible && (
                  <motion.g
                    initial={{ scale: 0, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: 'spring', stiffness: 420, damping: 14 }}
                    style={{ transformOrigin: `${cx}px ${cy}px` }}
                  >
                    {rej && (
                      <motion.circle
                        cx={cx}
                        cy={cy}
                        r={acc ? fs * 0.95 : fs * 0.6}
                        fill="#07080c"
                        stroke={hd.color}
                        strokeWidth={fs * 0.12}
                        initial={{ opacity: 1 }}
                        animate={{ opacity: acc ? 0.8 : 0.4 }}
                        transition={{ delay: 0.9, duration: 0.8 }}
                      />
                    )}
                    {acc && <circle cx={cx} cy={cy} r={fs * 0.5} fill={hd.color} stroke="#07080c" strokeWidth={fs * 0.15} style={{ filter: `drop-shadow(0 0 ${fs * 0.5}px ${hd.color})` }} />}
                  </motion.g>
                )}
              </AnimatePresence>
            )
          }),
        )}

        {/* moving heads with live values */}
        {progress > 0.001 &&
          (() => {
            const hv = heads.flatMap((hd) => {
              const v = valueAt(hd.key)
              return v === null ? [] : [{ ...hd, v, cy: Y(v) }]
            })
            const ly = hv.map((x) => x.cy)
            const minGap = fs * 1.3
            if (hv.length === 2 && Math.abs(ly[0] - ly[1]) < minGap) {
              const mid = (ly[0] + ly[1]) / 2
              const up = ly[0] <= ly[1] ? 0 : 1
              ly[up] = mid - minGap / 2
              ly[1 - up] = mid + minGap / 2
            }
            return hv.map((hd, i) => (
              <g key={`head-${hd.team}`}>
                <circle cx={headX} cy={hd.cy} r={fs * 0.9} fill={hd.color} opacity={0.18} className="motion-safe:animate-pulse" />
                <circle cx={headX} cy={hd.cy} r={fs * 0.32} fill="white" />
                <text
                  x={headX + fs * 1.1}
                  y={ly[i] + fs * 0.38}
                  fontSize={fs * 1.15}
                  fontWeight={700}
                  className="font-mono"
                  fill={hd.color}
                  stroke="#07080c"
                  strokeWidth={fs * 0.32}
                  strokeLinejoin="round"
                  paintOrder="stroke"
                >
                  {Math.round(hd.v * 100)}%
                </text>
              </g>
            ))
          })()}
      </svg>
    </div>
  )
}
