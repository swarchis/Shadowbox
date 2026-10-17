import { useEffect, useLayoutEffect, useRef, useState } from 'react'

/** Current time, re-rendered every `ms`. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(id)
  }, [ms])
  return now
}

export function useMediaQuery(query: string): boolean {
  const [match, setMatch] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : false))
  useEffect(() => {
    const mq = window.matchMedia(query)
    const fn = () => setMatch(mq.matches)
    fn()
    mq.addEventListener('change', fn)
    return () => mq.removeEventListener('change', fn)
  }, [query])
  return match
}

export function readLocal(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeLocal(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* storage unavailable: ignore */
  }
}

/**
 * Seconds elapsed since `resetKey` last changed, advanced with rAF while `running`.
 * Stops at `max`. Used to drive deterministic, pausable animations.
 */
export function useClock(running: boolean, resetKey: unknown, max = Number.POSITIVE_INFINITY): number {
  const [t, setT] = useState(0)
  const tRef = useRef(0)
  useEffect(() => {
    tRef.current = 0
    setT(0)
  }, [resetKey])
  useEffect(() => {
    if (!running) return
    let raf = 0
    let last = performance.now()
    const loop = (now: number) => {
      const dt = Math.min(0.1, Math.max(0, (now - last) / 1000))
      last = now
      tRef.current = Math.min(max, tRef.current + dt)
      setT(tRef.current)
      if (tRef.current < max) raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [running, resetKey, max])
  return t
}

/** Measures an element's content box synchronously on mount, then on every resize. */
export function useElementSize<T extends HTMLElement>(fallback: { w: number; h: number }) {
  const ref = useRef<T>(null)
  const [size, setSize] = useState(fallback)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      if (r.width > 0) setSize((s) => (Math.abs(s.w - r.width) < 0.5 && Math.abs(s.h - r.height) < 0.5 ? s : { w: r.width, h: r.height }))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [])
  return [ref, size] as const
}
