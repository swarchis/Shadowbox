import { useEffect, useRef, useState } from 'react'
import { Pause, Play, RotateCcw } from 'lucide-react'
import { useData } from '../lib/DataContext'
import { useNow } from '../lib/hooks'

function clock(s: number): string {
  const t = Math.max(0, Math.floor(s))
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`
}

/** Full-width progress bar for a replayed run: recorded time elapsed, total, and playback speed.
 *  Between polls the position is advanced locally at the replay speed so the bar moves smoothly. */
export function ReplayBar() {
  const { state } = useData()
  const [busy, setBusy] = useState(false)
  // the dashboard polls every few seconds; show a click's effect right away until the server confirms it
  const [override, setOverride] = useState<boolean | null>(null)
  const replay = state?.replay
  const now = useNow(200)
  const anchor = useRef<{ at: number; elapsed: number }>({ at: Date.now(), elapsed: 0 })
  const elapsedFromServer = replay?.elapsed_s ?? 0
  const serverPlaying = !!replay?.playing
  useEffect(() => {
    anchor.current = { at: Date.now(), elapsed: elapsedFromServer }
  }, [elapsedFromServer, serverPlaying])
  useEffect(() => {
    if (override === serverPlaying) setOverride(null)
  }, [override, serverPlaying])
  if (!replay || !replay.total_s) return null
  const total = replay.total_s
  const playing = override ?? serverPlaying
  const elapsed = Math.min(total, anchor.current.elapsed + (playing ? ((now - anchor.current.at) / 1000) * replay.speed : 0))
  const frac = total > 0 ? elapsed / total : 0
  const done = frac >= 0.999
  const send = async (action: 'play' | 'pause' | 'restart') => {
    setBusy(true)
    try {
      await fetch(`/api/replay/${action}`, { method: 'POST' })
    } catch {
      /* the next poll shows the offline badge if the API is down */
    }
    if (action === 'restart') {
      window.location.reload() // the feed and chart start over from an empty run
      return
    }
    anchor.current = { at: Date.now(), elapsed }
    setOverride(action === 'play')
    setBusy(false)
  }
  const btn = 'inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 font-semibold uppercase tracking-wider disabled:opacity-50' 
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02]">
      <div className="flex items-center gap-3 px-4 py-2.5 font-mono text-[11px]">
        {done ? (
          <button disabled={busy} onClick={() => send('restart')} className={`${btn} border-sky-400/40 bg-sky-400/10 text-sky-200 hover:bg-sky-400/20`}>
            <RotateCcw className="h-3 w-3" /> Replay again
          </button>
        ) : playing ? (
          <button disabled={busy} onClick={() => send('pause')} className={`${btn} border-white/15 bg-white/[0.05] text-slate-200 hover:bg-white/10`}>
            <Pause className="h-3 w-3" /> Pause
          </button>
        ) : (
          <button disabled={busy} onClick={() => send('play')} className={`${btn} border-emerald-400/40 bg-emerald-400/15 text-emerald-200 hover:bg-emerald-400/25`}>
            <Play className="h-3 w-3 fill-current" /> {elapsed > 0 ? 'Resume' : 'Play'}
          </button>
        )}
        {!done && elapsed > 0 && (
          <button disabled={busy} onClick={() => send('restart')} title="Back to the start (paused)" aria-label="Back to the start"
            className="shrink-0 rounded-md border border-white/10 p-1 text-slate-400 hover:bg-white/10 hover:text-slate-200 disabled:opacity-50">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
        <span className="shrink-0 font-semibold uppercase tracking-wider text-sky-300">
          Replay · {replay.speed}× speed
        </span>
        <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.07]" role="progressbar" aria-valuenow={Math.round(frac * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Replay progress">
          <div
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ width: `${frac * 100}%`, background: 'linear-gradient(90deg, #38bdf8, #fb7185)', boxShadow: '0 0 12px rgba(56,189,248,0.5)' }}
          />
        </div>
        <span className="num shrink-0 text-slate-300">
          {clock(elapsed)} <span className="text-slate-500">/ {clock(total)}</span>
          <span className="ml-2 text-slate-500">{done ? 'recorded run complete' : playing ? 'recorded run time' : 'paused'}</span>
        </span>
      </div>
    </div>
  )
}
