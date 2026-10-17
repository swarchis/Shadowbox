import { AnimatePresence, MotionConfig, motion } from 'framer-motion'
import { useCallback, useEffect, useState } from 'react'
import { TABS, TopBar, type TabId } from './components/TopBar'
import { DataProvider, useData } from './lib/DataContext'
import { EvolutionView } from './views/EvolutionView'
import { FinalExamView } from './views/FinalExamView'
import { LiveMatchView } from './views/LiveMatchView'
import { OverviewView } from './views/OverviewView'
import { DemoMode } from './views/demo/DemoMode'

function tabFromHash(): TabId {
  const h = window.location.hash.replace('#', '')
  return (TABS.find((t) => t.id === h)?.id ?? 'overview') as TabId
}

function Shell() {
  const params = new URLSearchParams(window.location.search)
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [demo, setDemo] = useState(params.has('demo'))
  // rehearsal aids: ?demo=1&scene=3&at=6.5&paused=1 opens scene 3 at 6.5s, paused
  const [demoStart] = useState(() => Math.max(0, Number(params.get('scene') ?? '1') - 1) || 0)
  const [demoAt] = useState(() => Math.max(0, Number(params.get('at') ?? '0')) || 0)
  const [demoPaused] = useState(() => params.get('paused') === '1')
  const [demoFromUrl, setDemoFromUrl] = useState(params.has('demo'))
  const { loaded } = useData()

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = useCallback((t: TabId) => {
    setTab(t)
    if (window.location.hash !== `#${t}`) window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${t}`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  // "D" opens demo mode from anywhere
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
      if (!demo && (e.key === 'd' || e.key === 'D') && !e.metaKey && !e.ctrlKey && !e.altKey) setDemo(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [demo])

  return (
    <>
      <div className="backdrop" />
      <TopBar tab={tab} onTab={go} onDemo={() => setDemo(true)} />
      <main className="mx-auto max-w-[1400px] px-4 pb-16 pt-4 sm:px-6">
        {!loaded ? (
          <div className="grid place-items-center py-40">
            <motion.div className="h-10 w-10 rounded-full border-2 border-white/10 border-t-builder" animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.9, ease: 'linear' }} />
          </div>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
              {tab === 'overview' && <OverviewView />}
              {tab === 'match' && <LiveMatchView onNavigate={go} />}
              {tab === 'evolution' && <EvolutionView />}
              {tab === 'final' && <FinalExamView />}
            </motion.div>
          </AnimatePresence>
        )}
      </main>
      <footer className="mx-auto max-w-[1400px] px-4 pb-10 text-xs text-slate-600 sm:px-6">
        Shadowbox · the model stays frozen, the team around it rewrites itself · press <kbd className="rounded border border-white/10 px-1 font-mono">D</kbd> for the
        60-second demo
      </footer>
      <AnimatePresence>{demo && (
          <DemoMode
            key="demo"
            startScene={demoFromUrl ? demoStart : 0}
            startAt={demoFromUrl ? demoAt : 0}
            startPaused={demoFromUrl && demoPaused}
            onExit={() => {
              setDemo(false)
              setDemoFromUrl(false)
            }}
          />
        )}</AnimatePresence>
    </>
  )
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <DataProvider>
        <Shell />
      </DataProvider>
    </MotionConfig>
  )
}
