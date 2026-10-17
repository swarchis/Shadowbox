import { AnimatePresence, motion } from 'framer-motion'
import { ChevronLeft, ChevronRight, Maximize2, Pause, Play, RotateCcw, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ComponentType, type ReactNode } from 'react'
import { DataBadge } from '../../components/Badges'
import { useData } from '../../lib/DataContext'
import { cx } from '../../lib/format'
import { SceneArmsRace, SceneCloser, SceneFinal, SceneIntro, SceneProblem, SceneSelection, type SceneProps } from './scenes'

interface SceneDef {
  id: string
  label: string
  dur: number
  C: ComponentType<SceneProps>
}

/** The six scenes of DEMO_SCRIPT.md: 8 + 10 + 14 + 14 + 10 + 4 = 60 seconds (TOTAL below). */
// The recorded demo uses only "The problem"; the rest of the story is shown on the live dashboard (replay).
// To bring a scene back, move it from ALL_SCENES into SCENES.
export const ALL_SCENES: SceneDef[] = [
  { id: 'intro', label: 'Intro', dur: 8, C: SceneIntro },
  { id: 'problem', label: 'The problem', dur: 3, C: SceneProblem },
  { id: 'arms', label: 'Arms race', dur: 14, C: SceneArmsRace },
  { id: 'select', label: 'Breaker at test time', dur: 14, C: SceneSelection },
  { id: 'final', label: 'Final exam', dur: 10, C: SceneFinal },
  { id: 'closer', label: 'Closer', dur: 4, C: SceneCloser },
]
export const SCENES: SceneDef[] = ALL_SCENES.filter((s) => s.id === 'problem')

export const TOTAL = SCENES.reduce((a, s) => a + s.dur, 0)
const START_OF = SCENES.map((_, i) => SCENES.slice(0, i).reduce((a, s) => a + s.dur, 0))
const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`

export function DemoMode({ onExit, startScene = 0, startAt = 0, startPaused = false }: { onExit: () => void; startScene?: number; startAt?: number; startPaused?: boolean }) {
  const data = useData()
  const [idx, setIdx] = useState(() => Math.max(0, Math.min(SCENES.length - 1, startScene)))
  const [t, setT] = useState(() => Math.max(0, startAt))
  const [paused, setPaused] = useState(startPaused)
  const [chrome, setChrome] = useState(true)
  const idxRef = useRef(idx)
  const tRef = useRef(Math.max(0, startAt))
  const pausedRef = useRef(startPaused)
  const hideTimer = useRef<number | undefined>(undefined)

  const goTo = useCallback((i: number) => {
    const n = Math.max(0, Math.min(SCENES.length - 1, i))
    idxRef.current = n
    tRef.current = 0
    setIdx(n)
    setT(0)
  }, [])

  const togglePause = useCallback(() => {
    pausedRef.current = !pausedRef.current
    setPaused(pausedRef.current)
  }, [])

  // scene clock
  useEffect(() => {
    let raf = 0
    let last = performance.now()
    const loop = (now: number) => {
      const dt = Math.min(0.1, Math.max(0, (now - last) / 1000))
      last = now
      if (!pausedRef.current) {
        const dur = SCENES[idxRef.current].dur
        tRef.current += dt
        if (tRef.current >= dur) {
          if (idxRef.current < SCENES.length - 1) {
            idxRef.current += 1
            tRef.current = 0
            setIdx(idxRef.current)
          } else {
            tRef.current = dur
          }
        }
        setT(tRef.current)
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])

  // keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      // a focused control handles its own Space / Enter (otherwise Space on "Pause" would also skip a scene)
      const el = e.target as HTMLElement | null
      if ((e.key === ' ' || e.key === 'Enter') && el?.closest('button')) return
      switch (e.key) {
        case 'ArrowRight':
        case ' ':
        case 'PageDown':
          e.preventDefault()
          if (idxRef.current < SCENES.length - 1) goTo(idxRef.current + 1)
          break
        case 'ArrowLeft':
        case 'PageUp':
          e.preventDefault()
          goTo(idxRef.current - 1)
          break
        case 'p':
        case 'P':
          togglePause()
          break
        case 'Escape':
          if (!document.fullscreenElement) onExit()
          break
        case 'r':
        case 'R':
          goTo(0)
          break
        case 'f':
        case 'F':
          if (document.fullscreenElement) document.exitFullscreen?.().catch(() => undefined)
          else document.documentElement.requestFullscreen?.().catch(() => undefined)
          break
        default:
          if (/^[1-6]$/.test(e.key)) goTo(Number(e.key) - 1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [goTo, togglePause, onExit])

  // hide controls + cursor when idle, so the recording is clean
  const poke = useCallback(() => {
    setChrome(true)
    window.clearTimeout(hideTimer.current)
    hideTimer.current = window.setTimeout(() => setChrome(false), 1800)
  }, [])
  useEffect(() => {
    poke()
    return () => window.clearTimeout(hideTimer.current)
  }, [poke])

  // drop focus from whatever opened the demo, so Space can't re-click it
  useEffect(() => {
    const el = document.activeElement
    if (el instanceof HTMLElement) el.blur()
  }, [])

  // lock page scroll underneath
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [])

  const scene = SCENES[idx]
  const Scene = scene.C
  const ended = idx === SCENES.length - 1 && t >= scene.dur
  const mock = data.state?.mode === 'mock'
  const fixtures = data.source === 'fixtures'
  const offline = data.source === 'offline'

  return (
    <motion.div
      className={cx('fixed inset-0 z-50 overflow-hidden bg-[#07080c] text-slate-200', !chrome && 'cursor-none')}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
      onMouseMove={poke}
      role="dialog"
      aria-label="Shadowbox demo"
    >
      <DemoBackdrop sceneIdx={idx} />

      <AnimatePresence>
        <motion.div
          key={scene.id}
          className="absolute inset-0"
          initial={{ opacity: 0, y: 30, scale: 0.985, filter: 'blur(10px)' }}
          animate={{ opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, y: -24, scale: 1.01, filter: 'blur(8px)' }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        >
          <Scene t={t} data={data} />
        </motion.div>
      </AnimatePresence>

      {/* data badges, top-left */}
      {(mock || fixtures || offline) && (
        <div className="absolute left-5 top-5 flex gap-2">
          {mock && <DataBadge kind="mock" />}
          {fixtures && <DataBadge kind="fixtures" />}
          {offline && <DataBadge kind="offline" />}
        </div>
      )}

      {/* paused indicator */}
      <AnimatePresence>
        {paused && (
          <motion.div
            className="absolute left-1/2 top-5 -translate-x-1/2 rounded-full border border-white/10 bg-black/60 px-3 py-1 text-xs text-slate-300 backdrop-blur"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            Paused · press P
          </motion.div>
        )}
      </AnimatePresence>

      {/* controls (only while the mouse moves) */}
      <AnimatePresence>
        {chrome && (
          <motion.div
            className="absolute right-5 top-5 flex items-center gap-1 rounded-xl border border-white/10 bg-black/50 p-1 text-slate-300 backdrop-blur"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            <span className="hidden items-center gap-2 px-2 text-xs text-slate-400 sm:flex">
              <span>
                {idx + 1}/{SCENES.length} · {scene.label}
              </span>
              <span className="num rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-slate-300" title="Elapsed / total">
                {clock(Math.min(TOTAL, START_OF[idx] + t))} / {clock(TOTAL)}
              </span>
            </span>
            <CtlButton label="Previous (←)" onClick={() => goTo(idx - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </CtlButton>
            <CtlButton label={paused ? 'Resume (P)' : 'Pause (P)'} onClick={togglePause}>
              {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            </CtlButton>
            <CtlButton label="Next (→ / Space)" onClick={() => idx < SCENES.length - 1 && goTo(idx + 1)}>
              <ChevronRight className="h-4 w-4" />
            </CtlButton>
            <CtlButton label="Restart (R)" onClick={() => goTo(0)}>
              <RotateCcw className="h-4 w-4" />
            </CtlButton>
            <CtlButton
              label="Fullscreen (F)"
              onClick={() => (document.fullscreenElement ? document.exitFullscreen?.() : document.documentElement.requestFullscreen?.())?.catch(() => undefined)}
            >
              <Maximize2 className="h-4 w-4" />
            </CtlButton>
            <CtlButton label="Exit (Esc)" onClick={onExit}>
              <X className="h-4 w-4" />
            </CtlButton>
          </motion.div>
        )}
      </AnimatePresence>

      {/* progress: one thin bar per scene, sized by duration; the button is taller than the bar so it is easy to hit */}
      <div className="absolute inset-x-0 bottom-0 flex gap-1 px-1">
        {SCENES.map((s, i) => {
          const frac = i < idx ? 1 : i > idx ? 0 : Math.min(1, t / s.dur)
          return (
            <button
              key={s.id}
              className="group relative flex h-3 items-end pb-1"
              style={{ flexGrow: s.dur, flexBasis: 0 }}
              onClick={() => goTo(i)}
              aria-label={`Go to scene ${i + 1}: ${s.label}`}
              title={`${i + 1}. ${s.label} (${s.dur}s)`}
            >
              <span className="relative block h-[3px] w-full overflow-hidden rounded-full bg-white/10 transition-[height] group-hover:h-[5px]">
                <span
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ width: `${frac * 100}%`, background: 'linear-gradient(90deg, #38bdf8, #fb7185)', opacity: ended ? 0.5 : 1 }}
                />
              </span>
            </button>
          )
        })}
      </div>
    </motion.div>
  )
}

function CtlButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} title={label} aria-label={label} className="rounded-lg p-2 hover:bg-white/10 hover:text-white">
      {children}
    </button>
  )
}

/** Slowly drifting team-colored glows behind every scene. */
function DemoBackdrop({ sceneIdx }: { sceneIdx: number }) {
  const positions = [
    { b: ['30%', '45%'], r: ['70%', '55%'] },
    { b: ['20%', '40%'], r: ['80%', '40%'] },
    { b: ['15%', '70%'], r: ['85%', '30%'] },
    { b: ['30%', '30%'], r: ['70%', '70%'] },
    { b: ['25%', '60%'], r: ['75%', '60%'] },
    { b: ['40%', '50%'], r: ['60%', '50%'] },
  ]
  const p = positions[sceneIdx % positions.length]
  return (
    <div className="pointer-events-none absolute inset-0">
      <motion.div
        className="absolute h-[70vmax] w-[70vmax] -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(56,189,248,0.16), transparent 60%)' }}
        animate={{ left: p.b[0], top: p.b[1] }}
        transition={{ duration: 2.4, ease: [0.16, 1, 0.3, 1] }}
      />
      <motion.div
        className="absolute h-[70vmax] w-[70vmax] -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(251,113,133,0.14), transparent 60%)' }}
        animate={{ left: p.r[0], top: p.r[1] }}
        transition={{ duration: 2.4, ease: [0.16, 1, 0.3, 1] }}
      />
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          maskImage: 'radial-gradient(ellipse at 50% 45%, black 10%, transparent 70%)',
          WebkitMaskImage: 'radial-gradient(ellipse at 50% 45%, black 10%, transparent 70%)',
        }}
      />
    </div>
  )
}
