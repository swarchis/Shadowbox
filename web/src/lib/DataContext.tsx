import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  fetchDemoCases,
  fetchDemoConfig,
  fetchEvents,
  fetchFinal,
  fetchLineage,
  fetchPlaybook,
  fetchPlaybookIndex,
  fetchRoundMatch,
  fetchRounds,
  fetchSelectionExamples,
  fetchSeries,
  fetchState,
  getSource,
  onSourceChange,
  type DataSource,
} from '../api'
import type {
  DemoCases,
  DemoConfig,
  FinalExam,
  Lineage,
  PlaybookDetail,
  PlaybookIndex,
  RoundMatch,
  RoundsList,
  RunEvent,
  RunState,
  SelectionExamples,
  Series,
  Team,
} from '../types'

export interface TeamPlaybooks {
  index: PlaybookIndex | null
  current: PlaybookDetail | null
}

export interface DataValue {
  loaded: boolean
  source: DataSource
  state: RunState | null
  series: Series | null
  lineage: Lineage | null
  rounds: RoundsList | null
  latestMatch: RoundMatch | null
  playbooks: Record<Team, TeamPlaybooks>
  final: FinalExam | null
  selection: SelectionExamples | null
  demoCases: DemoCases | null
  demoConfig: DemoConfig | null
  /** newest first */
  events: RunEvent[]
}

const EMPTY: DataValue = {
  loaded: false,
  source: getSource(),
  state: null,
  series: null,
  lineage: null,
  rounds: null,
  latestMatch: null,
  playbooks: { builder: { index: null, current: null }, breaker: { index: null, current: null } },
  final: null,
  selection: null,
  demoCases: null,
  demoConfig: null,
  events: [],
}

const DataCtx = createContext<DataValue>(EMPTY)

export const useData = () => useContext(DataCtx)

const FAST_MS = 3000
const SLOW_MS = 10000
const MAX_EVENTS = 200

async function loadTeam(team: Team): Promise<TeamPlaybooks> {
  const index = await fetchPlaybookIndex(team)
  const hasCurrent = index && typeof index.current === 'number' && (index.versions?.length ?? 0) > 0
  const current = hasCurrent ? await fetchPlaybook(team, index.current) : null
  return { index, current }
}

export function DataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<DataValue>(EMPTY)
  // Only replace a slice when its content changed, so charts don't re-animate on every poll.
  const lastJson = useRef<Record<string, string>>({})
  const patch = (p: Partial<DataValue>) => {
    const changed: Partial<DataValue> = {}
    let any = false
    for (const [k, v] of Object.entries(p) as [keyof DataValue, unknown][]) {
      const json = k === 'events' ? `events:${(v as RunEvent[]).length}:${(v as RunEvent[])[0]?.seq ?? ''}` : JSON.stringify(v)
      if (lastJson.current[k] === json) continue
      lastJson.current[k] = json
      ;(changed as Record<string, unknown>)[k] = v
      any = true
    }
    if (any) setData((d) => ({ ...d, ...changed }))
  }

  const slowKey = useRef<string>('')
  const nextSeq = useRef(0)
  const eventsSource = useRef<DataSource | null>(null)
  const eventsRef = useRef<RunEvent[]>([])

  useEffect(() => onSourceChange((source) => patch({ source })), [])

  useEffect(() => {
    let alive = true
    let timer: number | undefined

    const loadSlow = async () => {
      const [lineage, rounds, final, selection, demoCases, builder, breaker] = await Promise.all([
        fetchLineage(),
        fetchRounds(),
        fetchFinal(),
        fetchSelectionExamples(),
        fetchDemoCases(),
        loadTeam('builder'),
        loadTeam('breaker'),
      ])
      const done = (rounds?.rounds ?? []).filter((r) => r.complete)
      const latest = done.length ? done[done.length - 1].round : null
      const latestMatch = latest !== null ? await fetchRoundMatch(latest) : null
      if (!alive) return
      patch({ lineage, rounds, final, selection, demoCases, latestMatch, playbooks: { builder, breaker } })
    }

    const pollEvents = async () => {
      let page = await fetchEvents(nextSeq.current)
      const src = getSource()
      let changed = false
      if (eventsSource.current !== src || (page.next ?? 0) < nextSeq.current) {
        changed = true
        // data source flipped or the run restarted: start the feed over
        eventsSource.current = src
        eventsRef.current = []
        nextSeq.current = 0
        page = await fetchEvents(0)
      }
      const seen = new Set(eventsRef.current.map((e) => e.seq))
      const fresh = (page.events ?? []).filter((e) => !seen.has(e.seq))
      if (fresh.length) {
        changed = true
        eventsRef.current = [...eventsRef.current, ...fresh].sort((a, b) => b.seq - a.seq).slice(0, MAX_EVENTS)
      }
      nextSeq.current = Math.max(nextSeq.current, page.next ?? 0)
      if (!alive) return
      if (changed) patch({ events: eventsRef.current })
    }

    const tick = async () => {
      try {
        const state = await fetchState()
        if (!alive) return
        patch({ state })
        const key = [
          state?.status,
          state?.phase,
          state?.round,
          state?.step,
          state?.builder_version,
          state?.breaker_version,
          getSource(),
        ].join('|')
        const jobs: Promise<unknown>[] = [fetchSeries().then((series) => alive && patch({ series })), pollEvents()]
        if (key !== slowKey.current) {
          // only remember the key once the slow data actually loaded, so a failed load is retried
          jobs.push(loadSlow().then(() => {
            slowKey.current = key
          }))
        }
        await Promise.allSettled(jobs)
        if (alive) patch({ loaded: true, source: getSource() })
        timer = window.setTimeout(tick, state?.status === 'running' ? FAST_MS : SLOW_MS)
      } catch {
        // API offline: keep the last real data on screen, show the badge, retry soon
        if (alive) {
          patch({ loaded: true, source: getSource() })
          timer = window.setTimeout(tick, FAST_MS)
        }
      }
    }

    fetchDemoConfig()
      .then((demoConfig) => alive && patch({ demoConfig }))
      .catch(() => undefined)
    tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <DataCtx.Provider value={data}>{children}</DataCtx.Provider>
}
