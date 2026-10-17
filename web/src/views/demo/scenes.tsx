import { AnimatePresence, motion } from 'framer-motion'
import { Bug, Check, Crosshair, Hammer, Repeat, X } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { ExamBars } from '../../components/ExamBars'
import { LogoMark } from '../../components/Logo'
import { SelectionStage, pickDemoExample } from '../../components/SelectionStage'
import type { DataValue } from '../../lib/DataContext'
import { cx, pts, teamColor, teamName } from '../../lib/format'
import { improved, mainBars, metric } from '../FinalExamView'
import { ArmsRaceDraw } from './ArmsRaceDraw'

export interface SceneProps {
  t: number
  data: DataValue
}

const ease = [0.16, 1, 0.3, 1] as const
const at = (t: number, start: number) => t >= start

/* ---------- 1. Intro ---------- */

export function SceneIntro({ t, data }: SceneProps) {
  const cfg = data.demoConfig
  const project = (cfg?.project || 'Shadowbox').toUpperCase()
  const tagline = cfg?.tagline || 'AI teams that get better by fighting themselves'
  const team = (cfg?.team ?? []).filter((m) => m.name)
  // "SHADOW" white, "BOX" muted, matching the app's wordmark; any other name stays white
  const mutedFrom = project === 'SHADOWBOX' ? 6 : project.length
  // 8.4vw on desktop (capped at 176px); on phones up to 11vw so the nine letters still fit the width
  const wordStyle = { fontSize: 'min(11vw, max(48px, 8.4vw), 176px)', paddingLeft: '0.18em' }
  return (
    <div className="relative flex h-full w-full flex-col items-center justify-center px-[6vw]">
      <div className="flex flex-col items-center">
        <div className="relative">
          {/* soft two-team halo behind the mark */}
          <motion.div
            className="pointer-events-none absolute left-1/2 top-1/2 h-[220%] w-[260%] -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ background: 'radial-gradient(closest-side, rgba(56,189,248,0.22), rgba(251,113,133,0.12) 55%, transparent)', filter: 'blur(20px)' }}
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.5, duration: 1.4, ease }}
          />
          <div className="relative motion-safe:animate-floaty">
            <LogoMark size={Math.round(Math.min(230, Math.max(96, window.innerWidth * 0.1)))} animated />
          </div>
          {at(t, 0.75) && (
            <motion.span
              className="pointer-events-none absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white"
              initial={{ scale: 0.2, opacity: 0.9 }}
              animate={{ scale: 9, opacity: 0 }}
              transition={{ duration: 0.9, ease: 'easeOut' }}
              style={{ filter: 'blur(8px)' }}
            />
          )}
        </div>
        <div className="relative mt-[3vh]">
          <h1 className="flex font-semibold leading-none tracking-[0.18em] text-white" style={wordStyle} aria-label={project}>
            {project.split('').map((ch, i) => (
              <motion.span
                key={i}
                initial={{ opacity: 0, y: 40, filter: 'blur(12px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                transition={{ delay: 0.45 + i * 0.05, duration: 0.7, ease }}
                className={i >= mutedFrom ? 'text-slate-400' : undefined}
              >
                {ch}
              </motion.span>
            ))}
          </h1>
          {/* one builder-to-breaker light sweep across the wordmark once the letters land.
              Plain text (not flex items) so background-clip:text works; kerning off so glyphs sit exactly on the letters above. */}
          <div
            aria-hidden="true"
            className="shine-text pointer-events-none absolute inset-0 whitespace-nowrap font-semibold leading-none tracking-[0.18em]"
            style={{ ...wordStyle, fontKerning: 'none' }}
          >
            {project}
          </div>
        </div>
        <motion.p
          className="mt-[3vh] text-center text-slate-300"
          style={{ fontSize: 'clamp(18px, 2.1vw, 42px)' }}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.5, duration: 0.8, ease }}
        >
          {tagline}
        </motion.p>
        <motion.div
          className="mt-[3vh] flex flex-wrap items-center justify-center gap-x-3 gap-y-2 font-mono text-slate-400"
          style={{ fontSize: 'clamp(12px, 1vw, 20px)' }}
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.12, delayChildren: 2.2 } } }}
        >
          {[
            <span key="b" className="flex items-center gap-2 rounded-full border border-builder/30 bg-builder/[0.08] px-[0.9em] py-[0.35em] text-builder">
              <span className="h-[0.5em] w-[0.5em] rounded-full bg-builder shadow-[0_0_10px_#38bdf8]" /> Builder
            </span>,
            <span key="vs" className="text-slate-500">
              vs
            </span>,
            <span key="r" className="flex items-center gap-2 rounded-full border border-breaker/30 bg-breaker/[0.08] px-[0.9em] py-[0.35em] text-breaker">
              <span className="h-[0.5em] w-[0.5em] rounded-full bg-breaker shadow-[0_0_10px_#fb7185]" /> Breaker
            </span>,
            <span key="m" className="rounded-full border border-white/10 bg-white/[0.04] px-[0.9em] py-[0.35em] text-slate-300">
              one frozen model
            </span>,
          ].map((node, i) => (
            <motion.span key={i} variants={{ hidden: { opacity: 0, y: 8, scale: 0.95 }, show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.5, ease } } }}>
              {node}
            </motion.span>
          ))}
        </motion.div>
      </div>

      {/* team names, bottom-left: the bottom-right corner stays empty for the webcam bubble */}
      {team.length > 0 && (
        <motion.div
          className="absolute bottom-[8vh] left-[5vw] right-[5vw] flex flex-wrap items-center gap-x-[2vw] gap-y-3 md:right-[340px]"
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.15, delayChildren: 2.6 } } }}
        >
          <motion.span variants={{ hidden: { opacity: 0 }, show: { opacity: 1 } }} className="eyebrow" style={{ fontSize: 'clamp(11px, 0.8vw, 16px)' }}>
            Built by
          </motion.span>
          {team.map((m) => (
            <motion.span
              key={m.name}
              variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0, transition: { duration: 0.6, ease } } }}
              className="flex items-center gap-3 text-white"
              style={{ fontSize: 'clamp(16px, 1.5vw, 30px)' }}
            >
              {m.photo ? (
                <span className="rounded-full p-[2px]" style={{ background: 'linear-gradient(135deg, #38bdf8, #fb7185)' }}>
                  <img src={m.photo} alt="" className="block h-[2.2em] w-[2.2em] rounded-full border-2 border-[#07080c] object-cover" />
                </span>
              ) : (
                <span className="rounded-full p-[1.5px]" style={{ background: 'linear-gradient(135deg, rgba(56,189,248,0.8), rgba(251,113,133,0.8))' }}>
                  <span className="grid h-[2.2em] w-[2.2em] place-items-center rounded-full bg-[#0c0e14] text-[0.62em] font-semibold tracking-wide text-slate-200">
                    {m.name
                      .split(/\s+/)
                      .map((p) => p[0])
                      .slice(0, 2)
                      .join('')
                      .toUpperCase()}
                  </span>
                </span>
              )}
              {m.name}
            </motion.span>
          ))}
        </motion.div>
      )}
    </div>
  )
}

/* ---------- 2. The problem ---------- */


export function SceneProblem({ t }: SceneProps) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center px-[6vw]">
      <div className="eyebrow mb-[4vh]" style={{ fontSize: 'clamp(11px, 0.9vw, 18px)' }}>
        How chip companies work today
      </div>
      <div className="flex w-full max-w-[1500px] flex-col items-center justify-center gap-4 sm:flex-row sm:items-stretch sm:gap-[3vw]">
        <TeamCard
          side="left"
          visible={at(t, 0.3)}
          color="#38bdf8"
          icon={<Hammer className="h-[1em] w-[1em]" />}
          title="Design engineers"
          verb="build"
          line="write the chip design"
          t={t - 0.3}
        />
        <motion.div
          className="flex shrink-0 items-center"
          initial={{ opacity: 0, scale: 0.5 }}
          animate={at(t, 1.0) ? { opacity: 1, scale: [1.4, 1] } : { opacity: 0, scale: 0.5 }}
          transition={{ duration: 0.5 }}
        >
          <span
            className="grid place-items-center rounded-full border border-white/15 bg-[#0c0e14] font-mono font-semibold text-slate-300"
            style={{
              fontSize: 'clamp(16px, 1.6vw, 32px)',
              width: '2.8em',
              height: '2.8em',
              boxShadow: '-14px 0 40px -18px #38bdf8, 14px 0 40px -18px #fb7185, inset 0 1px 0 rgba(255,255,255,0.06)',
            }}
          >
            vs
          </span>
        </motion.div>
        <TeamCard
          side="right"
          visible={at(t, 0.5)}
          color="#fb7185"
          icon={<Bug className="h-[1em] w-[1em]" />}
          title="Verification engineers"
          verb="break"
          line="try to make it fail"
          t={t - 0.5}
        />
      </div>
    </div>
  )
}

function TeamCard({ side, visible, color, icon, title, verb, line, t }: { side: 'left' | 'right'; visible: boolean; color: string; icon: ReactNode; title: string; verb: string; line: string; t: number }) {
  const bars = side === 'left'
  return (
    <motion.div
      className="glass-strong relative w-full flex-1 overflow-hidden p-5 sm:p-[2.2vw]"
      style={{ maxWidth: 620, boxShadow: `0 0 0 1px ${color}40, 0 0 120px -40px ${color}` }}
      initial={{ opacity: 0, x: side === 'left' ? -120 : 120 }}
      animate={visible ? { opacity: 1, x: 0 } : { opacity: 0, x: side === 'left' ? -120 : 120 }}
      transition={{ type: 'spring', stiffness: 90, damping: 18 }}
    >
      <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full opacity-25 blur-3xl" style={{ background: color }} />
      <div className="relative flex items-center gap-3" style={{ color, fontSize: 'clamp(20px, 2vw, 40px)' }}>
        {icon}
        <span className="font-mono font-semibold uppercase tracking-[0.2em]" style={{ fontSize: '0.6em' }}>
          {verb}
        </span>
      </div>
      <div className="relative mt-[1.5vh] font-semibold tracking-tight text-white" style={{ fontSize: 'clamp(22px, 2.6vw, 54px)' }}>
        {title}
      </div>
      <div className="relative mt-1 text-slate-400" style={{ fontSize: 'clamp(14px, 1.3vw, 26px)' }}>
        {line}
      </div>
      {/* tiny illustration */}
      <div className="relative mt-[3vh] h-[9vh] min-h-[56px]">
        {bars ? (
          <div className="flex h-full flex-col justify-between">
            {[0.82, 0.55, 0.7, 0.4].map((w, i) => (
              <motion.div
                key={i}
                className="h-[14%] rounded-full"
                style={{ background: `${color}${i === 0 ? '' : '88'}` }}
                initial={{ width: 0 }}
                animate={{ width: t > 0.4 + i * 0.25 ? `${w * 100}%` : 0 }}
                transition={{ duration: 0.7, ease }}
              />
            ))}
          </div>
        ) : (
          <svg viewBox="0 0 300 60" className="h-full w-full" preserveAspectRatio="none">
            <motion.path
              d="M0 45 L40 45 L40 15 L90 15 L90 45 L130 45 L130 15 L170 15 L170 45 L300 45"
              fill="none"
              stroke="#94a3b8"
              strokeWidth="2.5"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: t > 0.4 ? 1 : 0 }}
              transition={{ duration: 1.2 }}
            />
            <motion.path
              d="M170 45 L170 15 L215 15 L215 45"
              fill="none"
              stroke={color}
              strokeWidth="3.5"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: t > 1.1 ? 1 : 0, opacity: t > 1.1 ? 1 : 0 }}
              transition={{ duration: 0.5 }}
              style={{ filter: `drop-shadow(0 0 6px ${color})` }}
            />
            {t > 1.3 && <motion.rect x="165" y="2" width="56" height="56" rx="6" fill={`${color}22`} stroke={color} initial={{ opacity: 0 }} animate={{ opacity: [0, 1, 0.6] }} transition={{ duration: 0.8 }} />}
          </svg>
        )}
      </div>
    </motion.div>
  )
}

/* ---------- 3. Arms race ---------- */

export function SceneArmsRace({ t, data }: SceneProps) {
  const series = data.series
  const pointsN = series?.points?.length ?? 0
  // the chart needs two scored rounds to draw a line (the engine writes null rates until a version is scored)
  const scoredN = (series?.points ?? []).filter((p) => typeof p.builder_val_pass === 'number' || typeof p.breaker_pool_catch === 'number').length
  const progress = Math.max(0, Math.min(1, (t - 0.9) / 10.6))
  const maxRound = Math.max(1, ...(series?.points ?? []).map((p) => p.round))
  const round = Math.floor(progress * maxRound + 1e-6)
  const humans = data.state?.human_interventions ?? 0
  const recent = useMemo(() => {
    const list = (series?.changes ?? []).filter((c) => c.round <= round && c.round > 0)
    return list.slice(-2).reverse()
  }, [series, round])

  if (pointsN < 2 || scoredN < 2) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-6 px-[6vw] text-center">
        <LogoMark size={96} />
        <div className="font-semibold text-white" style={{ fontSize: 'clamp(24px, 3vw, 60px)' }}>
          Two AI teams fight. Coaches rewrite their playbooks.
        </div>
        <div className="text-slate-400" style={{ fontSize: 'clamp(16px, 1.5vw, 30px)' }}>
          The arms race chart fills in as rounds complete.
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full w-full flex-col px-[5vw] pb-[6vh] pt-[7vh]">
      <div className="flex items-start justify-between gap-6">
        <div>
          <div className="eyebrow" style={{ fontSize: 'clamp(11px, 0.9vw, 18px)' }}>
            The arms race
          </div>
          <div className="mt-2 font-semibold tracking-tight text-white" style={{ fontSize: 'clamp(24px, 3vw, 60px)' }}>
            <span className="text-builder text-glow-builder">Builder</span> vs <span className="text-breaker text-glow-breaker">Breaker</span>, round by round
          </div>
          <div className="mt-3 flex flex-wrap gap-x-[2vw] gap-y-1 text-slate-400" style={{ fontSize: 'clamp(12px, 1.1vw, 22px)' }}>
            <span className="flex items-center gap-2">
              <span className="h-[3px] w-8 rounded-full bg-builder" /> Builder · validation pass rate
            </span>
            <span className="flex items-center gap-2">
              <span className="h-[3px] w-8 rounded-full bg-breaker" /> Breaker · bug-pool catch rate
            </span>
            <span className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-slate-300" /> kept
            </span>
            <span className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full border-2 border-slate-400" /> rejected
            </span>
          </div>
        </div>
        <motion.div
          className="glass-strong shrink-0 px-[1.4vw] py-[1.2vh] text-right"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <div className="font-mono font-semibold text-white" style={{ fontSize: 'clamp(20px, 2.2vw, 44px)' }}>
            Round{' '}
            <AnimatePresence mode="popLayout">
              <motion.span key={round} className="inline-block" initial={{ y: -14, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 14, opacity: 0 }}>
                {round}
              </motion.span>
            </AnimatePresence>
          </div>
          <div className="flex items-center justify-end gap-2 font-mono text-pass" style={{ fontSize: 'clamp(12px, 1.1vw, 22px)' }}>
            <span className="h-2 w-2 rounded-full bg-pass shadow-[0_0_8px_#34d399]" />
            {humans} human interventions
          </div>
        </motion.div>
      </div>

      <div className="relative mt-[3vh] min-h-0 flex-1">
        {series && <ArmsRaceDraw series={series} progress={progress} />}
      </div>

      {/* change ticker: the two newest coach proposals under the pen; right side stays clear for the webcam bubble */}
      <div className="mt-[1.5vh] flex min-h-[48px] flex-col gap-[0.8vh] md:pr-[300px]" style={{ height: 'calc(2 * clamp(13px, 1.15vw, 23px) * 2.1 + 0.8vh)' }}>
        <AnimatePresence mode="popLayout" initial={false}>
          {recent.map((c) => {
            const color = teamColor(c.team)
            return (
              <motion.div
                key={`${c.round}-${c.team}-${c.summary}`}
                layout
                initial={{ opacity: 0, x: -24, filter: 'blur(4px)' }}
                animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
                exit={{ opacity: 0, x: 12 }}
                transition={{ duration: 0.45, ease }}
                className="flex min-w-0 max-w-full items-center gap-[0.7em] self-start rounded-full border bg-black/40 py-[0.35em] pl-[0.45em] pr-[0.9em] backdrop-blur"
                style={{ fontSize: 'clamp(13px, 1.15vw, 23px)', borderColor: c.accepted ? `${color}55` : 'rgba(255,255,255,0.08)' }}
              >
                <span
                  className="grid h-[1.3em] w-[1.3em] shrink-0 place-items-center rounded-full"
                  style={{ background: c.accepted ? color : 'transparent', border: `2px solid ${color}`, boxShadow: c.accepted ? `0 0 12px ${color}` : undefined }}
                >
                  {c.accepted ? <Check className="h-[0.75em] w-[0.75em] text-black" strokeWidth={3.5} /> : <X className="h-[0.75em] w-[0.75em]" style={{ color }} strokeWidth={3.5} />}
                </span>
                <span className="shrink-0 font-mono text-slate-500">R{c.round}</span>
                <span className="shrink-0 font-medium" style={{ color }}>
                  {teamName(c.team)}
                </span>
                <span className={cx('min-w-0 truncate', c.accepted ? 'text-slate-100' : 'text-slate-500 line-through decoration-slate-600')}>{c.summary}</span>
                <span
                  className={cx(
                    'shrink-0 rounded-full px-[0.5em] font-mono text-[0.85em] font-semibold',
                    c.net_flips > 0 ? 'bg-pass/15 text-pass' : c.net_flips < 0 ? 'bg-breaker/15 text-breaker' : 'bg-white/5 text-slate-500',
                  )}
                >
                  {c.net_flips > 0 ? '+' : ''}
                  {c.net_flips}
                </span>
                <span className={cx('shrink-0 text-[0.75em] font-semibold uppercase tracking-wider', c.accepted ? 'text-pass' : 'text-slate-500')}>
                  {c.accepted ? 'kept' : c.net_flips > 0 && data.series?.gate_margin ? `rejected · needs +${data.series.gate_margin}` : 'rejected'}
                </span>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}

/* ---------- 4. Breaker at test time ---------- */

export function SceneSelection({ t, data }: SceneProps) {
  const ex = pickDemoExample(data.selection?.examples)
  const local = t - 1.4
  if (!ex) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-[3vh] px-[6vw] text-center">
        <div className="eyebrow" style={{ fontSize: 'clamp(11px, 0.9vw, 18px)' }}>
          Breaker at test time
        </div>
        <div className="font-semibold text-white" style={{ fontSize: 'clamp(24px, 3.2vw, 64px)' }}>
          No answer key. The Breaker decides.
        </div>
        <div className="flex items-center gap-[2vw] font-mono text-slate-400" style={{ fontSize: 'clamp(14px, 1.4vw, 28px)' }}>
          <span>5 drafts</span>
          <span className="text-breaker">→ Breaker finds where they disagree →</span>
          <span className="text-pass">survivor ships</span>
        </div>
        <div className="text-slate-500" style={{ fontSize: 'clamp(12px, 1vw, 20px)' }}>
          Selection examples appear after the final exam.
        </div>
      </div>
    )
  }
  return (
    <div className="flex h-full w-full flex-col items-center px-[5vw] pt-[7vh]">
      <motion.div className="text-center" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }}>
        <div className="eyebrow flex items-center justify-center gap-2" style={{ fontSize: 'clamp(11px, 0.9vw, 18px)' }}>
          <Crosshair className="h-[1.1em] w-[1.1em] text-breaker" /> Held-out problem · never seen · no answer key
        </div>
        <div className="mt-2 font-mono font-semibold text-white" style={{ fontSize: 'clamp(24px, 2.8vw, 56px)' }}>
          {ex.problem_id}
        </div>
        {/* real specs can run for paragraphs: two lines is enough on stage */}
        <div className="mx-auto mt-2 line-clamp-2 max-w-[1100px] text-slate-400" style={{ fontSize: 'clamp(14px, 1.25vw, 25px)' }} title={ex.spec}>
          {ex.spec}
        </div>
      </motion.div>
      <div className="mt-[5.5vh] w-full max-w-[1500px]">
        <SelectionStage example={ex} t={Math.max(0, local)} variant="demo" />
      </div>
      <motion.div
        className="mt-[1vh] font-semibold text-slate-200"
        style={{ fontSize: 'clamp(16px, 1.6vw, 32px)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: local > 8.8 ? 1 : 0 }}
        transition={{ duration: 0.6 }}
      >
        No answer key. <span className="text-breaker">The Breaker decides.</span>
      </motion.div>
    </div>
  )
}

/* ---------- 5. Final exam ---------- */

export function SceneFinal({ t, data }: SceneProps) {
  const final = data.final
  const bars = mainBars(final)
  const tv0 = metric(final, 'transfer_v0')
  const tvb = metric(final, 'transfer_vbest')
  const showTransfer = !!tv0 && !!tvb && tvb.pass - tv0.pass >= 0.02  // only show a clear gain on stage
  if (!bars.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-[6vw] text-center">
        <div className="eyebrow" style={{ fontSize: 'clamp(11px, 0.9vw, 18px)' }}>
          Final exam
        </div>
        <div className="font-semibold text-white" style={{ fontSize: 'clamp(24px, 3vw, 60px)' }}>
          Scored on problems it has never seen.
        </div>
        <div className="text-slate-400" style={{ fontSize: 'clamp(14px, 1.4vw, 28px)' }}>
          The final exam runs after the last round.
        </div>
      </div>
    )
  }
  const barH = typeof window !== 'undefined' ? Math.max(220, Math.min(560, window.innerHeight * 0.44)) : 420
  return (
    <div className="flex h-full w-full flex-col px-[5vw] pb-[8vh] pt-[7vh]">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }}>
        <div className="eyebrow" style={{ fontSize: 'clamp(11px, 0.9vw, 18px)' }}>
          Final exam · held-out split
        </div>
        <div className="mt-2 font-semibold tracking-tight text-white" style={{ fontSize: 'clamp(24px, 3vw, 60px)' }}>
          {final?.test_problems ? `${final.test_problems} unseen problems.` : 'Unseen problems.'} <span className="text-slate-400">Same frozen model.</span>
        </div>
      </motion.div>
      <div className="mt-[3vh] flex min-h-0 flex-1 flex-col items-stretch gap-6 md:flex-row md:items-start md:gap-[4vw]">
        <div className="w-full min-w-0 flex-1 pt-[2vh] md:w-auto md:self-center md:pt-[5vh]">
          <ExamBars bars={bars} height={barH} size={typeof window !== 'undefined' && window.innerWidth < 768 ? 'md' : 'xl'} startDelay={0.5} stepDelay={1.0} />
        </div>
        <AnimatePresence>
          {showTransfer && at(t, 5.6) && (
            <motion.div
              className="glass-strong w-full shrink-0 p-5 md:w-[26vw] md:min-w-[260px] md:max-w-[480px] md:p-[1.8vw]"
              style={{ boxShadow: '0 0 0 1px rgba(52,211,153,0.35), 0 0 120px -40px #34d399' }}
              initial={{ opacity: 0, x: 60, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              transition={{ type: 'spring', stiffness: 120, damping: 18 }}
            >
              <div className="flex items-center gap-2 text-pass" style={{ fontSize: 'clamp(12px, 1vw, 20px)' }}>
                <Repeat className="h-[1.1em] w-[1.1em]" />
                <span className="font-semibold uppercase tracking-[0.18em]" style={{ fontSize: '0.8em' }}>
                  Transfer to a different AI
                </span>
              </div>
              <div className="mt-[2vh] space-y-[1.6vh]">
                <TransferRow label={tv0!.label} value={tv0!.pass} dim />
                <TransferRow label={tvb!.label} value={tvb!.pass} />
              </div>
              <div className="mt-[2vh] font-mono font-semibold text-pass" style={{ fontSize: 'clamp(18px, 2vw, 40px)' }}>
                {pts(tvb!.pass - tv0!.pass)}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

function TransferRow({ label, value, dim }: { label: string; value: number; dim?: boolean }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3" style={{ fontSize: 'clamp(13px, 1.1vw, 22px)' }}>
        <span className={dim ? 'text-slate-400' : 'text-white'}>{label}</span>
        <span className={cx('font-mono font-semibold', dim ? 'text-slate-400' : 'text-white')}>{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="mt-1.5 h-[1.2vh] min-h-[8px] overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          className="h-full rounded-full"
          style={{ background: dim ? 'rgba(148,163,184,0.6)' : 'linear-gradient(90deg,#38bdf8,#34d399)' }}
          initial={{ width: 0 }}
          animate={{ width: `${value * 100}%` }}
          transition={{ delay: dim ? 0.2 : 0.6, duration: 1, ease }}
        />
      </div>
    </div>
  )
}

/* ---------- 6. Closer ---------- */

export function SceneCloser({ data }: SceneProps) {
  const cfg = data.demoConfig
  // "The team got better" only when kept changes AND a held-out gain back it up
  const anyKept = (data.lineage?.entries ?? []).some((e) => e.accepted)
  const better = anyKept && improved(data.final)
  const repo = cfg?.repo_url && !/\.\.\.$/.test(cfg.repo_url) ? cfg.repo_url.replace(/^https?:\/\//, '') : null
  return (
    <div className="flex h-full w-full flex-col items-center justify-center px-[6vw] text-center">
      <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.6, ease }}>
        <LogoMark size={Math.round(Math.min(150, Math.max(72, window.innerWidth * 0.06)))} />
      </motion.div>
      <motion.div
        className="mt-[2vh] font-semibold tracking-[0.2em] text-white"
        style={{ fontSize: 'clamp(22px, 2.6vw, 52px)' }}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.6 }}
      >
        {(cfg?.project || 'Shadowbox').toUpperCase()}
      </motion.div>
      <motion.div
        className="mt-[5vh] max-w-[1400px] font-semibold leading-tight tracking-tight text-white"
        style={{ fontSize: 'clamp(28px, 4.2vw, 84px)' }}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35, duration: 0.8, ease }}
      >
        <span className="block">The model stayed frozen.</span>
        <span className="block bg-gradient-to-r from-builder via-white to-breaker bg-clip-text pb-[0.08em] text-transparent">
          {better ? 'The team got better.' : 'Every change had to earn its place.'}
        </span>
      </motion.div>
      {repo && (
        <motion.div
          className="mt-[5vh] rounded-full border border-white/10 bg-white/[0.04] px-[1.6vw] py-[1vh] font-mono text-slate-300"
          style={{ fontSize: 'clamp(14px, 1.4vw, 28px)' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.0, duration: 0.6 }}
        >
          {repo}
        </motion.div>
      )}
    </div>
  )
}
