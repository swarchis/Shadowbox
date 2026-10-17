import { motion, type HTMLMotionProps } from 'framer-motion'
import type { ReactNode } from 'react'
import { cx } from '../lib/format'

export const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] } },
}

export const stagger = (gap = 0.07, delay = 0) => ({
  hidden: {},
  show: { transition: { staggerChildren: gap, delayChildren: delay } },
})

interface CardProps extends HTMLMotionProps<'div'> {
  glow?: string
  strong?: boolean
}

export function Card({ glow, strong, className, children, style, ...rest }: CardProps) {
  return (
    <motion.div
      variants={fadeUp}
      className={cx(strong ? 'glass-strong' : 'glass', 'relative overflow-hidden', className as string)}
      style={{
        ...(glow ? { boxShadow: `0 0 0 1px ${glow}22, 0 0 60px -20px ${glow}55, inset 0 1px 0 0 rgba(255,255,255,0.05)` } : {}),
        ...style,
      }}
      {...rest}
    >
      {children}
    </motion.div>
  )
}

export function CardHeader({ eyebrow, title, right, className }: { eyebrow?: ReactNode; title?: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <div className={cx('flex flex-wrap items-start justify-between gap-x-3 gap-y-2', className)}>
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        {title && <h3 className="text-base font-semibold tracking-tight text-white sm:text-lg">{title}</h3>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  )
}
