import { animate, useReducedMotion } from 'framer-motion'
import { useEffect, useRef } from 'react'

interface Props {
  value: number
  format?: (v: number) => string
  duration?: number
  delay?: number
  className?: string
}

const DEFAULT_FORMAT = (v: number) => Math.round(v).toLocaleString()

/** A number that eases from its previous value to the new one. */
export function CountUp({ value, format = DEFAULT_FORMAT, duration = 1.2, delay = 0, className }: Props) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLSpanElement>(null)
  const current = useRef(0)
  const fmt = useRef(format)
  fmt.current = format

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const target = Number.isFinite(value) ? value : 0
    if (reduce) {
      current.current = target
      node.textContent = fmt.current(target)
      return
    }
    const controls = animate(current.current, target, {
      duration,
      delay,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        current.current = v
        node.textContent = fmt.current(v)
      },
    })
    return () => controls.stop()
  }, [value, duration, delay, reduce])

  return (
    <span ref={ref} className={`tabular-nums ${className ?? ''}`}>
      {fmt.current(reduce ? value : current.current)}
    </span>
  )
}
