import { motion } from 'framer-motion'
import { GitBranch, ScrollText, Wrench } from 'lucide-react'
import { useMemo, useState } from 'react'
import { TeamChip } from '../components/Badges'
import { Card, CardHeader, fadeUp, stagger } from '../components/Card'
import { CodePane } from '../components/CodePane'
import { EmptyState } from '../components/EmptyState'
import { LineageCard } from '../components/LineageCard'
import { Modal } from '../components/Modal'
import { ToolCard, type ToolInfo } from '../components/ToolCard'
import { useData } from '../lib/DataContext'
import { cx, teamColor } from '../lib/format'
import type { LineageEntry, Team } from '../types'

type Filter = 'all' | Team

export function EvolutionView() {
  const { lineage, playbooks } = useData()
  const [filter, setFilter] = useState<Filter>('all')
  const [showRejected, setShowRejected] = useState(true)
  const [openTool, setOpenTool] = useState<string | null>(null)

  const entries = lineage?.entries ?? []

  const tools: ToolInfo[] = useMemo(() => {
    const out: ToolInfo[] = []
    for (const team of ['builder', 'breaker'] as Team[]) {
      const pb = playbooks[team].current
      if (!pb) continue
      const names = new Set([...(pb.tools ?? []), ...Object.keys(pb.tool_sources ?? {})])
      for (const name of names) out.push({ name, team, source: pb.tool_sources?.[name] ?? null, stats: pb.tool_stats?.[name] ?? null })
    }
    return out.sort((a, b) => (a.stats?.born_round ?? 99) - (b.stats?.born_round ?? 99))
  }, [playbooks])

  const byRound = useMemo(() => {
    const m = new Map<number, LineageEntry[]>()
    for (const e of entries) {
      if (filter !== 'all' && e.team !== filter) continue
      if (!showRejected && !e.accepted) continue
      const list = m.get(e.round) ?? []
      list.push(e)
      m.set(e.round, list)
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0])
  }, [entries, filter, showRejected])

  const kept = entries.filter((e) => e.accepted).length
  const tool = tools.find((t) => t.name === openTool) ?? null
  const toolFromLineage = openTool && !tool ? entries.find((e) => e.tool_name === openTool) : null

  return (
    <motion.div initial="hidden" animate="show" variants={stagger(0.07)} className="space-y-6">
      <motion.section variants={fadeUp} className="pt-2 sm:pt-4">
        <div className="eyebrow mb-3 flex items-center gap-2">
          <GitBranch className="h-3.5 w-3.5" /> Evolution
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Every change the coaches proposed. Only the ones that helped survived.</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
          A gatekeeper reran each candidate against the current version on the same validation problems. Kept changes became a new version; rejected ones are
          shown too, so you can see the filter is real.
        </p>
        {entries.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <Stat label="proposed" value={entries.length} />
            <Stat label="kept" value={kept} tone="pass" />
            <Stat label="rejected" value={entries.length - kept} tone="muted" />
            <Stat label="agent-written tools" value={tools.length} tone="tool" />
          </div>
        )}
      </motion.section>

      {/* Toolbox */}
      <motion.section variants={fadeUp}>
        <div className="mb-3 flex items-center gap-2">
          <Wrench className="h-4 w-4 text-slate-400" />
          <h2 className="text-sm font-semibold text-white">Toolbox</h2>
          <span className="text-xs text-slate-500">tools the coaches wrote for their own teams</span>
        </div>
        {tools.length ? (
          <div className="hide-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
            {tools.map((t, i) => (
              <ToolCard key={`${t.team}-${t.name}`} tool={t} index={i} onOpen={() => setOpenTool(t.name)} />
            ))}
          </div>
        ) : (
          <Card className="p-4">
            <EmptyState compact title="No agent-written tools yet" hint="Coaches write a tool when the same mistake shows up across many problems. It survives only if it helps." icon={<Wrench className="h-4 w-4" />} />
          </Card>
        )}
      </motion.section>

      <PlaybookSummary />

      {/* Timeline */}
      <motion.section variants={fadeUp}>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-semibold text-white">Timeline</h2>
          <div className="flex rounded-lg border border-white/[0.08] bg-black/20 p-0.5 text-xs">
            {(['all', 'builder', 'breaker'] as Filter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                aria-pressed={filter === f}
                className={cx('rounded-md px-2.5 py-1 capitalize transition-colors', filter === f ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-slate-200')}
              >
                {f === 'all' ? 'Both teams' : f}
              </button>
            ))}
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-400">
            <input type="checkbox" checked={showRejected} onChange={(e) => setShowRejected(e.target.checked)} className="accent-sky-400" />
            show rejected
          </label>
        </div>

        {byRound.length === 0 ? (
          <Card className="p-5">
            <EmptyState hint="After each round, both coaches propose changes. They show up here with their reasoning and the gate result." />
          </Card>
        ) : (
          <div className="relative">
            <div className="mb-4 hidden grid-cols-2 gap-10 md:grid">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-builder">
                <span className="h-px flex-1 bg-gradient-to-r from-transparent to-builder/40" /> Builder coach
              </div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-breaker">
                Breaker coach <span className="h-px flex-1 bg-gradient-to-l from-transparent to-breaker/40" />
              </div>
            </div>
            {/* spine */}
            <div className="absolute bottom-0 left-[11px] top-2 w-px bg-gradient-to-b from-white/20 via-white/10 to-transparent md:left-1/2" />
            <div className="space-y-8">
              {byRound.map(([round, list]) => {
                const b = list.filter((e) => e.team === 'builder')
                const r = list.filter((e) => e.team === 'breaker')
                return (
                  <div key={round} className="relative">
                    <RoundMarker round={round} list={list} />
                    {/* desktop: builder left, breaker right */}
                    <div className="mt-4 hidden gap-10 md:grid md:grid-cols-2">
                      <div className="space-y-3">
                        {b.map((e, i) => (
                          <LineageCard key={e.id} e={e} index={i} onTool={setOpenTool} />
                        ))}
                        {!b.length && filter !== 'breaker' && <NoChange team="builder" />}
                      </div>
                      <div className="space-y-3">
                        {r.map((e, i) => (
                          <LineageCard key={e.id} e={e} index={i} onTool={setOpenTool} />
                        ))}
                        {!r.length && filter !== 'builder' && <NoChange team="breaker" />}
                      </div>
                    </div>
                    {/* mobile: single column */}
                    <div className="mt-3 space-y-3 pl-8 md:hidden">
                      {list.map((e, i) => (
                        <LineageCard key={e.id} e={e} index={i} onTool={setOpenTool} />
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </motion.section>

      <Modal
        open={!!openTool}
        onClose={() => setOpenTool(null)}
        accent={teamColor(tool?.team ?? toolFromLineage?.team ?? null)}
        title={
          <span className="flex items-center gap-2">
            <Wrench className="h-4 w-4" />
            <span className="font-mono">{openTool}</span>
            {(tool?.team ?? toolFromLineage?.team) && <TeamChip team={(tool?.team ?? toolFromLineage?.team) as Team} />}
            {tool?.stats && (
              <span className="hidden text-xs font-normal text-slate-500 sm:inline">
                {tool.stats.born_round != null ? `born round ${tool.stats.born_round} · ` : ''}
                {tool.stats.runs} runs · fired {tool.stats.fired}×
              </span>
            )}
          </span>
        }
      >
        {tool?.source ? (
          <CodePane code={tool.source} lang="python" accent={teamColor(tool.team)} maxHeight="70vh" className="rounded-none border-0" />
        ) : (
          <div className="p-6 text-sm text-slate-400">
            {toolFromLineage && !toolFromLineage.accepted
              ? 'This tool was rejected by the gatekeeper, so it never joined the toolbox and its source was not kept in the current playbook.'
              : 'Source not available for this tool.'}
          </div>
        )}
      </Modal>
    </motion.div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'pass' | 'muted' | 'tool' }) {
  return (
    <span
      className={cx(
        'inline-flex items-baseline gap-1.5 rounded-lg border px-2.5 py-1',
        tone === 'pass' ? 'border-pass/25 bg-pass/[0.07]' : tone === 'tool' ? 'border-amber-300/20 bg-amber-300/[0.06]' : 'border-white/[0.08] bg-white/[0.03]',
      )}
    >
      <span className={cx('num text-sm font-semibold', tone === 'pass' ? 'text-pass' : tone === 'muted' ? 'text-slate-400' : tone === 'tool' ? 'text-amber-300' : 'text-white')}>
        {value}
      </span>
      <span className="text-slate-500">{label}</span>
    </span>
  )
}

function RoundMarker({ round, list }: { round: number; list: LineageEntry[] }) {
  const kept = list.filter((e) => e.accepted).length
  return (
    <div className="relative flex items-center md:justify-center">
      <motion.div
        initial={{ scale: 0.6, opacity: 0 }}
        whileInView={{ scale: 1, opacity: 1 }}
        viewport={{ once: true }}
        transition={{ type: 'spring', stiffness: 260, damping: 20 }}
        className="relative z-10 flex items-center gap-2 rounded-full border border-white/15 bg-[#0d0f15] py-1 pl-1 pr-3"
      >
        <span className="grid h-6 w-6 place-items-center rounded-full bg-white/10 font-mono text-[11px] font-semibold text-white">{round}</span>
        <span className="text-xs font-medium text-white">Round {round}</span>
        <span className="text-[11px] text-slate-500">
          {kept}/{list.length} kept
        </span>
      </motion.div>
    </div>
  )
}

function NoChange({ team }: { team: Team }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/[0.08] px-4 py-3 text-xs text-slate-600">
      No {team} change proposed this round.
    </div>
  )
}

function PlaybookSummary() {
  const { playbooks } = useData()
  const teams = (['builder', 'breaker'] as Team[]).filter((t) => playbooks[t].current)
  if (!teams.length) return null
  return (
    <motion.section variants={fadeUp} className="grid gap-4 md:grid-cols-2">
      {teams.map((team) => {
        const pb = playbooks[team].current!
        const color = teamColor(team)
        const versions = playbooks[team].index?.versions ?? []
        return (
          <Card key={team} className="p-5">
            <CardHeader
              eyebrow={
                <span className="flex items-center gap-2">
                  <ScrollText className="h-3.5 w-3.5" /> {team} playbook · v{pb.version}
                </span>
              }
              title={team === 'builder' ? 'What the Builder knows now' : 'What the Breaker knows now'}
              right={
                <div className="flex items-center gap-1" title="Version lineage">
                  {versions.map((v) => (
                    <span
                      key={v.version}
                      className="h-2 w-2 rounded-full"
                      style={{ background: v.version === pb.version ? color : `${color}40`, boxShadow: v.version === pb.version ? `0 0 8px ${color}` : undefined }}
                    />
                  ))}
                </div>
              }
            />
            {pb.rules?.length ? (
              <ol className="mt-3 space-y-2">
                {pb.rules.map((r, i) => (
                  <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-slate-300">
                    <span className="num mt-0.5 shrink-0 text-[11px]" style={{ color }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    {r}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-3 text-[13px] text-slate-500">No rules yet{pb.tools?.length ? `; ${pb.tools.length} tool${pb.tools.length === 1 ? '' : 's'}` : ''}.</p>
            )}
            {pb.params && Object.keys(pb.params).length > 0 && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {Object.entries(pb.params).map(([k, v]) => (
                  <span key={k} className="rounded-md border border-white/[0.06] bg-black/20 px-1.5 py-0.5 font-mono text-[10.5px] text-slate-400">
                    {k}=<span className="text-slate-200">{String(v)}</span>
                  </span>
                ))}
              </div>
            )}
          </Card>
        )
      })}
    </motion.section>
  )
}
