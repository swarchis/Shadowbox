import { motion } from 'framer-motion'
import { CodeXml, Wrench } from 'lucide-react'
import { teamColor } from '../lib/format'
import type { Team, ToolStat } from '../types'
import { TeamChip } from './Badges'

export interface ToolInfo {
  name: string
  team: Team
  source: string | null
  stats: ToolStat | null
}

export function ToolCard({ tool, onOpen, index = 0 }: { tool: ToolInfo; onOpen: () => void; index?: number }) {
  const color = teamColor(tool.team)
  const runs = tool.stats?.runs ?? 0
  const fired = tool.stats?.fired ?? 0
  const rate = runs > 0 ? fired / runs : 0
  return (
    <motion.button
      onClick={onOpen}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 + index * 0.08, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -3 }}
      className="glass group relative flex w-[260px] shrink-0 flex-col overflow-hidden p-4 text-left sm:w-[290px]"
    >
      <div className="pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full opacity-20 blur-2xl transition-opacity group-hover:opacity-40" style={{ background: color }} />
      <div className="relative flex items-center justify-between">
        <span className="grid h-8 w-8 place-items-center rounded-lg border" style={{ color, borderColor: `${color}40`, background: `${color}14` }}>
          <Wrench className="h-4 w-4" />
        </span>
        <TeamChip team={tool.team} />
      </div>
      <div className="relative mt-3 font-mono text-base font-semibold text-white">{tool.name}</div>
      <div className="relative mt-0.5 text-xs text-slate-500">
        {tool.stats?.born_round != null ? `born in round ${tool.stats.born_round}` : 'agent-written tool'} · by the {tool.team} coach
      </div>
      <div className="relative mt-4 grid grid-cols-2 gap-2">
        <div>
          <div className="num text-lg font-semibold text-white">{runs}</div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">runs</div>
        </div>
        <div>
          <div className="num text-lg font-semibold" style={{ color }}>
            {fired}
          </div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">times fired</div>
        </div>
      </div>
      <div className="relative mt-3 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div className="h-full rounded-full" style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${rate * 100}%` }} transition={{ delay: 0.4 + index * 0.1, duration: 1 }} />
      </div>
      <div className="relative mt-auto flex items-center gap-1.5 pt-3 text-xs font-medium text-slate-400 group-hover:text-white">
        <CodeXml className="h-3.5 w-3.5" /> View source
      </div>
    </motion.button>
  )
}
