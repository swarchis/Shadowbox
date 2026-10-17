import { motion } from 'framer-motion'
import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'

export function EmptyState({ title = 'Waiting for the first round...', hint, icon, compact }: { title?: ReactNode; hint?: ReactNode; icon?: ReactNode; compact?: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className={`flex flex-col items-center justify-center text-center ${compact ? 'gap-2 py-8' : 'gap-3 py-16'}`}
    >
      <div className="relative grid h-10 w-10 place-items-center rounded-full border border-white/10 bg-white/[0.03] text-slate-400">
        {icon ?? <Loader2 className="h-4 w-4 motion-safe:animate-spin" />}
        <span className="absolute inset-0 rounded-full border border-builder/30 motion-safe:animate-pulse-ring" />
      </div>
      <div className="text-sm font-medium text-slate-300">{title}</div>
      {hint && <div className="max-w-sm text-xs leading-relaxed text-slate-500">{hint}</div>}
    </motion.div>
  )
}
