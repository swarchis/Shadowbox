import { motion } from 'framer-motion'
import { Bug, Hammer, Swords, Target } from 'lucide-react'
import { useMemo } from 'react'
import { ArmsRaceChart, ArmsRaceLegend } from '../components/ArmsRaceChart'
import { Card, CardHeader, fadeUp, stagger } from '../components/Card'
import { EventFeed } from '../components/EventFeed'
import { LiveRunPanel } from '../components/LiveRunPanel'
import { LiveWorkbench } from '../components/LiveWorkbench'
import { MatchGrid } from '../components/MatchGrid'
import { StatTile } from '../components/StatTile'
import { useData } from '../lib/DataContext'
import { COLORS, finite, pct, pts } from '../lib/format'

export function OverviewView() {
  const { state, series, rounds, lineage } = useData()

  const stats = useMemo(() => {
    const points = series?.points ?? []
    const first = points[0]
    const last = points[points.length - 1]
    // rates are null until the engine has scored that version
    const vals = finite(points.map((p) => p.builder_val_pass))
    const bestVal = vals.length ? Math.max(...vals) : null
    const baseVal = first?.builder_val_pass ?? null
    // latest scored value per line (the newest point can still be null while it is being scored)
    const lastOf = (key: 'builder_val_pass' | 'breaker_pool_catch') => {
      for (let i = points.length - 1; i >= 0; i--) if (typeof points[i][key] === 'number') return points[i][key]
      return null
    }
    const lastBuilder = lastOf('builder_val_pass')
    const lastBreaker = lastOf('breaker_pool_catch')
    // distinct bugs: the same unchanged design re-attacked in later rounds counts once (computed by the engine)
    const bugs = series?.distinct_bugs ?? (rounds?.rounds ?? []).reduce((a, r) => a + (r.bugs_found ?? 0), 0)
    const subtle = series?.distinct_subtle_bugs ?? (rounds?.rounds ?? []).reduce((a, r) => a + (r.subtle_bugs ?? 0), 0)
    const entries = lineage?.entries ?? []
    const kept = entries.filter((e) => e.accepted).length
    const keptBy = (team: string) => entries.some((e) => e.accepted && e.team === team)
    const up = (a: number | null | undefined, b: number | null | undefined) => typeof a === 'number' && typeof b === 'number' && a > b
    // only claim improvement the numbers show
    const builderUp = keptBy('builder') && up(lastBuilder, first?.builder_val_pass)
    const breakerUp = keptBy('breaker') && up(lastBreaker, first?.breaker_pool_catch)
    return { first, last, bestVal, baseVal, lastBuilder, lastBreaker, bugs, subtle, kept, builderUp, breakerUp, proposed: entries.length, roundsDone: (rounds?.rounds ?? []).filter((r) => r.complete).length }
  }, [series, rounds, lineage])

  const builderV = state?.builder_version ?? stats.last?.builder_version ?? null
  const breakerV = state?.breaker_version ?? stats.last?.breaker_version ?? null

  return (
    <motion.div initial="hidden" animate="show" variants={stagger(0.07)} className="space-y-5">
      <motion.section variants={fadeUp} className="pb-1 pt-2 sm:pt-4">
        <div className="eyebrow mb-3 flex items-center gap-2">
          <Swords className="h-3.5 w-3.5 text-slate-400" /> Self-play for chip design
        </div>
        <h1 className="max-w-3xl text-3xl font-semibold leading-[1.1] tracking-tight text-white sm:text-5xl">
          Two AI teams. <span className="text-builder text-glow-builder">One builds</span>,{' '}
          <span className="text-breaker text-glow-breaker">one breaks</span>.
          {stats.builderUp && stats.breakerUp ? ' Both get better.' : stats.builderUp || stats.breakerUp ? ' Each change has to earn its place.' : ''}
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-400 sm:text-base">
          The model stays frozen. After every round, coaches rewrite their own team's playbook, and a gatekeeper keeps a change only if it
          measurably helps.
          {stats.proposed > 0 && (
            <>
              {' '}
              So far: <span className="text-slate-200">{stats.proposed}</span> changes proposed, <span className="text-pass">{stats.kept}</span> kept.
            </>
          )}
        </p>
      </motion.section>

      <motion.div variants={stagger(0.06)} className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatTile
          label="Builder"
          value={builderV}
          format={(v) => `v${Math.round(v)}`}
          color={COLORS.builder}
          icon={<Hammer className="h-3.5 w-3.5" />}
          sub={stats.roundsDone ? `after ${stats.roundsDone} round${stats.roundsDone === 1 ? '' : 's'}` : 'version 0'}
        />
        <StatTile
          label="Breaker"
          value={breakerV}
          format={(v) => `v${Math.round(v)}`}
          color={COLORS.breaker}
          icon={<Swords className="h-3.5 w-3.5" />}
          sub={stats.lastBreaker !== null ? `catches ${pct(stats.lastBreaker)} of the bug pool` : 'version 0'}
          delay={0.05}
        />
        <StatTile
          label="Best val pass"
          value={stats.bestVal}
          format={(v) => pct(v, 1)}
          color={COLORS.pass}
          icon={<Target className="h-3.5 w-3.5" />}
          sub={stats.baseVal !== null && stats.bestVal !== null ? `${pts(stats.bestVal - stats.baseVal)} vs version 0` : 'waiting for round 1'}
          delay={0.1}
        />
        <StatTile
          label="Bugs found"
          value={stats.bugs}
          color="#fbbf24"
          icon={<Bug className="h-3.5 w-3.5" />}
          sub={stats.subtle ? `${stats.subtle} the official tests missed` : 'validated against the reference'}
          delay={0.15}
        />
      </motion.div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="p-4 sm:p-5 lg:col-span-2">
          <CardHeader
            eyebrow="The arms race"
            title={stats.builderUp && stats.breakerUp ? 'Each team gets better because the other one does' : 'Builder vs Breaker, round by round'}
            right={
              stats.last ? (
                <div className="hidden gap-4 text-right sm:flex">
                  <Current label="Builder" value={stats.lastBuilder} base={stats.first?.builder_val_pass} color={COLORS.builder} />
                  <Current label="Breaker" value={stats.lastBreaker} base={stats.first?.breaker_pool_catch} color={COLORS.breaker} />
                </div>
              ) : null
            }
          />
          <div className="mt-3">
            <ArmsRaceLegend />
          </div>
          <div className="mt-3">
            <ArmsRaceChart series={series} height={340} />
          </div>
        </Card>
        <LiveRunPanel />
      </div>

      <LiveWorkbench />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <MatchGrid />
        </div>
        <EventFeed maxHeight={340} />
      </div>
    </motion.div>
  )
}

function Current({ label, value, base, color }: { label: string; value: number | null; base?: number | null; color: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="num text-xl font-semibold" style={{ color }}>
        {pct(value)}
      </div>
      {value !== null && base !== undefined && base !== null && <div className="num text-[10px] text-slate-500">{pts(value - base)}</div>}
    </div>
  )
}
