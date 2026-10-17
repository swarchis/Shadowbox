// Live view: what the agents are building and testing right now.
// Reads /api/live (the engine's progress files) every few seconds. Follows the newest design unless the
// viewer pins one. Shows a block diagram of the circuit, its Verilog, the checks it went through, and the
// Breaker's attack. The official grade is labelled as hidden from the agents.

import { AnimatePresence, motion } from 'framer-motion'
import { Bug, Check, Crosshair, Eye, EyeOff, Hammer, Pin, Radio, Wrench, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchLive } from '../api'
import { useData } from '../lib/DataContext'
import { COLORS, cx, timeAgo } from '../lib/format'
import type { LiveFeed, LiveItem, LivePort } from '../types'
import { Card, CardHeader } from './Card'
import { CodePane } from './CodePane'

const POLL_MS = 2500

export function LiveWorkbench() {
  const { state } = useData()
  const [feed, setFeed] = useState<LiveFeed | null>(null)
  const [pinned, setPinned] = useState<string | null>(null) // `${source}|${problem_id}` or null = follow live
  const [, tick] = useState(0)
  const running = state?.status === 'running'
  const timer = useRef<number>()

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const f = await fetchLive()
        if (alive) setFeed(f)
      } catch {
        /* API offline: keep the last feed; the top bar shows the badge */
      }
      if (alive) timer.current = window.setTimeout(load, POLL_MS)
    }
    load()
    const clock = window.setInterval(() => tick((n) => n + 1), 1000)
    return () => {
      alive = false
      window.clearTimeout(timer.current)
      window.clearInterval(clock)
    }
  }, [])

  const items = feed?.items ?? []
  const keyOf = (it: LiveItem) => `${feed?.source}|${it.problem_id}`
  const selected = useMemo(() => {
    if (pinned) return items.find((it) => keyOf(it) === pinned) ?? items[0] ?? null
    return items[0] ?? null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, pinned, feed?.source])
  const teamTone = feed?.team === 'breaker' ? COLORS.breaker : COLORS.builder

  return (
    <Card className="p-4 sm:p-5" glow={running ? teamTone : undefined}>
      <CardHeader
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Radio className="h-3.5 w-3.5" /> Live
          </span>
        }
        title="What the agents are working on right now"
        right={
          <div className="flex flex-wrap items-center gap-2">
            {feed?.label && (
              <span className="chip border-white/10 bg-white/[0.04] text-slate-300">
                <span className={cx('h-1.5 w-1.5 rounded-full', running && 'animate-pulse')} style={{ background: teamTone }} />
                {feed.label}
              </span>
            )}
            {feed?.updated_at && <span className="text-xs text-slate-500">updated {timeAgo(feed.updated_at)}</span>}
            <button
              onClick={() => setPinned(null)}
              className={cx(
                'chip transition-colors',
                pinned ? 'border-white/10 bg-white/[0.03] text-slate-400 hover:text-white' : 'border-pass/30 bg-pass/10 text-pass',
              )}
              title="Follow the newest design automatically"
            >
              {pinned ? <Pin className="h-3 w-3" /> : <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-pass" />}
              {pinned ? 'Pinned · follow live' : 'Following live'}
            </button>
          </div>
        }
      />

      {!items.length ? (
        <div className="mt-6 flex h-40 items-center justify-center text-sm text-slate-500">
          Waiting for the first design… the feed starts as soon as the run begins building.
        </div>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-[240px_1fr]">
          {/* feed */}
          <div className="hide-scrollbar flex max-h-[560px] gap-2 overflow-auto lg:flex-col">
            <AnimatePresence initial={false}>
              {items.map((it) => {
                const k = keyOf(it)
                const active = selected && keyOf(selected) === k
                return (
                  <motion.button
                    layout
                    key={k}
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.3 }}
                    onClick={() => setPinned(k)}
                    className={cx(
                      'flex min-w-[200px] shrink-0 items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left transition-colors lg:min-w-0',
                      active ? 'border-white/20 bg-white/[0.07]' : 'border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.05]',
                    )}
                  >
                    <span className="truncate font-mono text-[12px] text-slate-200">{it.problem_id}</span>
                    <StatusDot it={it} />
                  </motion.button>
                )
              })}
            </AnimatePresence>
          </div>

          {/* detail */}
          {selected && (
            <motion.div key={keyOf(selected)} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="min-w-0 space-y-4">
              <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
                <div className="glass min-w-0 p-4">
                  <div className="eyebrow mb-1">Circuit</div>
                  <div className="mb-3 font-mono text-sm text-white">{selected.problem_id}</div>
                  <CircuitBlock ports={selected.ports} tone={teamTone} />
                  {selected.spec && <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-slate-500">{selected.spec}</p>}
                </div>
                <CodePane
                  code={selected.code ?? '// no Verilog produced'}
                  title={<span className="text-xs text-slate-400">Builder's Verilog</span>}
                  accent={COLORS.builder}
                  maxHeight={300}
                />
              </div>
              <Pipeline it={selected} />
              {selected.attack && <AttackPanel it={selected} />}
            </motion.div>
          )}
        </div>
      )}
    </Card>
  )
}

function StatusDot({ it }: { it: LiveItem }) {
  if (it.attack?.found_bug) return <Bug className="h-3.5 w-3.5 shrink-0 text-breaker" />
  if (it.compiled === false) return <X className="h-3.5 w-3.5 shrink-0 text-breaker" />
  if (it.official?.passed) return <Check className="h-3.5 w-3.5 shrink-0 text-pass" />
  if (it.official && !it.official.passed) return <X className="h-3.5 w-3.5 shrink-0 text-breaker/80" />
  return <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-slate-400" />
}

// ---------- block diagram ----------
function CircuitBlock({ ports, tone }: { ports: LivePort[]; tone: string }) {
  const ins = ports.filter((p) => p.direction === 'input')
  const outs = ports.filter((p) => p.direction !== 'input')
  const rows = Math.max(ins.length, outs.length, 1)
  const rowH = 26
  const H = rows * rowH + 28
  const W = 440
  const box = { x: 130, y: 10, w: 180, h: H - 20 }
  const y = (i: number, n: number) => box.y + ((i + 1) * box.h) / (n + 1)
  const label = (p: LivePort) => (p.width > 1 ? `${p.name} [${p.width - 1}:0]` : p.name)
  if (!ports.length) return <div className="text-xs text-slate-500">Ports unavailable.</div>
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Module block diagram">
      <motion.rect
        x={box.x}
        y={box.y}
        width={box.w}
        height={box.h}
        rx={12}
        fill="rgba(255,255,255,0.03)"
        stroke={tone}
        strokeOpacity={0.6}
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.8 }}
      />
      <text x={box.x + box.w / 2} y={box.y + box.h / 2 + 4} textAnchor="middle" className="fill-slate-300 font-mono" fontSize={13}>
        TopModule
      </text>
      {ins.map((p, i) => {
        const yy = y(i, ins.length)
        const clk = /^(clk|clock)$/.test(p.name)
        return (
          <g key={p.name}>
            <motion.line x1={box.x - 60} y1={yy} x2={box.x} y2={yy} stroke="#94a3b8" strokeWidth={p.width > 1 ? 2.5 : 1.2}
              initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.2 + i * 0.05, duration: 0.4 }} />
            {clk && <path d={`M ${box.x} ${yy - 6} L ${box.x + 9} ${yy} L ${box.x} ${yy + 6}`} fill="none" stroke="#94a3b8" />}
            <text x={box.x - 66} y={yy + 4} textAnchor="end" className="fill-slate-400 font-mono" fontSize={11}>{label(p)}</text>
          </g>
        )
      })}
      {outs.map((p, i) => {
        const yy = y(i, outs.length)
        return (
          <g key={p.name}>
            <motion.line x1={box.x + box.w} y1={yy} x2={box.x + box.w + 60} y2={yy} stroke={tone} strokeWidth={p.width > 1 ? 2.5 : 1.2}
              initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.4 + i * 0.05, duration: 0.4 }} />
            <text x={box.x + box.w + 66} y={yy + 4} className="fill-slate-300 font-mono" fontSize={11}>{label(p)}</text>
          </g>
        )
      })}
    </svg>
  )
}

// ---------- the checks a design goes through ----------
function Pipeline({ it }: { it: LiveItem }) {
  // Only the checks that actually happened to this design are shown (no "none yet" / "not attacked" tiles).
  const fired = it.tools.filter((t) => t.fired)
  type Tone = 'ok' | 'bad' | 'hidden'
  const steps: { icon: JSX.Element; title: string; detail: string; tone: Tone; note?: string }[] = [
    {
      icon: <Hammer className="h-3.5 w-3.5" />,
      title: 'Builder',
      detail: !it.code ? 'no Verilog produced' : it.compiled === false ? 'wrote it · does not compile' : `wrote it · compiles${it.attempts && it.attempts > 1 ? ` after ${it.attempts} tries` : ''}`,
      tone: it.code && it.compiled !== false ? 'ok' : 'bad',
      note: 'checked with Icarus Verilog',
    },
  ]
  if (it.tools.length)
    steps.push({ icon: <Wrench className="h-3.5 w-3.5" />, title: 'Team tool checks', detail: fired.length ? `${fired.length} of ${it.tools.length} flagged a problem` : `all ${it.tools.length} passed`, tone: fired.length ? 'bad' : 'ok', note: 'tools the coach wrote' })
  if (it.attack)
    steps.push({ icon: <Crosshair className="h-3.5 w-3.5" />, title: 'Breaker attack', detail: `${it.attack.cycles ?? 0} cycles · ${it.attack.found_bug ? 'found a real bug' : 'no bug found'}`, tone: it.attack.found_bug ? 'bad' : 'ok', note: 'confirmed against the reference' })
  steps.push({
    icon: <EyeOff className="h-3.5 w-3.5" />,
    title: 'Official grade',
    detail: it.official ? (it.official.passed ? 'PASS' : `FAIL${it.official.kind && !['mismatch', 'known buggy design'].includes(it.official.kind) ? ` · ${it.official.kind}` : ''}`) : 'pending',
    tone: 'hidden',
    note: 'hidden from the agents',
  })
  const cols = ['sm:grid-cols-1', 'sm:grid-cols-2', 'sm:grid-cols-3', 'sm:grid-cols-4'][steps.length - 1]
  return (
    <div className={cx('grid grid-cols-1 gap-2', cols)}>
      {steps.map((s, i) => {
        const official = s.tone === 'hidden'
        const pass = official && it.official?.passed
        const color = s.tone === 'ok' || pass ? 'text-pass' : s.tone === 'bad' || (official && it.official && !pass) ? 'text-breaker' : 'text-slate-300'
        return (
          <motion.div
            key={s.title}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }}
            className={cx(
              'rounded-xl border px-3 py-2.5',
              (s.tone === 'ok' || pass) && 'border-pass/25 bg-pass/[0.06]',
              (s.tone === 'bad' || (official && it.official && !pass)) && 'border-breaker/30 bg-breaker/[0.07]',
            )}
          >
            <div className={cx('flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider', color)}>
              {s.icon} {s.title}
            </div>
            <div className="mt-1 truncate text-sm text-slate-100">{s.detail}</div>
            {s.note && (
              <div className="mt-0.5 flex items-center gap-1 text-[10px] text-slate-500">
                {official && <Eye className="h-3 w-3" />} {s.note}
              </div>
            )}
          </motion.div>
        )
      })}
    </div>
  )
}

// ---------- the Breaker's attack ----------
function AttackPanel({ it }: { it: LiveItem }) {
  const a = it.attack!
  const stim = a.stimulus ?? []
  const names = stim.length ? Object.keys(stim[0]) : []
  const fm = a.first_mismatch
  return (
    <div className="glass p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="eyebrow flex items-center gap-1.5" style={{ color: COLORS.breaker }}>
          <Crosshair className="h-3.5 w-3.5" /> Breaker's attack
        </div>
        <span className={cx('chip', a.found_bug ? 'border-breaker/30 bg-breaker/10 text-breaker' : 'border-pass/30 bg-pass/10 text-pass')}>
          {a.found_bug ? <Bug className="h-3 w-3" /> : <Check className="h-3 w-3" />}
          {a.found_bug ? 'Real bug (confirmed vs reference)' : 'No bug found'}
        </span>
      </div>
      {fm && (
        <p className="mb-3 text-sm text-slate-300">
          At cycle <span className="font-mono text-white">{fm.cycle}</span>, output <span className="font-mono text-white">{fm.signal}</span> should be{' '}
          <span className="font-mono text-pass">{fm.expected}</span> but the design gave <span className="font-mono text-breaker">{fm.got}</span>.
        </p>
      )}
      {stim.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[320px] border-separate border-spacing-y-1 font-mono text-[12px]">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="pr-4 font-normal">cycle</th>
                {names.map((n) => (
                  <th key={n} className="pr-4 font-normal">{n}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stim.map((row, i) => {
                const hit = fm?.cycle === i
                return (
                  <motion.tr key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.04 }}
                    className={cx(hit ? 'text-breaker' : 'text-slate-300')}>
                    <td className={cx('rounded-l-md px-2 py-1', hit ? 'bg-breaker/10' : 'bg-white/[0.02]')}>{i}</td>
                    {names.map((n, j) => (
                      <td key={n} className={cx('px-2 py-1', hit ? 'bg-breaker/10' : 'bg-white/[0.02]', j === names.length - 1 && 'rounded-r-md')}>{row[n]}</td>
                    ))}
                  </motion.tr>
                )
              })}
            </tbody>
          </table>
          {(a.cycles ?? 0) > stim.length && <div className="mt-1 text-xs text-slate-500">… {(a.cycles ?? 0) - stim.length} more cycles</div>}
        </div>
      ) : (
        <div className="text-xs text-slate-500">{a.cycles ?? 0}-cycle attack on a frozen buggy design (input values not stored for gate attacks).</div>
      )}
    </div>
  )
}
