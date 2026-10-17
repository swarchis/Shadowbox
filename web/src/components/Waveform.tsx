import { motion, useReducedMotion } from 'framer-motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useElementSize } from '../lib/hooks'
import { bitsToHex, cx } from '../lib/format'
import type { Trace } from '../types'

type VersionKey = 'v0' | 'vbest'
type LaneKind = 'clock' | 'bit' | 'bus'
type Role = 'clock' | 'input' | 'expected' | 'actual'

interface Lane {
  key: string
  label: string
  tag?: string
  kind: LaneKind
  width: number
  role: Role
  values: (string | undefined)[]
  compare?: (string | undefined)[]
  synthClock?: boolean
}

const LABEL_W_WIDE = 150
const LABEL_W_NARROW = 108
const PAD_R = 16
const TOP = 30
const LANE_H = { clock: 26, bit: 26, bus: 30 }
const GAP = 12
const DIVIDER = 18

const norm = (v: string | undefined) => (v === undefined ? undefined : String(v).toLowerCase())
const isKnownBit = (v: string | undefined) => v === '0' || v === '1'

function buildLanes(trace: Trace, version: VersionKey): Lane[] {
  const rows = trace.rows ?? []
  const lanes: Lane[] = []
  const signals = trace.signals ?? []
  const clock = signals.find((s) => s.kind === 'clock')
  const listed = new Set(signals.map((s) => s.name))

  if (clock) {
    const vals = rows.map((r) => r.inputs?.[clock.name])
    const synth = vals.every((v) => v === undefined)
    lanes.push({ key: `clk:${clock.name}`, label: clock.name, kind: 'clock', width: 1, role: 'clock', values: vals.map(norm), synthClock: synth })
  }
  const inputs = signals.filter((s) => s.kind === 'input')
  // inputs present in rows but missing from the signal list
  const extra = new Set<string>()
  rows.forEach((r) => Object.keys(r.inputs ?? {}).forEach((k) => !listed.has(k) && extra.add(k)))
  const allInputs = [...inputs.map((s) => ({ name: s.name, width: s.width })), ...[...extra].map((name) => ({ name, width: undefined }))]
  for (const s of allInputs) {
    const vals = rows.map((r) => norm(r.inputs?.[s.name]))
    const w = s.width ?? Math.max(1, ...vals.map((v) => v?.length ?? 1))
    lanes.push({ key: `in:${s.name}`, label: s.name, kind: w > 1 ? 'bus' : 'bit', width: w, role: 'input', values: vals })
  }
  const outputs = signals.filter((s) => s.kind === 'output')
  const outNames = outputs.length ? outputs.map((s) => ({ name: s.name, width: s.width })) : Object.keys(rows[0]?.expected ?? {}).map((name) => ({ name, width: undefined }))
  for (const s of outNames) {
    const exp = rows.map((r) => norm(r.expected?.[s.name]))
    const act = rows.map((r) => norm(r[version]?.[s.name]))
    const w = s.width ?? Math.max(1, ...exp.map((v) => v?.length ?? 1))
    const kind: LaneKind = w > 1 ? 'bus' : 'bit'
    lanes.push({ key: `exp:${s.name}`, label: s.name, tag: 'expected', kind, width: w, role: 'expected', values: exp })
    lanes.push({ key: `act:${s.name}:${version}`, label: s.name, tag: version === 'v0' ? 'version 0' : 'latest', kind, width: w, role: 'actual', values: act, compare: exp })
  }
  return lanes
}

export function firstMismatch(trace: Trace | null | undefined, version: VersionKey): number | null {
  if (!trace?.rows?.length) return null
  for (let i = 0; i < trace.rows.length; i++) {
    const r = trace.rows[i]
    const exp = r.expected ?? {}
    for (const k of Object.keys(exp)) {
      if (norm(r[version]?.[k]) !== norm(exp[k])) return i
    }
  }
  return version === 'v0' && typeof trace.first_mismatch_row === 'number' && trace.first_mismatch_row >= 0 ? trace.first_mismatch_row : null
}

export function Waveform({ trace, version }: { trace: Trace; version: VersionKey }) {
  const reduce = useReducedMotion()
  const [wrapRef, { w: wrapW }] = useElementSize<HTMLDivElement>({ w: 900, h: 0 })
  const scrollRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<number | null>(null)

  const narrow = wrapW < 640
  const LABEL_W = narrow ? LABEL_W_NARROW : LABEL_W_WIDE
  const lanes = useMemo(() => buildLanes(trace, version), [trace, version])
  const n = trace.rows?.length ?? 0
  const viewW = Math.max(0, wrapW - LABEL_W)
  const colW = Math.max(narrow ? 34 : 40, Math.floor((viewW - PAD_R) / Math.max(1, n)))
  const width = n * colW + PAD_R
  const scrolls = width > viewW + 1
  const mismatchCol = firstMismatch(trace, version)
  const accent = version === 'v0' ? '#fb7185' : '#34d399'

  // lane geometry: expected/actual pairs sit close together; a divider separates inputs from outputs
  let y = TOP
  let dividerY: number | null = null
  const laneY: number[] = []
  for (let i = 0; i < lanes.length; i++) {
    const l = lanes[i]
    if (dividerY === null && l.role === 'expected' && i > 0 && lanes[i - 1].role !== 'actual') {
      dividerY = y + 2
      y += DIVIDER
    }
    laneY.push(y)
    y += LANE_H[l.kind] + GAP + (l.role === 'expected' ? -4 : 0)
  }
  const height = y + 4
  const x = (i: number) => i * colW
  // one band behind each expected + actual pair
  const pairs = lanes.flatMap((l, i) => (l.role === 'expected' && lanes[i + 1]?.role === 'actual' ? [{ top: laneY[i] - 6, bottom: laneY[i + 1] + LANE_H[lanes[i + 1].kind] + 6, key: l.key }] : []))

  // on narrow screens, bring the first mismatch into view
  useEffect(() => {
    const el = scrollRef.current
    if (!el || mismatchCol === null || !scrolls) return
    el.scrollTo({ left: Math.max(0, mismatchCol * colW - viewW / 2 + colW / 2), behavior: reduce ? 'auto' : 'smooth' })
  }, [mismatchCol, version, scrolls, viewW, colW, reduce])

  const bands = (w: number, x0: number) => (
    <>
      {pairs.map((p) => (
        <rect key={`band-${p.key}`} x={x0} y={p.top} width={w} height={p.bottom - p.top} fill="rgba(255,255,255,0.022)" />
      ))}
      {dividerY !== null && <line x1={x0} x2={x0 + w} y1={dividerY} y2={dividerY} stroke="rgba(255,255,255,0.07)" strokeDasharray="3 5" />}
    </>
  )

  return (
    <div ref={wrapRef} className="relative">
      <div className="flex">
        {/* signal names stay put while the timeline scrolls */}
        <svg width={LABEL_W} height={height} className={cx('block shrink-0', scrolls && 'shadow-[8px_0_16px_-12px_rgba(0,0,0,0.9)]')} aria-hidden="true">
          {bands(LABEL_W, 0)}
          <text x={14} y={TOP - 14} fontSize="9.5" letterSpacing="0.12em" fill="#475569" className="font-mono">
            {narrow ? 'IN' : 'INPUTS'}
          </text>
          {dividerY !== null && (
            <text x={14} y={dividerY + DIVIDER - 4} fontSize="9.5" letterSpacing="0.12em" fill="#475569" className="font-mono">
              {narrow ? 'OUT' : 'OUTPUTS'}
            </text>
          )}
          {lanes.map((lane, li) => (
            <LaneLabel key={lane.key} lane={lane} top={laneY[li]} accent={accent} narrow={narrow} />
          ))}
          {scrolls && <line x1={LABEL_W - 0.5} x2={LABEL_W - 0.5} y1={TOP - 8} y2={height - 4} stroke="rgba(255,255,255,0.06)" />}
        </svg>
        <div ref={scrollRef} className="min-w-0 flex-1 overflow-x-auto">
          <svg width={width} height={height} className="block" onMouseLeave={() => setHover(null)} role="img" aria-label={`Waveform, ${version === 'v0' ? 'version 0' : 'latest version'}`}>
            <defs>
              <pattern id="xhatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="6" height="6" fill="rgba(251,113,133,0.12)" />
                <line x1="0" y1="0" x2="0" y2="6" stroke="rgba(251,113,133,0.55)" strokeWidth="2" />
              </pattern>
              <linearGradient id="mmGlow" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="#fb7185" stopOpacity="0.35" />
                <stop offset="1" stopColor="#fb7185" stopOpacity="0.08" />
              </linearGradient>
              <filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {bands(width, 0)}

            {/* column grid + time labels (the first-mismatch time is always labelled, in red) */}
            {Array.from({ length: n }, (_, i) => {
              const isMm = i === mismatchCol
              return (
                <g key={`col${i}`}>
                  <line x1={x(i)} x2={x(i)} y1={TOP - 8} y2={height - 4} stroke="rgba(255,255,255,0.04)" />
                  {(n <= 24 || i % 2 === 0 || isMm) && (
                    <text
                      x={x(i) + colW / 2}
                      y={TOP - 14}
                      textAnchor="middle"
                      className="font-mono"
                      fontSize={isMm ? 11 : 10}
                      fontWeight={isMm ? 700 : 400}
                      fill={isMm ? '#fb7185' : hover === i ? '#e2e8f0' : '#64748b'}
                    >
                      {trace.rows[i]?.t ?? i}
                    </text>
                  )}
                </g>
              )
            })}

            {/* first mismatch column */}
            {mismatchCol !== null && (
              <motion.g key={`mm-${version}-${mismatchCol}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: reduce ? 0 : 0.5, duration: 0.5 }}>
                <rect x={x(mismatchCol)} y={TOP - 8} width={colW} height={height - TOP + 4} rx={6} fill="url(#mmGlow)" />
                <rect
                  x={x(mismatchCol)}
                  y={TOP - 8}
                  width={colW}
                  height={height - TOP + 4}
                  rx={6}
                  fill="none"
                  stroke="#fb7185"
                  strokeOpacity={0.8}
                  filter="url(#softGlow)"
                  className="motion-safe:animate-pulse"
                />
              </motion.g>
            )}

            {/* hover column */}
            {hover !== null && <rect x={x(hover)} y={TOP - 8} width={colW} height={height - TOP + 4} fill="rgba(255,255,255,0.05)" rx={4} />}

            {lanes.map((lane, li) => (
              <LaneView key={lane.key} lane={lane} top={laneY[li]} colW={colW} n={n} accent={accent} reduce={!!reduce} />
            ))}

            {/* hover targets */}
            {Array.from({ length: n }, (_, i) => (
              <rect key={`hit${i}`} x={x(i)} y={0} width={colW} height={height} fill="transparent" onMouseEnter={() => setHover(i)} onClick={() => setHover(i)} />
            ))}
          </svg>
        </div>
      </div>
      <HoverReadout trace={trace} lanes={lanes} col={hover ?? mismatchCol} isMismatch={hover === null && mismatchCol !== null} />
    </div>
  )
}

function LaneLabel({ lane, top, accent, narrow }: { lane: Lane; top: number; accent: string; narrow: boolean }) {
  const mid = top + LANE_H[lane.kind] / 2
  const color = lane.role === 'actual' ? accent : lane.role === 'expected' ? '#e2e8f0' : lane.role === 'clock' ? '#64748b' : '#94a3b8'
  const tag = lane.tag ? (narrow ? (lane.role === 'expected' ? 'exp' : lane.tag === 'version 0' ? 'v0' : 'new') : lane.tag) : null
  return (
    <g>
      {lane.role === 'actual' && <rect x={6} y={mid - 7} width={2.5} height={14} rx={1.25} fill={accent} />}
      <text x={14} y={mid + 4} fontSize="12" className="font-mono" fill={color} fontWeight={lane.role === 'input' || lane.role === 'clock' ? 400 : 600}>
        {lane.label}
        {tag && (
          <tspan dx={6} fontSize="10" fontWeight={400} fill={lane.role === 'actual' ? accent : '#64748b'} opacity={0.9}>
            {tag}
          </tspan>
        )}
      </text>
    </g>
  )
}

function LaneView({ lane, top, colW, n, accent, reduce }: { lane: Lane; top: number; colW: number; n: number; accent: string; reduce: boolean }) {
  const h = LANE_H[lane.kind]
  const hi = top + 3
  const lo = top + h - 3
  const mid = top + h / 2
  const x = (i: number) => i * colW
  const isActual = lane.role === 'actual'
  const baseStroke = lane.role === 'clock' ? '#64748b' : lane.role === 'input' ? '#94a3b8' : lane.role === 'expected' ? '#e2e8f0' : accent === '#34d399' ? '#34d399' : '#e2e8f0'
  const mism = (i: number) => isActual && lane.compare && lane.values[i] !== lane.compare[i]

  // mismatch cell backgrounds
  const mismatchCells = isActual
    ? Array.from({ length: n }, (_, i) =>
        mism(i) ? <rect key={`m${i}`} x={x(i) + 1} y={top - 2} width={colW - 2} height={h + 4} rx={4} fill="rgba(251,113,133,0.16)" stroke="rgba(251,113,133,0.35)" /> : null,
      )
    : null

  if (lane.kind === 'clock') {
    let d = ''
    if (lane.synthClock) {
      d = `M ${x(0)} ${lo}`
      for (let i = 0; i < n; i++) d += ` L ${x(i)} ${lo} L ${x(i)} ${hi} L ${x(i) + colW / 2} ${hi} L ${x(i) + colW / 2} ${lo} L ${x(i + 1)} ${lo}`
    } else {
      d = digitalPath(lane.values, x, colW, hi, lo, n).d
    }
    return (
      <g>
        <motion.path d={d} fill="none" stroke={baseStroke} strokeWidth={1.5} initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2, ease: 'easeInOut' }} />
      </g>
    )
  }

  if (lane.kind === 'bit') {
    const { d, xs } = digitalPath(lane.values, x, colW, hi, lo, n)
    return (
      <g>
        {mismatchCells}
        {xs.map((i) => (
          <rect key={`x${i}`} x={x(i)} y={hi} width={colW} height={lo - hi} fill="url(#xhatch)" rx={2} />
        ))}
        <motion.path
          d={d}
          fill="none"
          stroke={baseStroke}
          strokeWidth={isActual || lane.role === 'expected' ? 2 : 1.5}
          strokeLinejoin="round"
          initial={reduce ? false : { pathLength: 0, opacity: 0.4 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: isActual ? 1.1 : 0.9, ease: 'easeInOut' }}
          style={isActual ? { filter: `drop-shadow(0 0 4px ${baseStroke}80)` } : undefined}
        />
        {isActual &&
          Array.from({ length: n }, (_, i) =>
            mism(i) ? (
              <path
                key={`mp${i}`}
                d={segmentPath(lane.values[i], x(i), colW, hi, lo)}
                fill="none"
                stroke="#fb7185"
                strokeWidth={2.25}
                style={{ filter: 'drop-shadow(0 0 4px #fb7185)' }}
              />
            ) : null,
          )}
      </g>
    )
  }

  // bus: hexagon-ended boxes per run of equal values
  const runs: { s: number; e: number; v: string | undefined }[] = []
  for (let i = 0; i < n; i++) {
    const v = lane.values[i]
    const last = runs[runs.length - 1]
    if (last && last.v === v && !(isActual && mism(i) !== mism(i - 1))) last.e = i + 1
    else runs.push({ s: i, e: i + 1, v })
  }
  return (
    <g>
      {mismatchCells}
      {runs.map((r, k) => {
        const xs = x(r.s) + 1
        const xe = x(r.e) - 1
        const e = Math.min(6, (xe - xs) / 3)
        const pts = `${xs + e},${hi} ${xe - e},${hi} ${xe},${mid} ${xe - e},${lo} ${xs + e},${lo} ${xs},${mid}`
        const unknown = r.v === undefined || /[xz]/.test(r.v)
        const bad = isActual && mism(r.s)
        const stroke = bad ? '#fb7185' : baseStroke
        const txt = r.v === undefined ? '' : bitsToHex(r.v, lane.width)
        const fits = xe - xs > txt.length * 7 + 8
        return (
          <motion.g
            key={`${k}-${r.v}`}
            initial={reduce ? false : { opacity: 0, scaleX: 0.6 }}
            animate={{ opacity: 1, scaleX: 1 }}
            transition={{ duration: 0.35, delay: reduce ? 0 : r.s * 0.035 }}
            style={{ transformOrigin: `${xs}px ${mid}px` }}
          >
            <polygon
              points={pts}
              fill={unknown ? 'url(#xhatch)' : bad ? 'rgba(251,113,133,0.14)' : lane.role === 'input' ? 'rgba(148,163,184,0.06)' : isActual ? `${accent}14` : 'rgba(226,232,240,0.06)'}
              stroke={unknown ? 'rgba(251,113,133,0.6)' : stroke}
              strokeWidth={bad ? 1.75 : 1.25}
              style={bad ? { filter: 'drop-shadow(0 0 5px #fb7185)' } : undefined}
            />
            {fits && (
              <text x={(xs + xe) / 2} y={mid + 4} textAnchor="middle" fontSize="11" className="font-mono" fill={bad ? '#fda4af' : unknown ? '#fda4af' : lane.role === 'input' ? '#94a3b8' : '#e2e8f0'}>
                {txt}
              </text>
            )}
          </motion.g>
        )
      })}
    </g>
  )
}

function segmentPath(v: string | undefined, x0: number, w: number, hi: number, lo: number): string {
  if (v === '1') return `M ${x0} ${hi} L ${x0 + w} ${hi}`
  if (v === '0') return `M ${x0} ${lo} L ${x0 + w} ${lo}`
  return `M ${x0} ${(hi + lo) / 2} L ${x0 + w} ${(hi + lo) / 2}`
}

function digitalPath(values: (string | undefined)[], x: (i: number) => number, colW: number, hi: number, lo: number, n: number): { d: string; xs: number[] } {
  let d = ''
  const xs: number[] = []
  let prev: string | undefined
  const yOf = (v: string) => (v === '1' ? hi : lo)
  for (let i = 0; i < n; i++) {
    const v = values[i]
    if (isKnownBit(v)) {
      const yy = yOf(v as string)
      if (!isKnownBit(prev)) d += ` M ${x(i)} ${yy}`
      else if (prev !== v) d += ` L ${x(i)} ${yy}`
      d += ` L ${x(i) + colW} ${yy}`
    } else if (v === 'z') {
      const m = (hi + lo) / 2
      d += ` M ${x(i)} ${m} L ${x(i) + colW} ${m}`
    } else {
      xs.push(i)
    }
    prev = v
  }
  return { d: d.trim() || `M ${x(0)} ${lo}`, xs }
}

function HoverReadout({ trace, lanes, col, isMismatch }: { trace: Trace; lanes: Lane[]; col: number | null; isMismatch: boolean }) {
  if (col === null || !trace.rows[col]) {
    return <div className="mt-2 h-6 px-1 text-[11px] text-slate-600">Hover a column to read every signal at that moment.</div>
  }
  return (
    <div className="mt-2 flex min-h-6 flex-wrap items-center gap-x-3 gap-y-1 px-1 font-mono text-[11px]">
      <span className={isMismatch ? 'text-breaker' : 'text-slate-400'}>
        {isMismatch ? 'first mismatch · ' : ''}t={trace.rows[col].t}
      </span>
      {lanes
        .filter((l) => l.role !== 'clock')
        .map((l) => {
          const v = l.values[col]
          const bad = l.role === 'actual' && l.compare && v !== l.compare[col]
          return (
            <span key={l.key} className={bad ? 'text-breaker' : l.role === 'expected' ? 'text-slate-200' : 'text-slate-500'}>
              {l.label}
              {l.tag ? `(${l.tag})` : ''}={v === undefined ? '?' : l.width > 1 ? `${bitsToHex(v, l.width)}` : v}
            </span>
          )
        })}
    </div>
  )
}
