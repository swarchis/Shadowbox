import { useReducedMotion } from 'framer-motion'
import { Check, X } from 'lucide-react'
import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from 'recharts'
import { COLORS, finite, pct, teamColor } from '../lib/format'
import type { Series, SeriesChange, Team } from '../types'
import { EmptyState } from './EmptyState'

interface Row {
  round: number
  /** null when the engine has not scored that version yet: drawn as a gap, no dot */
  builder: number | null
  breaker: number | null
  bv: number
  brv: number
}

function ChartTooltip({ active, payload, changesByRound }: TooltipProps<number, string> & { changesByRound: Map<number, SeriesChange[]> }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as Row
  const changes = changesByRound.get(row.round) ?? []
  return (
    <div className="glass-strong w-72 max-w-[80vw] p-3 text-xs">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-white">{row.round === 0 ? 'Baseline' : `Round ${row.round}`}</span>
        <span className="num text-slate-500">
          B v{row.bv} · R v{row.brv}
        </span>
      </div>
      <div className="mb-2 grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-builder/10 px-2 py-1.5">
          <div className="text-[10px] uppercase tracking-wider text-builder/80">Builder val</div>
          <div className="num text-base font-semibold text-builder">{pct(row.builder, 1)}</div>
        </div>
        <div className="rounded-lg bg-breaker/10 px-2 py-1.5">
          <div className="text-[10px] uppercase tracking-wider text-breaker/80">Breaker catch</div>
          <div className="num text-base font-semibold text-breaker">{pct(row.breaker, 1)}</div>
        </div>
      </div>
      {changes.length > 0 ? (
        <ul className="space-y-1.5">
          {changes.map((c, i) => (
            <li key={i} className="flex gap-2">
              <span
                className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full"
                style={{ background: c.accepted ? teamColor(c.team) : 'transparent', border: `1.5px solid ${teamColor(c.team)}` }}
              >
                {c.accepted ? <Check className="h-2.5 w-2.5 text-[#07080c]" strokeWidth={3} /> : <X className="h-2.5 w-2.5" style={{ color: teamColor(c.team) }} strokeWidth={3} />}
              </span>
              <span className={c.accepted ? 'text-slate-200' : 'text-slate-500 line-through decoration-slate-600'}>{c.summary}</span>
              <span className={`num ml-auto shrink-0 ${c.net_flips > 0 ? 'text-pass' : c.net_flips < 0 ? 'text-breaker' : 'text-slate-500'}`}>
                {c.net_flips > 0 ? '+' : ''}
                {c.net_flips}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-slate-500">{row.round === 0 ? 'Version 0 of both teams.' : 'No changes proposed this round.'}</div>
      )}
    </div>
  )
}

export function ArmsRaceChart({ series, height = 340 }: { series: Series | null; height?: number }) {
  const reduce = useReducedMotion()
  const rows: Row[] = useMemo(
    () =>
      (series?.points ?? [])
        .slice()
        .sort((a, b) => a.round - b.round)
        .map((p) => ({ round: p.round, builder: p.builder_val_pass, breaker: p.breaker_pool_catch, bv: p.builder_version, brv: p.breaker_version })),
    [series],
  )
  const changesByRound = useMemo(() => {
    const m = new Map<number, SeriesChange[]>()
    for (const c of series?.changes ?? []) {
      const list = m.get(c.round) ?? []
      list.push(c)
      m.set(c.round, list)
    }
    return m
  }, [series])

  const [lo, hi] = useMemo(() => {
    const vals = finite(rows.flatMap((r) => [r.builder, r.breaker]))
    if (!vals.length) return [0, 1]
    const min = Math.max(0, Math.floor((Math.min(...vals) - 0.08) * 10) / 10)
    const max = Math.min(1, Math.ceil((Math.max(...vals) + 0.06) * 10) / 10)
    return [min, Math.max(max, min + 0.2)]
  }, [rows])

  const hasValues = rows.some((r) => r.builder !== null || r.breaker !== null)
  if (!rows.length || !hasValues) return <EmptyState hint="The chart starts at round 0 (both teams at version 0) and adds a point after every round." />

  const dot = (team: Team) => {
    const DotRenderer = (props: { cx?: number | null; cy?: number | null; index?: number; payload?: Row }) => {
      const { index = 0, payload } = props
      const cx = props.cx
      const cy = props.cy
      if (typeof cx !== 'number' || typeof cy !== 'number' || !Number.isFinite(cy) || !payload || payload[team] === null) return <g key={`${team}-${index}`} />
      const color = teamColor(team)
      const list = (payload ? changesByRound.get(payload.round) : undefined)?.filter((c) => c.team === team) ?? []
      const acc = list.some((c) => c.accepted)
      const rej = list.some((c) => !c.accepted)
      return (
        <g key={`${team}-${index}`} className="dot-pop" style={{ animationDelay: `${index * 70}ms`, transformOrigin: `${cx}px ${cy}px` }}>
          {rej && <circle cx={cx} cy={cy} r={acc ? 9.5 : 6.5} fill="#07080c" stroke={color} strokeWidth={1.75} strokeOpacity={0.85} />}
          {acc && <circle cx={cx} cy={cy} r={5.5} fill={color} stroke="#07080c" strokeWidth={2} style={{ filter: `drop-shadow(0 0 6px ${color})` }} />}
          {!acc && !rej && <circle cx={cx} cy={cy} r={2.5} fill={color} opacity={0.7} />}
        </g>
      )
    }
    return DotRenderer
  }

  return (
    <div style={{ height }} className="arms-race w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 16, right: 18, bottom: 4, left: -12 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.045)" strokeDasharray="2 6" vertical={false} />
          <XAxis
            dataKey="round"
            type="number"
            domain={[0, Math.max(1, rows[rows.length - 1].round)]}
            allowDecimals={false}
            tickCount={Math.min(12, rows.length + 1)}
            tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'JetBrains Mono' }}
            tickFormatter={(r: number) => (r === 0 ? 'v0' : `R${r}`)}
            axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
            tickLine={false}
          />
          <YAxis
            domain={[lo, hi]}
            tickFormatter={(v: number) => pct(v)}
            tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'JetBrains Mono' }}
            axisLine={false}
            tickLine={false}
            width={52}
          />
          <Tooltip
            cursor={{ stroke: 'rgba(255,255,255,0.15)', strokeDasharray: '3 4' }}
            content={<ChartTooltip changesByRound={changesByRound} />}
            wrapperStyle={{ outline: 'none', zIndex: 20 }}
          />
          <Line
            className="line-builder"
            type="monotone"
            dataKey="builder"
            name="Builder"
            stroke={COLORS.builder}
            strokeWidth={2.75}
            dot={dot('builder')}
            activeDot={{ r: 6, fill: COLORS.builder, stroke: '#07080c', strokeWidth: 2 }}
            connectNulls
            isAnimationActive={!reduce}
            animationDuration={1600}
            animationEasing="ease-out"
          />
          <Line
            className="line-breaker"
            type="monotone"
            dataKey="breaker"
            name="Breaker"
            stroke={COLORS.breaker}
            strokeWidth={2.75}
            dot={dot('breaker')}
            activeDot={{ r: 6, fill: COLORS.breaker, stroke: '#07080c', strokeWidth: 2 }}
            connectNulls
            isAnimationActive={!reduce}
            animationDuration={1600}
            animationBegin={250}
            animationEasing="ease-out"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ArmsRaceLegend() {
  // series and markers wrap as two groups, so the markers never strand on their own line
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-400">
      <span className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="flex items-center gap-2">
          <span className="h-0.5 w-5 rounded-full bg-builder shadow-[0_0_8px_#38bdf8]" />
          Builder · validation pass rate
        </span>
        <span className="flex items-center gap-2">
          <span className="h-0.5 w-5 rounded-full bg-breaker shadow-[0_0_8px_#fb7185]" />
          Breaker · frozen bug-pool catch rate
        </span>
      </span>
      <span className="flex items-center gap-3 text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-300" /> kept
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border-[1.5px] border-slate-400" /> rejected
        </span>
      </span>
    </div>
  )
}
