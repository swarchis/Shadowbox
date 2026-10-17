import type { ChangeType, Phase, RunStatus, Step, Team } from '../types'

export const COLORS = {
  builder: '#38bdf8',
  breaker: '#fb7185',
  pass: '#34d399',
  fail: '#fb7185',
  amber: '#fbbf24',
  slate: '#94a3b8',
} as const

export const teamColor = (team: Team | null | undefined) =>
  team === 'breaker' ? COLORS.breaker : team === 'builder' ? COLORS.builder : COLORS.slate

export const teamName = (team: Team | null | undefined) =>
  team === 'breaker' ? 'Breaker' : team === 'builder' ? 'Builder' : 'System'

export function pct(x: number | null | undefined, digits = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '–'
  return `${(x * 100).toFixed(digits)}%`
}

export function pts(delta: number | null | undefined): string {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return '–'
  const v = Math.round(delta * 1000) / 10
  const s = Number.isInteger(v) ? v.toFixed(0) : v.toFixed(1)
  return `${v > 0 ? '+' : ''}${s} pts`
}

export function signed(n: number): string {
  return `${n > 0 ? '+' : ''}${n}`
}

export function money(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '$–'
  return `$${x.toFixed(2)}`
}

export const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  prompt_edit: 'Prompt edit',
  rule_add: 'New rule',
  rule_remove: 'Rule removed',
  tool_add: 'New tool',
  tool_remove: 'Tool removed',
  param: 'Parameter',
  memory_add: 'Memory',
}

export const STEP_LABEL: Record<Step, string> = {
  match: 'Match',
  builder_coach: 'Builder coach',
  builder_gate: 'Builder gate',
  breaker_coach: 'Breaker coach',
  breaker_gate: 'Breaker gate',
  done: 'Done',
}

/** Steps the engine writes outside a round (not in the contract's round-step list). */
const EXTRA_STEP_LABEL: Record<string, string> = {
  baseline: 'Baseline',
  bug_pool: 'Bug pool',
  breaker_baseline: 'Breaker baseline',
  final: 'Final exam',
  selection: 'Selection',
  demo_material: 'Demo cases',
}

/** Label for any step string, including ones the contract does not list. */
export function stepLabel(step: string | null | undefined): string {
  if (!step) return ''
  return (STEP_LABEL as Record<string, string>)[step] ?? EXTRA_STEP_LABEL[step] ?? step.replace(/_/g, ' ')
}

export const STEP_ORDER: Step[] = ['match', 'builder_coach', 'builder_gate', 'breaker_coach', 'breaker_gate', 'done']

/** Index of a round step in STEP_ORDER, or -1 for null / non-round steps. */
export const stepIndex = (step: string | null | undefined): number => (step ? (STEP_ORDER as string[]).indexOf(step) : -1)

/** Finite numbers only (drops the nulls the engine writes for not-yet-scored rates). */
export const finite = (xs: (number | null | undefined)[]): number[] => xs.filter((x): x is number => typeof x === 'number' && Number.isFinite(x))

export const PHASE_LABEL: Record<Phase, string> = {
  setup: 'Setup',
  bug_pool: 'Building bug pool',
  round: 'Self-play rounds',
  final: 'Final exam',
  done: 'Done',
}

export const STATUS_LABEL: Record<RunStatus, string> = {
  idle: 'Idle',
  running: 'Running',
  finished: 'Finished',
  error: 'Error',
  stopped: 'Stopped',
}

export function statusColor(status: RunStatus | undefined): string {
  switch (status) {
    case 'running':
      return COLORS.pass
    case 'finished':
      return COLORS.builder
    case 'error':
      return COLORS.fail
    case 'stopped':
      return COLORS.amber
    default:
      return COLORS.slate
  }
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 48) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}

export function clockTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export function duration(ms: number): string {
  if (!Number.isFinite(ms)) return '–'
  const neg = ms < 0
  let s = Math.floor(Math.abs(ms) / 1000)
  const h = Math.floor(s / 3600)
  s -= h * 3600
  const m = Math.floor(s / 60)
  s -= m * 60
  const body = h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
  return neg ? `-${body}` : body
}

/** Binary string (may contain x/z) to hex for display. */
export function bitsToHex(bits: string | undefined, width?: number): string {
  if (bits === undefined || bits === null) return '?'
  const b = String(bits).toLowerCase()
  if (/[xz]/.test(b)) {
    if (/^[x]+$/.test(b)) return 'x'
    if (/^[z]+$/.test(b)) return 'z'
    return 'x'
  }
  const w = width ?? b.length
  const n = parseInt(b, 2)
  if (Number.isNaN(n)) return b
  const digits = Math.max(1, Math.ceil(w / 4))
  return n.toString(16).padStart(digits, '0')
}

export function formatInputValue(v: number | string): string {
  if (typeof v === 'number') return String(v)
  if (/^[01xz]+$/i.test(v) && v.length > 1) return `${v}`
  return v
}

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
