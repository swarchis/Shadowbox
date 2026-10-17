import { motion, useReducedMotion } from 'framer-motion'
import { Brain, GraduationCap, Repeat, Scale } from 'lucide-react'
import type { ReactNode } from 'react'
import { Card, CardHeader, fadeUp, stagger } from '../components/Card'
import { CountUp } from '../components/CountUp'
import { EmptyState } from '../components/EmptyState'
import { ExamBars, type BarSpec } from '../components/ExamBars'
import { useData } from '../lib/DataContext'
import { cx, money, pts } from '../lib/format'
import type { FinalExam, FinalMetric, FinalMetricKey } from '../types'

const pctFmt = (v: number) => `${(v * 100).toFixed(1)}%`
/** "v4", or "v?" while the engine has not written that version number yet. */
const ver = (n: number | null | undefined) => `v${typeof n === 'number' ? n : '?'}`

export function metric(final: FinalExam | null | undefined, key: FinalMetricKey): FinalMetric | null {
  const m = final?.metrics?.[key]
  return m && typeof m.pass === 'number' ? m : null
}

export function mainBars(final: FinalExam | null | undefined): BarSpec[] {
  const out: BarSpec[] = []
  const v0 = metric(final, 'v0')
  const vb = metric(final, 'vbest')
  const vs = metric(final, 'vbest_selection')
  if (v0) out.push({ key: 'v0', metric: v0, fill: 'linear-gradient(180deg, rgba(56,189,248,0.55), rgba(56,189,248,0.15))', glow: 'rgba(56,189,248,0.35)', sub: `Builder ${ver(final?.builder_versions?.v0 ?? 0)}` })
  if (vb) out.push({ key: 'vbest', metric: vb, fill: 'linear-gradient(180deg, #7dd3fc, #0284c7)', glow: 'rgba(56,189,248,0.7)', sub: `Builder ${ver(final?.builder_versions?.vbest)}` })
  if (vs)
    out.push({
      key: 'vbest_selection',
      metric: vs,
      fill: 'linear-gradient(180deg, #fda4af 0%, #38bdf8 100%)',
      glow: 'rgba(251,113,133,0.6)',
      sub: `+ Breaker ${ver(final?.breaker_versions?.vbest)} picking drafts`,
    })
  return out
}

/** True only when the latest version (or latest + Breaker) beats version 0 by at least 2 points. */
export function improved(final: FinalExam | null | undefined): boolean {
  const v0 = metric(final, 'v0')
  if (!v0) return false
  const best = Math.max(metric(final, 'vbest')?.pass ?? -1, metric(final, 'vbest_selection')?.pass ?? -1)
  return best - v0.pass >= 0.02
}

/** "Selection captures X of the Y-point gap between a random draft and the best possible pick" */
export function selectionTakeaway(final: FinalExam | null | undefined): string | null {
  const rp = metric(final, 'random_pick')
  const vs = metric(final, 'vbest_selection')
  const ce = metric(final, 'ceiling')
  if (!rp || !vs || !ce || ce.pass <= rp.pass) return null
  const gap = (ce.pass - rp.pass) * 100
  const got = (vs.pass - rp.pass) * 100
  // whole points read better on stage; keep one decimal only for tiny gaps
  const fmt = (x: number) => (gap >= 5 ? Math.round(x).toFixed(0) : x.toFixed(1))
  if (got <= 0) return `Selection does not beat a random draft yet (gap to the best possible pick: ${fmt(gap)} points).`
  return `Selection captures ${fmt(got)} of the ${fmt(gap)}-point gap between a random draft and the best possible pick.`
}

export function FinalExamView() {
  const { final } = useData()
  const bars = mainBars(final)
  const hasAny = bars.length > 0

  return (
    <motion.div initial="hidden" animate="show" variants={stagger(0.08)} className="space-y-5">
      <motion.section variants={fadeUp} className="pt-2 sm:pt-4">
        <div className="eyebrow mb-3 flex items-center gap-2">
          <GraduationCap className="h-3.5 w-3.5" /> Final exam
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          On problems it has <span className="text-white underline decoration-builder/60 decoration-2 underline-offset-4">never seen</span>
          {improved(final) ? ', the same frozen model scores higher.' : ': the same frozen model, graded honestly.'}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
          {final?.test_problems ? `${final.test_problems} held-out problems` : 'Held-out problems'}, locked away from every agent during training, graded only by the official
          testbenches.
        </p>
      </motion.section>

      {!final || !hasAny ? (
        <Card className="p-5">
          <EmptyState title="The final exam runs after the last round." hint="Version 0, the latest version, and the latest version with the Breaker picking drafts are scored on the held-out split." />
        </Card>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
            <Card className="p-5 sm:p-6">
              <CardHeader
                eyebrow="Held-out pass rate · 95% CI"
                title="Version 0 → latest → latest with the Breaker"
                right={!final.complete ? <span className="chip border-amber-300/30 bg-amber-300/10 text-amber-300">in progress</span> : undefined}
              />
              <div className="mt-8 sm:mt-10">
                <ExamBars bars={bars} height={300} />
              </div>
            </Card>
            <SelectionDetail final={final} />
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <UltraCard final={final} />
            <TransferCard final={final} />
            <AblationCard final={final} />
          </div>

          <motion.div variants={fadeUp} className="flex flex-wrap items-center gap-x-5 gap-y-2 px-1 text-xs text-slate-500">
            {typeof final.cost_usd === 'number' && <span>Final exam cost {money(final.cost_usd)}</span>}
            {typeof final.builder_versions?.vbest === 'number' && (
              <span>
                Builder {ver(final.builder_versions.v0 ?? 0)} → {ver(final.builder_versions.vbest)}
              </span>
            )}
            {typeof final.breaker_versions?.vbest === 'number' && (
              <span>
                Breaker {ver(final.breaker_versions.v0 ?? 0)} → {ver(final.breaker_versions.vbest)}
              </span>
            )}
            {(final.notes ?? []).map((n, i) => (
              <span key={i}>{n}</span>
            ))}
          </motion.div>
        </>
      )}
    </motion.div>
  )
}

function HBar({ label, m, color, delay, max, highlight, ceiling }: { label: string; m: FinalMetric; color: string; delay: number; max: number; highlight?: boolean; ceiling?: number | null }) {
  const reduce = useReducedMotion()
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-xs">
        <span className={cx('truncate', highlight ? 'font-semibold text-white' : 'text-slate-400')}>{label}</span>
        <span className={cx('num', highlight ? 'font-semibold text-white' : 'text-slate-300')}>
          <CountUp value={m.pass} format={pctFmt} delay={delay} />
        </span>
      </div>
      <div className="relative h-3">
        <div className="absolute inset-0 overflow-hidden rounded-full bg-white/[0.05]">
          <motion.div
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ background: color, boxShadow: highlight ? `0 0 16px ${color}` : undefined }}
            initial={{ width: reduce ? `${(m.pass / max) * 100}%` : 0 }}
            animate={{ width: `${(m.pass / max) * 100}%` }}
            transition={{ delay: reduce ? 0 : delay, duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
          />
        </div>
        {/* the best-possible-pick ceiling, marked on each track rather than across the labels */}
        {typeof ceiling === 'number' && (
          <motion.span
            className="pointer-events-none absolute -bottom-1 -top-1 w-0 border-l-2 border-dashed border-pass/70"
            style={{ left: `${(ceiling / max) * 100}%` }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: reduce ? 0 : 1.2 }}
            aria-hidden="true"
          />
        )}
      </div>
    </div>
  )
}

function SelectionDetail({ final }: { final: FinalExam }) {
  const rows: { key: FinalMetricKey; color: string; highlight?: boolean }[] = [
    { key: 'random_pick', color: 'rgba(148,163,184,0.55)' },
    { key: 'random_input_sel', color: 'rgba(148,163,184,0.85)' },
    { key: 'breaker_v0_sel', color: 'rgba(251,113,133,0.55)' },
    { key: 'vbest_selection', color: 'linear-gradient(90deg, #38bdf8, #fb7185)', highlight: true },
  ]
  const present = rows.map((r) => ({ ...r, m: metric(final, r.key) })).filter((r) => r.m) as { key: FinalMetricKey; color: string; highlight?: boolean; m: FinalMetric }[]
  const ceiling = metric(final, 'ceiling')
  const takeaway = selectionTakeaway(final)
  const max = 1
  if (present.length < 2) {
    return (
      <Card className="p-5">
        <CardHeader eyebrow="Does the Breaker matter?" title="Selection vs simpler ways to pick a draft" />
        <EmptyState compact title="Selection baselines not scored yet" />
      </Card>
    )
  }
  return (
    <Card className="flex flex-col p-5 sm:p-6">
      <CardHeader eyebrow={<span className="flex items-center gap-2"><Scale className="h-3.5 w-3.5" /> Does the Breaker matter?</span>} title="Wouldn't random testing do the same?" />
      <div className="relative mt-6 space-y-4">
        {present.map((r, i) => (
          <HBar key={r.key} label={r.m.label} m={r.m} color={r.color} delay={0.3 + i * 0.15} max={max} highlight={r.highlight} ceiling={ceiling?.pass ?? null} />
        ))}
      </div>
      {ceiling && (
        <div className="mt-4 flex items-center gap-2 text-xs text-pass">
          <span className="inline-block w-5 border-t-2 border-dashed border-pass/70" /> {ceiling.label}: <span className="num">{pctFmt(ceiling.pass)}</span>
        </div>
      )}
      {takeaway && (
        <motion.p initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.4 }} className="mt-auto pt-5 text-[15px] font-medium leading-snug text-white">
          {takeaway}
        </motion.p>
      )}
    </Card>
  )
}

function PairCard({ icon, eyebrow, title, a, b, note }: { icon: ReactNode; eyebrow: string; title: string; a: FinalMetric; b: FinalMetric; note?: ReactNode }) {
  const delta = b.pass - a.pass
  return (
    <Card className="p-5">
      <CardHeader eyebrow={<span className="flex items-center gap-2">{icon} {eyebrow}</span>} title={title} />
      <div className="mt-5 space-y-3.5">
        <HBar label={a.label} m={a} color="rgba(148,163,184,0.6)" delay={0.3} max={1} />
        <HBar label={b.label} m={b} color="linear-gradient(90deg, #38bdf8, #34d399)" delay={0.5} max={1} highlight />
      </div>
      <div className="mt-4 flex items-center justify-between text-xs">
        <span className="text-slate-500">{note}</span>
        <span className={cx('num rounded-full border px-2 py-0.5 font-semibold', delta >= 0 ? 'border-pass/30 bg-pass/10 text-pass' : 'border-breaker/30 bg-breaker/10 text-breaker')}>{pts(delta)}</span>
      </div>
    </Card>
  )
}

function UltraCard({ final }: { final: FinalExam }) {
  const ultra = metric(final, 'ultra')
  const ours = metric(final, 'vbest_selection') ?? metric(final, 'vbest')
  if (!ultra || !ours) return null
  return (
    <PairCard
      icon={<Brain className="h-3.5 w-3.5" />}
      eyebrow="Small vs big model"
      title={
        ours.pass - ultra.pass >= 0.02
          ? 'The evolved small model beats the big one'
          : ours.pass - ultra.pass > -0.02
            ? 'The evolved small model matches the big one'
            : 'Closing the gap to a much bigger model'
      }
      a={ultra}
      b={ours}
      note="same held-out split"
    />
  )
}

function TransferCard({ final }: { final: FinalExam }) {
  const a = metric(final, 'transfer_v0')
  const b = metric(final, 'transfer_vbest')
  if (!a || !b) return null
  // Claims follow the numbers: only call it a transfer when the learned playbook clearly helps.
  const gain = b.pass - a.pass
  const title = gain >= 0.02 ? 'The playbook works on a different AI' : gain > -0.02 ? 'No clear transfer to a different AI' : 'The playbook did not transfer'
  const note = gain >= 0.02 ? 'skills you can copy-paste' : 'same held-out split, same playbooks'
  return <PairCard icon={<Repeat className="h-3.5 w-3.5" />} eyebrow="Transfer" title={title} a={a} b={b} note={note} />
}

function AblationCard({ final }: { final: FinalExam }) {
  const nano = metric(final, 'ablation_nano_coach')
  const main = metric(final, 'ablation_main_coach')
  if (!nano && !main) return null
  return (
    <Card className="p-5">
      <CardHeader eyebrow={<span className="flex items-center gap-2"><Brain className="h-3.5 w-3.5" /> Distillation ablation</span>} title="Does the coach need a bigger model?" />
      <div className="mt-5 grid grid-cols-2 gap-3">
        {[main, nano].filter(Boolean).map((m, i) => (
          <div key={`${i}-${m!.label}`} className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
            {/* `pass` here is a gain on the validation subset (a fraction), so it can be negative */}
            <div className={cx('num text-2xl font-semibold', m!.pass >= 0 ? 'text-pass' : 'text-breaker')}>
              <CountUp value={m!.pass * 100} format={(v) => `${v >= 0.05 ? '+' : ''}${v.toFixed(1)}`} />
              <span className="ml-1 text-sm text-slate-500">pts</span>
            </div>
            <div className="mt-1 text-xs text-slate-400">{m!.label}</div>
            <div className="text-[10px] text-slate-600">n = {m!.n}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}
