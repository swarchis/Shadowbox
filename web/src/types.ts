// Types mirroring docs/CONTRACT.md exactly. CONTRACT.md is the source of truth:
// if a shape changes there, change it here.

export type Mode = 'mock' | 'real'
export type RunStatus = 'idle' | 'running' | 'finished' | 'error' | 'stopped'
export type Phase = 'setup' | 'bug_pool' | 'round' | 'final' | 'done'
export type Step = 'match' | 'builder_coach' | 'builder_gate' | 'breaker_coach' | 'breaker_gate' | 'done'
/**
 * The engine also writes steps outside a round (e.g. "baseline", "bug_pool", "final", "selection")
 * and null before the run starts, so the UI must accept any string here.
 */
export type AnyStep = Step | (string & {})
export type Team = 'builder' | 'breaker'
export type ChangeType = 'prompt_edit' | 'rule_add' | 'rule_remove' | 'tool_add' | 'tool_remove' | 'param' | 'memory_add'

/** Verilog bit string, e.g. "0101"; may contain x / z. */
export type Bits = string

// ---------- GET /api/state ----------
export interface RunState {
  mode: Mode
  status: RunStatus
  phase: Phase
  round: number
  step: AnyStep | null
  message: string
  started_at: string | null
  updated_at: string | null
  deadline_at: string | null
  spend_usd: number
  spend_cap_usd: number
  llm_calls: number
  human_interventions: number
  builder_version: number
  breaker_version: number
  splits: { train: number; val: number; test: number }
}

// ---------- GET /api/series ----------
/** Rates are null until the engine has scored that version (round 0 never has train/hard rates). */
export interface SeriesPoint {
  round: number
  builder_val_pass: number | null
  breaker_pool_catch: number | null
  builder_train_pass: number | null
  builder_hard_pass: number | null
  builder_version: number
  breaker_version: number
}

export interface SeriesChange {
  round: number
  team: Team
  accepted: boolean
  summary: string
  net_flips: number
}

export interface Series {
  points: SeriesPoint[]
  changes: SeriesChange[]
  gate_margin?: number | null
  distinct_bugs?: number | null
  distinct_subtle_bugs?: number | null
}

// ---------- GET /api/lineage ----------
export interface LineageEntry {
  id: string
  round: number
  team: Team
  change_type: ChangeType
  summary: string
  reasoning: string
  evidence_problems: string[]
  score_before: number | null
  /** null when the proposal was invalid and never gated */
  score_after: number | null
  gained: string[]
  lost: string[]
  net_flips: number | null
  accepted: boolean
  from_version: number
  new_version: number | null
  tool_name: string | null
  cost_usd: number
  ts: string
}

export interface Lineage {
  entries: LineageEntry[]
}

// ---------- GET /api/rounds ----------
/** Fields are null while the round's match.json has not been written yet. */
export interface RoundSummary {
  round: number
  complete: boolean
  builder_version: number | null
  breaker_version: number | null
  train_pass: number | null
  hard_pass: number | null
  bugs_found: number | null
  subtle_bugs: number | null
  problems: number | null
}

export interface RoundsList {
  rounds: RoundSummary[]
}

// ---------- GET /api/rounds/{n}/match ----------
export interface OfficialResult {
  passed: boolean
  kind: string
  mismatches: number
  samples: number
}

export interface BuildStep {
  agent: string
  summary: string
}

export interface ToolReport {
  tool: string
  fired: boolean
  findings: string[]
}

export interface BuildResult {
  code: string
  compiled: boolean
  attempts: number
  steps: BuildStep[]
  tool_reports: ToolReport[]
}

export interface FirstMismatch {
  cycle: number
  phase: string
  signal: string
  expected: Bits
  got: Bits
  inputs: Record<string, number | string>
}

export interface AttackResult {
  stimulus_cycles: number
  valid_bug: boolean
  caught_by_official: boolean
  first_mismatch: FirstMismatch | null
}

export interface MatchProblem {
  problem_id: string
  spec: string
  is_sequential: boolean
  official: OfficialResult
  hard_pass: boolean
  build: BuildResult
  attack: AttackResult | null
}

export interface MatchSummary {
  train_pass: number | null
  hard_pass: number | null
  bugs_found: number | null
  subtle_bugs: number | null
  problems: number | null
}

export interface RoundMatch {
  round: number
  builder_version: number | null
  breaker_version: number | null
  summary: MatchSummary
  problems: MatchProblem[]
}

// ---------- GET /api/playbooks/{team} ----------
export interface PlaybookVersionInfo {
  version: number
  parent: number | null
  rules: number
  tools: number
  created_round: number | null
}

export interface PlaybookIndex {
  team: Team
  current: number
  versions: PlaybookVersionInfo[]
}

// ---------- GET /api/playbooks/{team}/{version} ----------
export interface ToolStat {
  runs: number
  fired: number
  /** null when the engine recorded runs before it knew the birth round */
  born_round: number | null
  errors?: number
}

export interface PlaybookDetail {
  version: number
  parent: number | null
  team: Team
  prompts: Record<string, string>
  rules: string[]
  tools: string[]
  params: Record<string, number | string | boolean>
  tool_sources: Record<string, string>
  tool_stats: Record<string, ToolStat>
}

// ---------- GET /api/final ----------
export interface FinalMetric {
  label: string
  pass: number
  ci: [number, number] | null
  n: number
}

export type FinalMetricKey =
  | 'v0'
  | 'vbest'
  | 'vbest_selection'
  | 'random_pick'
  | 'random_input_sel'
  | 'breaker_v0_sel'
  | 'ceiling'
  | 'ultra'
  | 'transfer_v0'
  | 'transfer_vbest'
  | 'ablation_nano_coach'
  | 'ablation_main_coach'

export interface VersionPair {
  v0: number | null
  vbest: number | null
}

/** Before the final exam runs, the server returns every metric as null and the other numbers as null. */
export interface FinalExam {
  complete: boolean
  test_problems: number | null
  metrics: Partial<Record<FinalMetricKey, FinalMetric | null>>
  builder_versions: VersionPair
  breaker_versions: VersionPair
  cost_usd: number | null
  notes: string[]
}

// ---------- GET /api/selection-examples ----------
export interface SelectionDraft {
  label: string
  code: string
  compiled: boolean
  official_pass: boolean
}

export interface DisputedInput {
  cycle: number
  phase: string
  inputs: Record<string, number | string>
  /** keyed by draft label, then by output signal */
  outputs: Record<string, Record<string, Bits>>
}

/** The engine can also write "fallback" (nothing distinguished the drafts), so accept any string. */
export type DecidedBy = 'majority' | 'judge' | 'single' | 'none' | (string & {})

export interface SelectionExample {
  problem_id: string
  spec: string
  drafts: SelectionDraft[]
  groups: string[][]
  /** null when no draft compiled (decided_by "none") */
  chosen_group: number | null
  chosen_label: string | null
  chosen_correct: boolean
  decided_by: DecidedBy
  judge_reasoning: string | null
  disputed: DisputedInput | null
  stimulus_cycles: number
}

export interface SelectionExamples {
  examples: SelectionExample[]
}

// ---------- GET /api/demo-cases ----------
export interface DemoVersionCode {
  /** "selection" when the engine fell back to Breaker-selected drafts (label it "Latest + Breaker") */
  version: number | 'selection'
  code: string
  official_pass: boolean
}

export type TraceSignalKind = 'clock' | 'input' | 'output'

export interface TraceSignal {
  name: string
  kind: TraceSignalKind
  width?: number
}

export interface TraceRow {
  t: number
  inputs: Record<string, Bits>
  expected: Record<string, Bits>
  v0: Record<string, Bits>
  vbest: Record<string, Bits>
}

export interface Trace {
  signals: TraceSignal[]
  rows: TraceRow[]
  first_mismatch_row: number | null
  /** where the inputs came from: the Breaker's attack, or random inputs when the attack exposed nothing */
  source?: 'breaker' | 'random'
}

export interface DemoCase {
  problem_id: string
  spec: string
  v0: DemoVersionCode
  vbest: DemoVersionCode
  explanation: {
    round: number | null
    summary: string
    reasoning: string
    kind?: 'builder' | 'selection'
    changes?: { round: number | null; summary: string }[]
  } | null
  trace: Trace | null
}

export interface DemoCases {
  cases: DemoCase[]
}

// ---------- GET /api/demo-config ----------
export interface TeamMember {
  name: string
  photo: string | null
}

export interface DemoConfig {
  project: string
  tagline: string
  team: TeamMember[]
  repo_url: string | null
}

// ---------- GET /api/events?since=<n> ----------
export interface RunEvent {
  seq: number
  ts: string
  type: string
  round: number | null
  team: Team | null
  message: string
}

export interface EventsPage {
  events: RunEvent[]
  next: number
}

// ---------- GET /api/live ----------
export interface LivePort {
  name: string
  direction: 'input' | 'output' | string
  width: number
}

export interface LiveItem {
  problem_id: string
  spec: string
  ports: LivePort[]
  code: string | null
  compiled: boolean | null
  attempts: number | null
  /** grade from the official testbench: the agents never see it */
  official: { passed: boolean; kind: string | null } | null
  attack: {
    cycles: number | null
    found_bug: boolean
    first_mismatch: { cycle?: number; phase?: string; signal?: string; expected?: string; got?: string; inputs?: Record<string, number> } | null
    stimulus: Record<string, string>[] | null
  } | null
  tools: { tool: string; fired?: boolean; findings?: string[] }[]
  error: string | null
}

export interface LiveFeed {
  source: string | null
  label: string | null
  team: Team | null
  updated_at: string | null
  items: LiveItem[]
}
