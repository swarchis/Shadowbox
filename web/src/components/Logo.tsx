import { motion } from 'framer-motion'
import { useId } from 'react'

/** Two overlapping "fighters": builder diamond (cyan) and breaker diamond (rose). */
export function LogoMark({ size = 28, animated = false, className = '' }: { size?: number; animated?: boolean; className?: string }) {
  const id = `lm${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" className={className} style={{ overflow: 'visible' }} aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-b`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7dd3fc" />
          <stop offset="1" stopColor="#0ea5e9" />
        </linearGradient>
        <linearGradient id={`${id}-r`} x1="1" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fda4af" />
          <stop offset="1" stopColor="#f43f5e" />
        </linearGradient>
      </defs>
      <motion.g
        initial={animated ? { x: -12, opacity: 0 } : false}
        animate={{ x: 0, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 140, damping: 14, delay: animated ? 0.15 : 0 }}
      >
        <rect x="5" y="11" width="18" height="18" rx="4.5" transform="rotate(45 14 20)" fill={`url(#${id}-b)`} opacity={0.95} />
      </motion.g>
      <motion.g
        initial={animated ? { x: 12, opacity: 0 } : false}
        animate={{ x: 0, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 140, damping: 14, delay: animated ? 0.25 : 0 }}
        style={{ mixBlendMode: 'screen' }}
      >
        <rect x="17" y="11" width="18" height="18" rx="4.5" transform="rotate(45 26 20)" fill={`url(#${id}-r)`} opacity={0.9} />
      </motion.g>
    </svg>
  )
}

export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`font-semibold tracking-[0.22em] text-white ${className}`}>
      SHADOW<span className="text-slate-400">BOX</span>
    </span>
  )
}
