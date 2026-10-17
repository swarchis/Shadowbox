// Typed fetchers for every endpoint in docs/CONTRACT.md.
//
// URLs are relative ("/api/..."): in dev, Vite proxies /api to FastAPI on :8000;
// in production, FastAPI serves web/dist at "/" next to the API.
//
// Sample data is shown ONLY with ?fixtures=1 (for UI work without an engine run).
// If the API is unreachable, fetchers throw ApiOfflineError: the app keeps showing the last
// real data it had, shows an API OFFLINE badge and keeps retrying. It never substitutes
// invented numbers on its own, so a hiccup during a demo can't put sample scores on screen.
//
// "Unreachable" means the request failed, timed out, or did not come back as JSON
// (e.g. the Vite proxy's error page). A JSON error from a live API (a 4xx/5xx on one
// endpoint) renders that endpoint's empty-but-valid shape, as CONTRACT.md requires.
//
// Every response, live or fixture, goes through src/lib/normalize.ts so views can rely
// on the shapes in types.ts even when the engine leaves a field null.

import type {
  DemoCases,
  DemoConfig,
  EventsPage,
  FinalExam,
  Lineage,
  PlaybookDetail,
  PlaybookIndex,
  RoundMatch,
  RoundsList,
  RunState,
  SelectionExamples,
  Series,
  Team,
} from './types'

import {
  normDemoCases,
  normDemoConfig,
  normEvents,
  normFinal,
  normLineage,
  normMatch,
  normPlaybook,
  normPlaybookIndex,
  normRounds,
  normSelection,
  normSeries,
  normState,
} from './lib/normalize'

import fxState from './fixtures/state.json'
import fxSeries from './fixtures/series.json'
import fxLineage from './fixtures/lineage.json'
import fxRounds from './fixtures/rounds.json'
import fxMatch from './fixtures/round_match.json'
import fxPbBuilder from './fixtures/playbooks_builder.json'
import fxPbBreaker from './fixtures/playbooks_breaker.json'
import fxPbBuilderCur from './fixtures/playbook_builder_current.json'
import fxPbBreakerCur from './fixtures/playbook_breaker_current.json'
import fxFinal from './fixtures/final.json'
import fxSelection from './fixtures/selection_examples.json'
import fxDemoCases from './fixtures/demo_cases.json'
import fxDemoConfig from './fixtures/demo_config.json'
import fxEvents from './fixtures/events.json'

export type DataSource = 'api' | 'fixtures' | 'offline'

const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : new URLSearchParams()
const fixturesParam = params.get('fixtures')
export const FORCE_FIXTURES = fixturesParam !== null && fixturesParam !== '0' && fixturesParam !== 'false'

let source: DataSource = FORCE_FIXTURES ? 'fixtures' : 'api'
const listeners = new Set<(s: DataSource) => void>()

function setSource(next: DataSource) {
  if (next === source) return
  source = next
  listeners.forEach((fn) => fn(next))
}

export function getSource(): DataSource {
  return source
}

export function onSourceChange(fn: (s: DataSource) => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function clone<T>(value: unknown): T {
  return JSON.parse(JSON.stringify(value)) as T
}

const TIMEOUT_MS = 6000

class ApiJsonError extends Error {}
export class ApiOfflineError extends Error {}

async function getJson<T>(path: string, fixture: () => unknown, norm: (raw: unknown) => T): Promise<T> {
  if (FORCE_FIXTURES) return norm(fixture())
  const ctrl = new AbortController()
  const timer = window.setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const res = await fetch(path, { headers: { Accept: 'application/json' }, signal: ctrl.signal, cache: 'no-store' })
    const type = res.headers.get('content-type') ?? ''
    if (!type.includes('json')) throw new Error(`${path}: not JSON (HTTP ${res.status})`)
    const data: unknown = await res.json()
    setSource('api')
    // the API is up but this endpoint errored: show its empty shape, not sample data
    if (!res.ok) throw new ApiJsonError(`${path}: HTTP ${res.status}`)
    return norm(data)
  } catch (err) {
    if (err instanceof ApiJsonError) return norm({})
    setSource('offline')
    throw new ApiOfflineError(err instanceof Error ? err.message : String(err))
  } finally {
    window.clearTimeout(timer)
  }
}

// ---------- endpoints ----------

export const fetchState = () => getJson<RunState>('/api/state', () => clone(fxState), normState)

export const fetchSeries = () => getJson<Series>('/api/series', () => clone(fxSeries), normSeries)

export const fetchLineage = () => getJson<Lineage>('/api/lineage', () => clone(fxLineage), normLineage)

export const fetchRounds = () => getJson<RoundsList>('/api/rounds', () => clone(fxRounds), normRounds)

export const fetchRoundMatch = (n: number) =>
  getJson<RoundMatch>(
    `/api/rounds/${encodeURIComponent(String(n))}/match`,
    () => ({ ...clone<RoundMatch>(fxMatch), round: n }),
    (raw) => normMatch(raw, n),
  )

export const fetchPlaybookIndex = (team: Team) =>
  getJson<PlaybookIndex>(`/api/playbooks/${team}`, () => clone(team === 'builder' ? fxPbBuilder : fxPbBreaker), (raw) => normPlaybookIndex(raw, team))

export const fetchPlaybook = (team: Team, version: number) =>
  getJson<PlaybookDetail>(
    `/api/playbooks/${team}/${encodeURIComponent(String(version))}`,
    () => clone(team === 'builder' ? fxPbBuilderCur : fxPbBreakerCur),
    (raw) => normPlaybook(raw, team, version),
  )

export const fetchFinal = () => getJson<FinalExam>('/api/final', () => clone(fxFinal), normFinal)

export const fetchSelectionExamples = () => getJson<SelectionExamples>('/api/selection-examples', () => clone(fxSelection), normSelection)

export const fetchDemoCases = () => getJson<DemoCases>('/api/demo-cases', () => clone(fxDemoCases), normDemoCases)

export const fetchDemoConfig = () => getJson<DemoConfig>('/api/demo-config', () => clone(fxDemoConfig), normDemoConfig)

export const fetchEvents = (since = 0) =>
  getJson<EventsPage>(
    `/api/events?since=${encodeURIComponent(String(since))}`,
    () => {
      const all = clone<EventsPage>(fxEvents)
      return { events: all.events.filter((e) => e.seq >= since), next: all.next }
    },
    normEvents,
  )
