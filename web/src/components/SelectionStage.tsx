import { LayoutGroup, motion } from 'framer-motion'
import { Check, Crosshair, X } from 'lucide-react'
import { useMemo } from 'react'
import { useElementSize } from '../lib/hooks'
import { cx } from '../lib/format'
import type { SelectionExample } from '../types'

/** Timeline (seconds) shared by Demo scene 4 and the Live Match explorer. */
export const SEL_T = {
  fan: 0.6,
  sweepStart: 2.8,
  sweepEnd: 5.0,
  group: 6.0,
  verdict: 8.0,
  end: 10,
}

const EASE = [0.16, 1, 0.3, 1] as const
const PASS = '#34d399'
const FAIL = '#fb7185'

/** Did the Breaker actually attack and split the drafts? (not a fallback, a single draft, or no choice) */
export function breakerDecided(e: SelectionExample): boolean {
  return (e.decided_by === 'majority' || e.decided_by === 'judge') && (e.stimulus_cycles ?? 0) > 0
}

export function pickDemoExample(examples: SelectionExample[] | undefined | null): SelectionExample | null {
  if (!examples?.length) return null
  // only show a real Breaker decision on stage; otherwise the scene shows its placeholder
  const real = examples.filter(breakerDecided)
  return (
    real.find((e) => e.chosen_correct && e.drafts?.some((d) => !d.official_pass) && (e.groups?.length ?? 0) > 1) ??
    real.find((e) => e.chosen_correct && e.drafts?.some((d) => !d.official_pass)) ??
    null
  )
}

function codePreview(code: string, max = 7): string[] {
  const lines = (code ?? '').split('\n')
  const start = lines.findIndex((l) => /\)\s*;\s*$/.test(l))
  const body = (start >= 0 ? lines.slice(start + 1) : lines).filter((l) => l.trim() && !/^\s*endmodule/.test(l))
  return body.slice(0, max).map((l) => l.replace(/\s+$/, ''))
}

function fmtValue(v: number | string): string {
  return typeof v === 'number' ? String(v) : v
}

/** "pos = 00", or just "00" in compact mode. Falls back to a group-mate's recorded output. */
function outputFor(ex: SelectionExample, label: string | undefined, compact = false): string | null {
  if (!label) return null
  const outs = ex.disputed?.outputs ?? {}
  let o = outs[label]
  if (!o) {
    const g = ex.groups?.find((grp) => grp.includes(label))
    const rep = g?.find((l) => outs[l])
    if (rep) o = outs[rep]
  }
  if (!o) return null
  return Object.entries(o)
    .map(([k, v]) => (compact ? String(v) : `${k} = ${v}`))
    .join(compact ? ' ' : ', ')
}

interface Props {
  example: SelectionExample
  t: number
  variant?: 'demo' | 'app'
}

/**
 * Test-time selection, choreographed on a clock `t` (seconds):
 * drafts are dealt and fan out, a Breaker beam sweeps across them revealing each output,
 * the drafts regroup by behavior, and the chosen group glows while the rest turn red.
 */
export function SelectionStage({ example, t, variant = 'app' }: Props) {
  const demo = variant === 'demo'
  const [wrapRef, { w: W }] = useElementSize<HTMLDivElement>({ w: 900, h: 0 })

  const drafts = example.drafts ?? []
  const N = Math.max(1, drafts.length)
  const groups = useMemo(() => {
    const g = (example.groups ?? []).filter((x) => x.length)
    return g.length ? g : [drafts.map((d) => d.label)]
  }, [example, drafts])
  const G = Math.max(1, groups.length)

  // ---- geometry: one card size for every phase, so the regroup is a pure move ----
  const narrow = W < 560
  const gap = narrow ? 6 : demo ? 18 : 10
  const pad = narrow ? 6 : demo ? 14 : 10
  const groupGap = narrow ? 10 : demo ? 28 : 16
  const BORDER = 2 // 1px group border on each side
  const SAFE = 4 // rounding slack so a row never wraps by a pixel
  const maxW = demo ? 250 : 172
  const fanW = Math.floor((W - (N - 1) * gap - SAFE) / N)
  const rowW = Math.floor((W - G * (pad * 2 + BORDER) - (G - 1) * groupGap - (N - G) * gap - SAFE) / N)
  const minRowW = narrow ? 52 : 72
  const stack = G > 1 && rowW < minRowW // one row would make the cards too small: stack the groups
  const largest = Math.max(1, ...groups.map((g) => g.length))
  const stackW = Math.floor((W - (pad * 2 + BORDER) - (largest - 1) * gap - SAFE) / largest)
  // on stage, keep the whole scene (title, cards, verdict) inside one screen
  const byHeight = demo && typeof window !== 'undefined' ? Math.floor((window.innerHeight * 0.3) / 1.02) : Number.POSITIVE_INFINITY
  const cardW = Math.max(44, Math.min(maxW, byHeight, fanW, stack ? stackW : rowW))
  const showCode = cardW >= 120
  const compact = cardW < 96
  const cardH = showCode ? Math.round(cardW * (demo ? 1.02 : 1.08)) : compact ? 64 : 76
  const labelH = demo ? 40 : 28
  const groupH = cardH + pad * 2 + BORDER + labelH
  const fanH = cardH + (demo ? 40 : 28)
  // fixed height across phases, so the verdict below never jumps
  const stageH = Math.max(fanH, stack ? G * groupH + (G - 1) * groupGap : groupH) + 16

  // ---- timeline ----
  const fanned = t >= SEL_T.fan
  const attacked = breakerDecided(example)  // no attack happened for fallback / single-draft / no-choice cases
  const sweeping = attacked && t >= SEL_T.sweepStart && t < SEL_T.sweepEnd + 0.4
  const sweepP = Math.min(1, Math.max(0, (t - SEL_T.sweepStart) / (SEL_T.sweepEnd - SEL_T.sweepStart)))
  const grouped = t >= SEL_T.group && groups.length > 0
  const verdict = t >= SEL_T.verdict
  // null when nothing was chosen (decided_by "none"): no group glows, every card stays neutral
  const chosen = typeof example.chosen_group === 'number' ? example.chosen_group : -1
  const hasChoice = chosen >= 0 && chosen < groups.length
  const good = example.chosen_correct
  const revealAt = (i: number) => SEL_T.sweepStart + ((i + 0.5) / N) * (SEL_T.sweepEnd - SEL_T.sweepStart)

  const card = (label: string, i: number) => {
    const d = drafts.find((x) => x.label === label)
    const gi = groups.findIndex((g) => g.includes(label))
    const revealed = attacked && t >= revealAt(i)
    const hit = attacked && t >= revealAt(i) - 0.12 && t < revealAt(i) + 0.45
    const isChosen = verdict && hasChoice && gi === chosen
    const isOther = verdict && hasChoice && gi !== chosen
    const mid = (N - 1) / 2
    const out = outputFor(example, label, compact)
    const big = demo && !compact // stage sizes only when the cards are large enough to carry them
    const tone = isChosen ? (good ? PASS : FAIL) : isOther ? FAIL : hit ? FAIL : revealed ? 'rgba(255,255,255,0.16)' : 'rgba(255,255,255,0.1)'
    return (
      <motion.div
        key={label}
        layoutId={`draft-${example.problem_id}-${label}`}
        layout
        initial={grouped ? false : { opacity: 0, x: (mid - i) * (cardW + gap), y: 28, rotate: (i - mid) * 1.2, scale: 0.86 }}
        animate={{
          opacity: isOther ? 0.55 : 1,
          x: 0,
          rotate: fanned && !grouped ? (i - mid) * (demo ? 3.5 : 2.5) : 0,
          y: fanned && !grouped ? Math.abs(i - mid) * (demo ? 8 : 5) : 0,
          scale: fanned ? (isChosen ? 1.03 : 1) : 0.86,
          filter: isOther ? 'saturate(0.5)' : 'saturate(1)',
        }}
        transition={{
          type: 'spring',
          stiffness: grouped ? 140 : 170,
          damping: grouped ? 20 : 22,
          delay: !fanned || grouped ? 0 : i * 0.07,
          opacity: { duration: 0.45 },
          filter: { duration: 0.45 },
        }}
        className="relative shrink-0"
        style={{ width: cardW, height: cardH }}
      >
        {/* Breaker hit: a quick shake plus an expanding ring */}
        <motion.div className="h-full w-full" animate={hit ? { x: [0, -5, 4, -2, 0] } : { x: 0 }} transition={{ duration: 0.4, ease: 'easeOut' }}>
          <div
            className="relative h-full w-full overflow-hidden rounded-xl border bg-[#0d0f15] transition-[border-color,box-shadow] duration-300"
            style={{
              borderColor: tone,
              boxShadow: isChosen ? `0 0 0 1px ${tone}, 0 0 44px -6px ${tone}` : hit ? `0 0 34px -4px ${FAIL}` : '0 14px 34px -18px rgba(0,0,0,0.95)',
            }}
          >
            <div className={cx('flex items-center justify-between border-b border-white/[0.06]', big ? 'px-3 py-2' : compact ? 'px-1.5 py-1' : 'px-2 py-1.5')}>
              <span className={cx('font-mono font-semibold text-white', big ? 'text-base' : compact ? 'text-[11px]' : 'text-xs')}>{label}</span>
              {verdict && d && (
                <motion.span
                  initial={{ scale: 0, rotate: -30 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 16, delay: 0.15 + i * 0.05 }}
                  className={cx('grid place-items-center rounded-full', big ? 'h-6 w-6' : 'h-4 w-4', d.official_pass ? 'bg-pass/20 text-pass' : 'bg-breaker/20 text-breaker')}
                  title={d.official_pass ? 'Official grade: pass' : 'Official grade: fail'}
                >
                  {d.official_pass ? <Check className={big ? 'h-4 w-4' : 'h-3 w-3'} strokeWidth={3} /> : <X className={big ? 'h-4 w-4' : 'h-3 w-3'} strokeWidth={3} />}
                </motion.span>
              )}
            </div>
            {showCode && (
              <pre className={cx('overflow-hidden px-3 pt-2 font-mono leading-[1.5] text-slate-500', demo ? 'text-[10.5px]' : 'text-[9px]')}>
                {codePreview(d?.code ?? '', demo ? 8 : 6).join('\n')}
              </pre>
            )}
            <div className={cx('absolute inset-x-0 bottom-0 border-t border-white/[0.06] bg-black/50', big ? 'px-3 py-2' : compact ? 'px-1.5 py-1' : 'px-2 py-1.5')}>
              <motion.div
                key={revealed ? 'r' : 'h'}
                initial={{ opacity: 0, y: 6, filter: 'blur(4px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                transition={{ duration: 0.35, ease: EASE }}
                className={cx(
                  'truncate font-mono',
                  big ? 'text-sm' : 'text-[11px]',
                  revealed ? (isOther ? 'text-breaker' : isChosen ? (good ? 'text-pass' : 'text-breaker') : 'text-white') : 'text-slate-600',
                )}
              >
                {revealed ? (out ?? (compact ? 'ok' : 'output recorded')) : attacked ? '· · ·' : '—'}
              </motion.div>
            </div>
            {hit && <motion.div className="pointer-events-none absolute inset-0 bg-breaker/25" initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={{ duration: 0.6 }} />}
          </div>
        </motion.div>
        {hit && (
          <motion.span
            className="pointer-events-none absolute inset-0 rounded-xl border-2 border-breaker"
            initial={{ opacity: 0.9, scale: 1 }}
            animate={{ opacity: 0, scale: 1.14 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
          />
        )}
      </motion.div>
    )
  }

  const order = drafts.map((d) => d.label)
  const indexOf = (label: string) => Math.max(0, order.indexOf(label))

  return (
    <div ref={wrapRef} className="relative w-full">
      <LayoutGroup id={`sel-${example.problem_id}`}>
        <div className="relative flex items-start justify-center" style={{ height: stageH }}>
          {!grouped ? (
            <div className="relative flex items-start justify-center pt-4" style={{ gap }}>
              {order.map((label, i) => card(label, i))}
              {sweeping && <SweepBeam p={sweepP} on={t < SEL_T.sweepEnd} demo={demo} />}
            </div>
          ) : (
            <div className={cx('flex justify-center pt-4', stack ? 'flex-col items-center' : 'flex-nowrap items-start')} style={{ gap: groupGap }}>
              {groups.map((g, gi) => {
                const isChosen = verdict && hasChoice && gi === chosen
                const isOther = verdict && hasChoice && gi !== chosen
                const tone = isChosen ? (good ? PASS : FAIL) : isOther ? FAIL : null
                const out = outputFor(example, g[0], true)
                return (
                  <motion.div key={gi} layout className="relative shrink-0 rounded-2xl" style={{ padding: pad + BORDER / 2 }}>
                    {/* the frame fades in after the cards land, so the regroup reads as a move, then a box */}
                    <motion.div
                      className="pointer-events-none absolute inset-0 rounded-2xl border"
                      initial={{ opacity: 0, scale: 0.97 }}
                      animate={{
                        opacity: 1,
                        scale: 1,
                        borderColor: tone ? `${tone}${isChosen ? '99' : '4d'}` : 'rgba(255,255,255,0.12)',
                        backgroundColor: tone ? `${tone}${isChosen ? '12' : '0a'}` : 'rgba(255,255,255,0.025)',
                      }}
                      transition={{ opacity: { delay: 0.35, duration: 0.5 }, scale: { delay: 0.35, duration: 0.5, ease: EASE }, default: { duration: 0.5 } }}
                    />
                    {isChosen && (
                      <motion.div
                        className="pointer-events-none absolute -inset-1 rounded-[20px]"
                        style={{ boxShadow: `0 0 90px -16px ${tone}` }}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: [0, 1, 0.75] }}
                        transition={{ duration: 1.2, times: [0, 0.4, 1] }}
                      />
                    )}
                    <div className="relative flex" style={{ gap }}>
                      {g.map((label) => card(label, indexOf(label)))}
                    </div>
                    <motion.div
                      className={cx('relative flex items-center justify-between gap-2', demo ? 'mt-3' : 'mt-2')}
                      style={{ height: labelH - (demo ? 12 : 8) }}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.5, duration: 0.4, ease: EASE }}
                    >
                      <span
                        className={cx(
                          'truncate font-medium',
                          demo ? 'text-base' : 'text-[11px]',
                          isChosen ? (good ? 'text-pass' : 'text-breaker') : isOther ? 'text-breaker/80' : 'text-slate-300',
                        )}
                      >
                        {attacked
                          ? `${g.length} draft${g.length === 1 ? '' : 's'} ${g.length === 1 ? 'alone' : 'agree'}`
                          : example.decided_by === 'fallback'
                            ? 'Breaker found no input · first compiling draft taken'
                            : example.decided_by === 'single'
                              ? 'only one draft compiled'
                              : 'no draft compiled'}
                        {out && !compact && <span className="ml-2 font-mono text-slate-500">→ {out}</span>}
                      </span>
                      {isChosen && (
                        <motion.span
                          initial={{ scale: 0.4, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ type: 'spring', stiffness: 300, damping: 16, delay: 0.1 }}
                          className={cx(
                            'inline-flex shrink-0 items-center gap-1 rounded-full font-semibold',
                            demo ? 'px-3 py-1 text-sm' : 'px-2 py-0.5 text-[10px]',
                            good ? 'bg-pass text-[#05120c]' : 'bg-breaker text-[#1a0508]',
                          )}
                          style={{ boxShadow: `0 0 24px -4px ${tone}` }}
                        >
                          {good ? <Check className={demo ? 'h-4 w-4' : 'h-3 w-3'} strokeWidth={3} /> : <X className={demo ? 'h-4 w-4' : 'h-3 w-3'} strokeWidth={3} />}
                          Ships
                        </motion.span>
                      )}
                    </motion.div>
                  </motion.div>
                )
              })}
            </div>
          )}
        </div>
      </LayoutGroup>

      {/* disputed input + verdict line */}
      <div className={cx('mt-2 flex flex-col items-center gap-3 text-center', demo ? 'min-h-[110px]' : 'min-h-[72px]')}>
        {example.disputed && t >= SEL_T.sweepStart && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.45, ease: EASE }}
            className={cx(
              'inline-flex max-w-full flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-full border border-breaker/35 bg-breaker/[0.09] font-mono text-breaker-soft',
              demo ? 'px-4 py-1.5 text-base' : 'px-3 py-1 text-[11px]',
            )}
            style={{ boxShadow: '0 0 30px -12px #fb7185' }}
          >
            <Crosshair className={demo ? 'h-4 w-4' : 'h-3 w-3'} />
            <span className="text-slate-400">Breaker's input{narrow ? '' : `, cycle ${example.disputed.cycle}`}:</span>
            {Object.entries(example.disputed.inputs ?? {}).map(([k, v]) => (
              <span key={k} className="text-white">
                {k} = {fmtValue(v)}
              </span>
            ))}
          </motion.div>
        )}
        {verdict && hasChoice && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ type: 'spring', stiffness: 220, damping: 18, delay: 0.35 }}
            className={cx('flex items-center font-semibold tracking-tight', demo ? '' : 'text-sm', good ? 'text-pass text-glow-pass' : 'text-breaker')}
            style={demo ? { fontSize: 'clamp(24px, 2.5vw, 50px)' } : undefined}
          >
            {good ? (
              <Check className={cx('mr-2 shrink-0', demo ? 'h-[1em] w-[1em]' : 'h-4 w-4')} strokeWidth={3} />
            ) : (
              <X className={cx('mr-2 shrink-0', demo ? 'h-[1em] w-[1em]' : 'h-4 w-4')} strokeWidth={3} />
            )}
            Official grade: {good ? 'PASS' : 'FAIL'}
          </motion.div>
        )}
      </div>
    </div>
  )
}

/** The Breaker's attack: a bright scan line with a soft halo, riding left to right across the drafts. */
function SweepBeam({ p, on, demo }: { p: number; on: boolean; demo: boolean }) {
  return (
    <motion.div
      className="pointer-events-none absolute -bottom-4 -top-2 z-20"
      style={{ left: `${p * 100}%` }}
      initial={{ opacity: 0 }}
      animate={{ opacity: on ? 1 : 0 }}
      transition={{ duration: 0.25 }}
      aria-hidden="true"
    >
      <div className="absolute inset-y-0 w-32 -translate-x-1/2" style={{ background: 'radial-gradient(closest-side, rgba(251,113,133,0.42), transparent)', filter: 'blur(6px)' }} />
      <div
        className="absolute inset-y-0 w-[2px] -translate-x-1/2"
        style={{ background: 'linear-gradient(180deg, transparent, #fb7185 12%, #ffe4e6 50%, #fb7185 88%, transparent)', boxShadow: '0 0 10px #fb7185, 0 0 28px #fb7185' }}
      />
      {demo && (
        <div className="absolute -top-1 flex -translate-x-1/2 -translate-y-full items-center gap-1.5 whitespace-nowrap rounded-full border border-breaker/50 bg-[#1a0a0e]/90 px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-breaker-soft shadow-[0_0_24px_-6px_#fb7185]">
          <Crosshair className="h-3.5 w-3.5" /> Breaker attack
        </div>
      )}
    </motion.div>
  )
}
