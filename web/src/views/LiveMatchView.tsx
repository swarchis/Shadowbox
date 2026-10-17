import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, Check, GraduationCap, RotateCcw, Swords, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Card, CardHeader, fadeUp, stagger } from '../components/Card'
import { CodePane } from '../components/CodePane'
import { EmptyState } from '../components/EmptyState'
import { SEL_T, SelectionStage, pickDemoExample } from '../components/SelectionStage'
import { Waveform, firstMismatch } from '../components/Waveform'
import { useData } from '../lib/DataContext'
import { cx } from '../lib/format'
import { lineDiff } from '../lib/highlight'
import { useClock } from '../lib/hooks'
import type { DemoCase, SelectionExample } from '../types'

type V = 'v0' | 'vbest'

export function latestLabel(c: DemoCase | null | undefined): string {
  if (!c) return 'Latest'
  const v = c.vbest?.version
  return v === 'selection' ? 'Latest + Breaker' : typeof v === 'number' ? `Latest · v${v}` : 'Latest'
}

const DECIDED_LABEL: Record<string, string> = { majority: 'majority', judge: 'judge', single: 'all agree', none: 'none', fallback: 'fallback' }
const decidedLabel = (d: string | null | undefined) => (d ? (DECIDED_LABEL[d] ?? d.replace(/_/g, ' ')) : 'none')

export function LiveMatchView({ onNavigate }: { onNavigate?: (tab: 'evolution') => void }) {
  const { demoCases, selection } = useData()
  const cases = demoCases?.cases ?? []
  const [idx, setIdx] = useState(0)
  const [version, setVersion] = useState<V>('v0')
  const c = cases[Math.min(idx, Math.max(0, cases.length - 1))] ?? null

  useEffect(() => {
    if (idx >= cases.length && cases.length) setIdx(0)
  }, [cases.length, idx])

  const diff = useMemo(() => (c ? lineDiff(c.v0.code ?? '', c.vbest.code ?? '') : null), [c])

  return (
    <motion.div initial="hidden" animate="show" variants={stagger(0.07)} className="space-y-5">
      <motion.section variants={fadeUp} className="pt-2 sm:pt-4">
        <div className="eyebrow mb-3 flex items-center gap-2">
          <Swords className="h-3.5 w-3.5" /> Live match
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Same problem. <span className="text-breaker text-glow-breaker">Version 0</span> fails,{' '}
          <span className="text-pass text-glow-pass">{c && isSelectionCase(c) ? "the Breaker's pick" : c && typeof c.vbest?.version === 'number' ? `version ${c.vbest.version}` : 'the latest'}</span>{' '}
          passes.
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
          {c?.trace?.source === 'random'
            ? "The Breaker's own attack didn't expose this bug, so the waveform below replays random inputs that do, against both designs."
            : 'The Breaker attacked version 0 with inputs it chose itself. Below is the waveform of that attack, replayed against both designs.'}
        </p>
      </motion.section>

      {!c ? (
        <Card className="p-5">
          <EmptyState title="Waiting for the first round..." hint="Live Match cases appear once the Builder has a version that passes a problem version 0 failed." />
        </Card>
      ) : (
        <>
          {/* case picker */}
          <motion.div variants={fadeUp} className="hide-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 py-1 sm:-mx-1 sm:px-1">
            {cases.map((dc, i) => (
              <button
                key={`${i}-${dc.problem_id}`}
                onClick={() => {
                  setIdx(i)
                  setVersion('v0')
                }}
                className={cx(
                  'group relative min-w-[220px] max-w-[300px] shrink-0 rounded-xl border px-3.5 py-2.5 text-left transition-colors',
                  i === idx ? 'border-white/20 bg-white/[0.07]' : 'border-white/[0.06] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]',
                )}
              >
                {i === idx && <motion.span layoutId="case-glow" className="absolute inset-0 rounded-xl ring-1 ring-builder/40" />}
                <div className="truncate font-mono text-[13px] text-white">{dc.problem_id}</div>
                <div className="mt-0.5 truncate text-xs text-slate-500">
                  {dc.explanation?.kind === 'selection' || (dc.explanation && dc.explanation.round == null)
                    ? 'Fixed by Breaker selection'
                    : `v0 fails · ${typeof dc.vbest?.version === 'number' ? `v${dc.vbest.version}` : 'latest'} passes`}
                </div>
              </button>
            ))}
          </motion.div>

          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <Card className="p-5">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="eyebrow mb-1">Problem</div>
                  <div className="font-mono text-lg text-white">{c.problem_id}</div>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{c.spec}</p>
                </div>
                <VerdictBig pass={(version === 'v0' ? c.v0 : c.vbest).official_pass} k={`${c.problem_id}-${version}`} />
              </div>
              <div className="mt-5">
                <VersionToggle value={version} onChange={setVersion} latest={latestLabel(c)} />
              </div>
            </Card>

            <ExplanationCard c={c} version={version} onNavigate={onNavigate} />
          </div>

          <Card className="p-4 sm:p-5">
            <CardHeader
              eyebrow={c.trace?.source === 'random' ? 'Random inputs, replayed (the Breaker found no failing input)' : "The Breaker's attack, replayed"}
              title={
                <span>
                  Waveform · <span className={version === 'v0' ? 'text-breaker' : 'text-pass'}>{version === 'v0' ? 'Version 0' : latestLabel(c)}</span>
                </span>
              }
              right={<MismatchChip c={c} version={version} />}
            />
            <div className="mt-4">
              {c.trace?.rows?.length ? (
                <Waveform trace={c.trace} version={version} />
              ) : (
                <EmptyState compact title="No waveform recorded for this case" icon={<Swords className="h-4 w-4" />} />
              )}
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <CodePane
              code={c.v0.code}
              title={<>Version 0 · <span className="text-slate-400">official grade {c.v0.official_pass ? 'PASS' : 'FAIL'}</span></>}
              accent="#fb7185"
              marks={diff?.removed}
              markTone="del"
              active={version === 'v0'}
              right={<MiniVerdict pass={c.v0.official_pass} />}
            />
            <CodePane
              code={c.vbest.code}
              title={<>{latestLabel(c)} · <span className="text-slate-400">official grade {c.vbest.official_pass ? 'PASS' : 'FAIL'}</span></>}
              accent="#34d399"
              marks={diff?.added}
              markTone="add"
              active={version === 'vbest'}
              right={<MiniVerdict pass={c.vbest.official_pass} />}
            />
          </div>
        </>
      )}

      <SelectionExplorer examples={selection?.examples ?? []} />
    </motion.div>
  )
}

function MiniVerdict({ pass }: { pass: boolean }) {
  return (
    <span className={cx('chip', pass ? 'border-pass/30 bg-pass/10 text-pass' : 'border-breaker/30 bg-breaker/10 text-breaker')}>
      {pass ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
      {pass ? 'PASS' : 'FAIL'}
    </span>
  )
}

function MismatchChip({ c, version }: { c: DemoCase; version: V }) {
  const mm = firstMismatch(c.trace, version)
  const rows = c.trace?.rows ?? []
  if (!rows.length) return null // no trace recorded: nothing to claim either way
  const count = rows.filter((r) => Object.keys(r.expected ?? {}).some((k) => String(r[version]?.[k] ?? '').toLowerCase() !== String(r.expected[k]).toLowerCase())).length
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={version}
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 4 }}
        className={cx('chip whitespace-nowrap', mm !== null ? 'border-breaker/30 bg-breaker/10 text-breaker' : 'border-pass/30 bg-pass/10 text-pass')}
      >
        {mm !== null ? `${count} mismatching sample${count === 1 ? '' : 's'} · first at t=${rows[mm]?.t ?? mm}` : 'every sample matches the reference'}
      </motion.span>
    </AnimatePresence>
  )
}

export function VersionToggle({ value, onChange, latest }: { value: V; onChange: (v: V) => void; latest: string }) {
  const opts: { id: V; label: string; color: string }[] = [
    { id: 'v0', label: 'Version 0', color: '#fb7185' },
    { id: 'vbest', label: latest, color: '#34d399' },
  ]
  return (
    <div className="inline-flex rounded-xl border border-white/[0.08] bg-black/30 p-1" role="tablist">
      {opts.map((o) => (
        <button
          key={o.id}
          role="tab"
          aria-selected={value === o.id}
          onClick={() => onChange(o.id)}
          className={cx('relative flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors', value === o.id ? 'text-white' : 'text-slate-400 hover:text-slate-200')}
        >
          {value === o.id && (
            <motion.span
              layoutId="version-pill"
              className="absolute inset-0 rounded-lg"
              style={{ background: `${o.color}1f`, boxShadow: `inset 0 0 0 1px ${o.color}66, 0 0 24px -8px ${o.color}` }}
              transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            />
          )}
          <span className="relative h-2 w-2 rounded-full" style={{ background: o.color, boxShadow: `0 0 8px ${o.color}` }} />
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  )
}

export function VerdictBig({ pass, k, size = 'md' }: { pass: boolean; k: string; size?: 'md' | 'xl' }) {
  const color = pass ? '#34d399' : '#fb7185'
  const xl = size === 'xl'
  return (
    <div className="relative shrink-0">
      <AnimatePresence mode="wait">
        <motion.div
          key={k}
          initial={{ scale: 0.5, opacity: 0, rotate: -8 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          exit={{ scale: 0.8, opacity: 0, rotate: 6 }}
          transition={{ type: 'spring', stiffness: 320, damping: 18 }}
          className={cx('relative flex items-center gap-3 rounded-2xl border-2 font-black tracking-tight', xl ? 'px-8 py-5 text-7xl' : 'px-5 py-3 text-4xl')}
          style={{ color, borderColor: `${color}aa`, background: `${color}14`, boxShadow: `0 0 60px -10px ${color}, inset 0 0 30px -10px ${color}` }}
        >
          <span className="absolute inset-0 rounded-2xl motion-safe:animate-pulse" style={{ boxShadow: `0 0 0 1px ${color}55` }} />
          {pass ? <Check className={xl ? 'h-16 w-16' : 'h-9 w-9'} strokeWidth={3.5} /> : <X className={xl ? 'h-16 w-16' : 'h-9 w-9'} strokeWidth={3.5} />}
          {pass ? 'PASS' : 'FAIL'}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

function ExplanationCard({ c, version, onNavigate }: { c: DemoCase; version: V; onNavigate?: (tab: 'evolution') => void }) {
  const e = c.explanation
  const selection = e?.kind === 'selection' || (e != null && e.round == null)
  const changes = e?.changes ?? []
  return (
    <Card className="flex flex-col p-5" glow={version === 'vbest' ? '#34d399' : undefined}>
      <CardHeader
        eyebrow={selection ? 'How the passing design was chosen' : 'What the team changed since version 0'}
        right={
          selection ? (
            <span className="chip border-breaker/30 bg-breaker/10 text-breaker">picked by the Breaker</span>
          ) : (
            <span className="chip border-builder/30 bg-builder/10 text-builder">
              {changes.length} change{changes.length === 1 ? '' : 's'} kept
            </span>
          )
        }
      />
      {e ? (
        <>
          <div className="mt-3 text-lg font-semibold leading-snug tracking-tight text-white">{e.summary}</div>
          {changes.length > 0 ? (
            <ol className="mt-3 space-y-1.5">
              {changes.map((ch, i) => (
                <li key={i} className="flex gap-2 text-sm leading-snug text-slate-300">
                  <span className="mt-0.5 shrink-0 font-mono text-[11px] text-builder">R{ch.round ?? '?'}</span>
                  <span>{ch.summary}</span>
                </li>
              ))}
            </ol>
          ) : null}
          <p className="mt-3 text-xs leading-relaxed text-slate-500">{e.reasoning}</p>
        </>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No playbook changes were recorded for this case.</p>
      )}
      <div className="mt-auto pt-4">
        {onNavigate && !selection && (
          <button onClick={() => onNavigate('evolution')} className="inline-flex items-center gap-1.5 text-xs font-medium text-builder hover:text-builder-soft">
            See every change the coaches proposed <ArrowRight className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </Card>
  )
}

function SelectionExplorer({ examples }: { examples: SelectionExample[] }) {
  const initial = useMemo(() => {
    const d = pickDemoExample(examples)
    return d ? Math.max(0, examples.indexOf(d)) : 0
  }, [examples])
  const [idx, setIdx] = useState<number | null>(null)
  const [run, setRun] = useState(0)
  const cur = idx ?? initial
  const ex = examples[cur] ?? null
  const t = useClock(!!ex, `${cur}-${run}`, SEL_T.end)

  return (
    <Card className="p-4 sm:p-5">
      <CardHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <GraduationCap className="h-3.5 w-3.5" /> Breaker at test time · held-out problems, no answer key
          </span>
        }
        title="Five drafts. The Breaker finds where they disagree. The survivor ships."
        right={
          ex ? (
            <button
              onClick={() => setRun((r) => r + 1)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5 text-xs text-slate-300 hover:bg-white/[0.08]"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Replay
            </button>
          ) : null
        }
      />
      {!ex ? (
        <EmptyState compact title="Selection examples appear after the final exam." />
      ) : (
        <>
          <div className="hide-scrollbar -mx-1 mt-3 flex gap-2 overflow-x-auto p-1">
            {examples.map((e, i) => (
              <button
                key={`${i}-${e.problem_id}`}
                onClick={() => {
                  setIdx(i)
                  setRun((r) => r + 1)
                }}
                className={cx(
                  'shrink-0 rounded-lg border px-3 py-1.5 text-left text-xs transition-colors',
                  i === cur ? 'border-white/20 bg-white/[0.07] text-white' : 'border-white/[0.06] text-slate-400 hover:text-slate-200',
                )}
              >
                <span className="font-mono">{e.problem_id}</span>
                <span className="ml-2 text-slate-500">
                  {decidedLabel(e.decided_by)}
                </span>
                {e.chosen_group !== null && <span className={cx('ml-2', e.chosen_correct ? 'text-pass' : 'text-breaker')}>{e.chosen_correct ? '✓' : '✗'}</span>}
              </button>
            ))}
          </div>
          <p className="mt-3 text-sm text-slate-400">{ex.spec}</p>
          <div className="mt-2">
            <SelectionStage key={`${cur}-${run}`} example={ex} t={t} variant="app" />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
            <span>
              Decided by <span className="text-slate-300">{decidedLabel(ex.decided_by)}</span>
              {ex.groups?.length ? ` · ${ex.groups.map((g) => g.length).join(' vs ')}` : ''}
            </span>
            <span>{ex.stimulus_cycles} Breaker stimulus cycles</span>
          </div>
          {ex.judge_reasoning && (
            <div className="mt-3 rounded-xl border border-white/[0.06] bg-black/20 p-3 text-xs leading-relaxed text-slate-400">
              <span className="font-semibold text-slate-300">Judge: </span>
              {ex.judge_reasoning}
            </div>
          )}
        </>
      )}
    </Card>
  )
}

function isSelectionCase(c: DemoCase): boolean {
  return c.vbest?.version === 'selection' || c.explanation?.kind === 'selection' || (c.explanation != null && c.explanation.round == null)
}
