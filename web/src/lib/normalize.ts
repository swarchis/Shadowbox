// Response normalizers: coerce whatever the API (or a half-written engine file) returns into
// the shapes in types.ts, so views can trust that arrays are arrays and objects are objects.
// Every function accepts `unknown` and never throws. Unknown extra keys are kept.
//
// These mirror the server's own defaults (server/api.py) and also cover an older server, a
// proxy error page, or a field the engine left null.

import type {
  DemoCase,
  DemoCases,
  DemoConfig,
  DemoVersionCode,
  EventsPage,
  FinalExam,
  FinalMetric,
  Lineage,
  LineageEntry,
  MatchProblem,
  MatchSummary,
  PlaybookDetail,
  PlaybookIndex,
  RoundMatch,
  RoundsList,
  RunEvent,
  RunState,
  SelectionExample,
  SelectionExamples,
  Series,
  SeriesPoint,
  Team,
  Trace,
  TraceRow,
  VersionPair,
} from '../types'

type Obj = Record<string, unknown>

const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v)
const obj = (v: unknown): Obj => (isObj(v) ? v : {})
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const objs = (v: unknown): Obj[] => arr(v).filter(isObj)
const strs = (v: unknown): string[] => arr(v).filter((x): x is string => typeof x === 'string')
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const numOr = (v: unknown, d: number): number => num(v) ?? d
const str = (v: unknown, d = ''): string => (typeof v === 'string' ? v : v === null || v === undefined ? d : String(v))
const strOrNull = (v: unknown): string | null => (typeof v === 'string' ? v : null)
const bool = (v: unknown): boolean => v === true
const team = (v: unknown): Team | null => (v === 'builder' || v === 'breaker' ? v : null)
const strMap = (v: unknown): Record<string, string> => {
  const out: Record<string, string> = {}
  for (const [k, x] of Object.entries(obj(v))) if (x !== null && x !== undefined) out[k] = String(x)
  return out
}

const STALE_MS = 5 * 60 * 1000 // the engine refreshes updated_at at least every 30 s while it works

export function normState(v: unknown): RunState {
  const s = obj(v)
  const splits = obj(s.splits)
  const st = normStateRaw(s, splits)
  // A "running" state with no update for 5 minutes means the engine was killed without saying so:
  // never show a dead run as live.
  const updated = st.updated_at ? Date.parse(st.updated_at) : NaN
  if (st.status === 'running' && !st.replay && Number.isFinite(updated) && Date.now() - updated > STALE_MS) {
    const mins = Math.round((Date.now() - updated) / 60000)
    return { ...st, status: 'stopped', message: `No activity from the engine for ${mins} min; it may have been stopped. Rerun the same command to resume.` }
  }
  return st
}

function normStateRaw(s: Record<string, unknown>, splits: Record<string, unknown>): RunState {
  return {
    ...(s as object),
    mode: s.mode === 'real' ? 'real' : 'mock',
    status: (typeof s.status === 'string' ? s.status : 'idle') as RunState['status'],
    phase: (typeof s.phase === 'string' ? s.phase : 'setup') as RunState['phase'],
    round: numOr(s.round, 0),
    step: typeof s.step === 'string' ? s.step : null,
    message: str(s.message),
    started_at: strOrNull(s.started_at),
    updated_at: strOrNull(s.updated_at),
    deadline_at: strOrNull(s.deadline_at),
    spend_usd: numOr(s.spend_usd, 0),
    spend_cap_usd: numOr(s.spend_cap_usd, 0),
    llm_calls: numOr(s.llm_calls, 0),
    human_interventions: numOr(s.human_interventions, 0),
    builder_version: numOr(s.builder_version, 0),
    breaker_version: numOr(s.breaker_version, 0),
    splits: { train: numOr(splits.train, 0), val: numOr(splits.val, 0), test: numOr(splits.test, 0) },
  }
}

export function normSeries(v: unknown): Series {
  const s = obj(v)
  const points: SeriesPoint[] = objs(s.points)
    .filter((p) => num(p.round) !== null)
    .map((p) => ({
      ...(p as object),
      round: num(p.round) as number,
      builder_val_pass: num(p.builder_val_pass),
      breaker_pool_catch: num(p.breaker_pool_catch),
      builder_train_pass: num(p.builder_train_pass),
      builder_hard_pass: num(p.builder_hard_pass),
      builder_version: numOr(p.builder_version, 0),
      breaker_version: numOr(p.breaker_version, 0),
    }))
  const changes = objs(s.changes)
    .filter((c) => team(c.team))
    .map((c) => ({ ...(c as object), round: numOr(c.round, 0), team: team(c.team) as Team, accepted: bool(c.accepted), summary: str(c.summary), net_flips: numOr(c.net_flips, 0) }))
  return { ...(s as object), points, changes, gate_margin: num(s.gate_margin), distinct_bugs: num(s.distinct_bugs), distinct_subtle_bugs: num(s.distinct_subtle_bugs) }
}

function normEntry(e: Obj, i: number): LineageEntry {
  return {
    ...(e as object),
    id: str(e.id, `entry-${i}`),
    round: numOr(e.round, 0),
    team: team(e.team) ?? 'builder',
    change_type: str(e.change_type) as LineageEntry['change_type'],
    summary: str(e.summary),
    reasoning: str(e.reasoning),
    evidence_problems: strs(e.evidence_problems),
    score_before: num(e.score_before),
    score_after: num(e.score_after),
    gained: strs(e.gained),
    lost: strs(e.lost),
    net_flips: num(e.net_flips),
    accepted: bool(e.accepted),
    from_version: numOr(e.from_version, 0),
    new_version: num(e.new_version),
    tool_name: strOrNull(e.tool_name),
    cost_usd: numOr(e.cost_usd, 0),
    ts: str(e.ts),
  }
}

export function normLineage(v: unknown): Lineage {
  const l = obj(v)
  return { ...(l as object), entries: objs(l.entries).filter((e) => team(e.team)).map(normEntry) }
}

function normSummary(v: unknown): MatchSummary {
  const s = obj(v)
  return {
    ...(s as object),
    train_pass: num(s.train_pass),
    hard_pass: num(s.hard_pass),
    bugs_found: num(s.bugs_found),
    subtle_bugs: num(s.subtle_bugs),
    problems: num(s.problems),
  }
}

export function normRounds(v: unknown): RoundsList {
  const r = obj(v)
  return {
    ...(r as object),
    rounds: objs(r.rounds)
      .filter((x) => num(x.round) !== null)
      .map((x) => ({
        ...normSummary(x),
        round: num(x.round) as number,
        complete: bool(x.complete),
        builder_version: num(x.builder_version),
        breaker_version: num(x.breaker_version),
      })),
  }
}

function normProblem(p: Obj): MatchProblem {
  const official = obj(p.official)
  const build = obj(p.build)
  const attack = isObj(p.attack) ? p.attack : null
  const fm = attack && isObj(attack.first_mismatch) ? attack.first_mismatch : null
  return {
    ...(p as object),
    problem_id: str(p.problem_id),
    spec: str(p.spec),
    is_sequential: bool(p.is_sequential),
    official: { ...(official as object), passed: bool(official.passed), kind: str(official.kind), mismatches: numOr(official.mismatches, 0), samples: numOr(official.samples, 0) },
    hard_pass: bool(p.hard_pass),
    build: {
      ...(build as object),
      code: str(build.code),
      compiled: bool(build.compiled),
      attempts: numOr(build.attempts, 1),
      steps: objs(build.steps).map((s) => ({ agent: str(s.agent), summary: str(s.summary) })),
      tool_reports: objs(build.tool_reports).map((t) => ({ ...(t as object), tool: str(t.tool), fired: bool(t.fired), findings: strs(t.findings) })),
    },
    attack: attack
      ? {
          ...(attack as object),
          stimulus_cycles: numOr(attack.stimulus_cycles, 0),
          valid_bug: bool(attack.valid_bug),
          caught_by_official: bool(attack.caught_by_official),
          first_mismatch: fm
            ? {
                cycle: numOr(fm.cycle, 0),
                phase: str(fm.phase),
                signal: str(fm.signal),
                expected: str(fm.expected),
                got: str(fm.got),
                inputs: obj(fm.inputs) as Record<string, number | string>,
              }
            : null,
        }
      : null,
  }
}

export function normMatch(v: unknown, n: number): RoundMatch {
  const m = obj(v)
  return {
    ...(m as object),
    round: numOr(m.round, n),
    builder_version: num(m.builder_version),
    breaker_version: num(m.breaker_version),
    summary: normSummary(m.summary),
    problems: objs(m.problems).filter((p) => typeof p.problem_id === 'string').map(normProblem),
  }
}

export function normPlaybookIndex(v: unknown, t: Team): PlaybookIndex {
  const p = obj(v)
  const versions = objs(p.versions)
    .filter((x) => num(x.version) !== null)
    .map((x) => ({ ...(x as object), version: num(x.version) as number, parent: num(x.parent), rules: numOr(x.rules, 0), tools: numOr(x.tools, 0), created_round: num(x.created_round) }))
  const fallback = versions.length ? versions[versions.length - 1].version : 0
  return { ...(p as object), team: t, current: numOr(p.current, fallback), versions }
}

export function normPlaybook(v: unknown, t: Team, version: number): PlaybookDetail {
  const p = obj(v)
  const toolStats: PlaybookDetail['tool_stats'] = {}
  for (const [k, x] of Object.entries(obj(p.tool_stats))) {
    if (!isObj(x)) continue
    toolStats[k] = { ...(x as object), runs: numOr(x.runs, 0), fired: numOr(x.fired, 0), born_round: num(x.born_round) }
  }
  const params: PlaybookDetail['params'] = {}
  for (const [k, x] of Object.entries(obj(p.params))) {
    if (typeof x === 'number' || typeof x === 'string' || typeof x === 'boolean') params[k] = x
    else if (x !== null && x !== undefined) params[k] = JSON.stringify(x)
  }
  return {
    ...(p as object),
    version: numOr(p.version, version),
    parent: num(p.parent),
    team: t,
    prompts: strMap(p.prompts),
    rules: strs(p.rules),
    tools: strs(p.tools),
    params,
    tool_sources: strMap(p.tool_sources),
    tool_stats: toolStats,
  }
}

function normMetric(v: unknown): FinalMetric | null {
  if (!isObj(v)) return null
  const pass = num(v.pass)
  if (pass === null) return null
  const ci = arr(v.ci)
  const lo = num(ci[0])
  const hi = num(ci[1])
  return { ...(v as object), label: str(v.label), pass, ci: lo !== null && hi !== null ? [lo, hi] : null, n: numOr(v.n, 0) }
}

const pair = (v: unknown): VersionPair => {
  const p = obj(v)
  return { v0: num(p.v0), vbest: num(p.vbest) }
}

export function normFinal(v: unknown): FinalExam {
  const f = obj(v)
  const metrics: FinalExam['metrics'] = {}
  for (const [k, x] of Object.entries(obj(f.metrics))) (metrics as Record<string, FinalMetric | null>)[k] = normMetric(x)
  return {
    ...(f as object),
    complete: bool(f.complete),
    test_problems: num(f.test_problems),
    metrics,
    builder_versions: pair(f.builder_versions),
    breaker_versions: pair(f.breaker_versions),
    cost_usd: num(f.cost_usd),
    notes: strs(f.notes),
  }
}

function normExample(e: Obj): SelectionExample {
  const drafts = objs(e.drafts)
    .filter((d) => typeof d.label === 'string')
    .map((d) => ({ ...(d as object), label: d.label as string, code: str(d.code), compiled: bool(d.compiled), official_pass: bool(d.official_pass) }))
  const groups = arr(e.groups)
    .map(strs)
    .filter((g) => g.length)
  const disputed = isObj(e.disputed) ? e.disputed : null
  const outputs: Record<string, Record<string, string>> = {}
  if (disputed) for (const [k, x] of Object.entries(obj(disputed.outputs))) outputs[k] = strMap(x)
  const cg = num(e.chosen_group)
  return {
    ...(e as object),
    problem_id: str(e.problem_id),
    spec: str(e.spec),
    drafts,
    groups,
    chosen_group: cg !== null && cg >= 0 && cg < groups.length ? cg : null,
    chosen_label: strOrNull(e.chosen_label),
    chosen_correct: bool(e.chosen_correct),
    decided_by: str(e.decided_by, 'none'),
    judge_reasoning: strOrNull(e.judge_reasoning),
    disputed: disputed
      ? { ...(disputed as object), cycle: numOr(disputed.cycle, 0), phase: str(disputed.phase), inputs: obj(disputed.inputs) as Record<string, number | string>, outputs }
      : null,
    stimulus_cycles: numOr(e.stimulus_cycles, 0),
  }
}

export function normSelection(v: unknown): SelectionExamples {
  const s = obj(v)
  return { ...(s as object), examples: objs(s.examples).filter((e) => typeof e.problem_id === 'string').map(normExample) }
}

function normVersionCode(v: unknown): DemoVersionCode {
  const c = obj(v)
  return { ...(c as object), version: c.version === 'selection' ? 'selection' : numOr(c.version, 0), code: str(c.code), official_pass: bool(c.official_pass) }
}

function normTrace(v: unknown): Trace | null {
  if (!isObj(v)) return null
  const rows: TraceRow[] = objs(v.rows).map((r, i) => ({
    ...(r as object),
    t: numOr(r.t, i),
    inputs: strMap(r.inputs),
    expected: strMap(r.expected),
    v0: strMap(r.v0),
    vbest: strMap(r.vbest),
  }))
  const signals = objs(v.signals)
    .filter((s) => typeof s.name === 'string')
    .map((s) => ({
      ...(s as object),
      name: s.name as string,
      kind: (s.kind === 'clock' || s.kind === 'input' ? s.kind : 'output') as 'clock' | 'input' | 'output',
      width: num(s.width) ?? undefined,
    }))
  const fm = num(v.first_mismatch_row)
  return { ...(v as object), signals, rows, first_mismatch_row: fm !== null && fm >= 0 && fm < rows.length ? fm : null }
}

function normCase(c: Obj): DemoCase {
  const e = isObj(c.explanation) ? c.explanation : null
  return {
    ...(c as object),
    problem_id: str(c.problem_id),
    spec: str(c.spec),
    v0: normVersionCode(c.v0),
    vbest: normVersionCode(c.vbest),
    explanation: e ? { ...(e as object), round: num(e.round), summary: str(e.summary), reasoning: str(e.reasoning) } : null,
    trace: normTrace(c.trace),
  }
}

export function normDemoCases(v: unknown): DemoCases {
  const d = obj(v)
  return { ...(d as object), cases: objs(d.cases).filter((c) => typeof c.problem_id === 'string').map(normCase) }
}

export function normDemoConfig(v: unknown): DemoConfig {
  const d = obj(v)
  return {
    ...(d as object),
    project: str(d.project) || 'Shadowbox',
    tagline: str(d.tagline) || 'AI teams that get better by fighting themselves',
    team: objs(d.team)
      .map((m) => ({ name: str(m.name).trim(), photo: strOrNull(m.photo) }))
      .filter((m) => m.name),
    repo_url: strOrNull(d.repo_url),
  }
}

export function normEvents(v: unknown): EventsPage {
  const p = obj(v)
  const events: RunEvent[] = objs(p.events)
    .filter((e) => num(e.seq) !== null)
    .map((e) => ({ ...(e as object), seq: num(e.seq) as number, ts: str(e.ts), type: str(e.type), round: num(e.round), team: team(e.team), message: str(e.message) }))
  return { events, next: numOr(p.next, events.length ? Math.max(...events.map((e) => e.seq)) + 1 : 0) }
}
