import { useEffect, useState, type ReactNode } from 'react'
import {
  Activity, BarChart3, Bot, ClipboardCheck, FlaskConical, Inbox, Menu, MessageSquareText, Moon, ShieldAlert, Sun, Type, X,
} from 'lucide-react'
import { DataProvider, useData } from './data'
import Resident from './pages/Resident'
import PlanOverview from './pages/PlanOverview'
import Scenarios from './pages/Scenarios'
import Agents from './pages/Agents'
import Risk from './pages/Risk'
import Review from './pages/Review'
import Evaluation from './pages/Evaluation'
import AskDrawer from './AskDrawer'

type Route = 'resident' | 'plan' | 'scenarios' | 'agents' | 'risk' | 'review' | 'eval'
const NAV: { group: string; items: { id: Route; label: string; icon: ReactNode }[] }[] = [
  { group: 'Intake', items: [
    { id: 'resident', label: 'Report a problem', icon: <MessageSquareText /> },
    { id: 'review', label: 'Review queue', icon: <Inbox /> },
  ] },
  { group: 'Planning', items: [
    { id: 'plan', label: '2025 crew plan', icon: <BarChart3 /> },
    { id: 'scenarios', label: 'Scenarios', icon: <FlaskConical /> },
    { id: 'risk', label: 'Risk & equity', icon: <ShieldAlert /> },
    { id: 'agents', label: 'Agents', icon: <Bot /> },
  ] },
  { group: 'Quality', items: [
    { id: 'eval', label: 'Evaluation', icon: <ClipboardCheck /> },
  ] },
]
const ROUTES = NAV.flatMap((g) => g.items.map((i) => i.id))

function readHash(): { route: Route; kiosk: boolean } {
  const h = window.location.hash.replace('#', '').split('?')[0]
  if (h === 'file') return { route: 'resident', kiosk: true }
  if (h === 'planner') return { route: 'plan', kiosk: false } // old links
  return { route: (ROUTES.includes(h as Route) ? h : 'resident') as Route, kiosk: false }
}

export default function App() {
  return <DataProvider><Shell /></DataProvider>
}

function Shell() {
  const [{ route, kiosk }, setRoute] = useState(readHash)
  const [menu, setMenu] = useState(false)
  const [large, setLarge] = useState(() => store('largeText') === '1')
  const [theme, setTheme] = useState<string>(() => store('theme') || 'system')
  const { health } = useData()

  useEffect(() => {
    const on = () => { setRoute(readHash()); setMenu(false); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  useEffect(() => { document.documentElement.classList.toggle('large-text', large); store('largeText', large ? '1' : '0') }, [large])
  useEffect(() => {
    if (theme === 'system') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    store('theme', theme)
  }, [theme])
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)

  const page = {
    resident: <Resident kiosk={kiosk} />, plan: <PlanOverview />, scenarios: <Scenarios />, agents: <Agents />,
    risk: <Risk />, review: <Review />, eval: <Evaluation />,
  }[route]

  if (kiosk) {
    return (
      <div className="min-h-screen">
        <header className="h-14 flex items-center px-4 border-b" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
          <Logo />
        </header>
        <main className="max-w-2xl mx-auto px-4 py-6">{page}</main>
      </div>
    )
  }

  const sidebar = (
    <nav aria-label="Main" className="flex flex-col h-full">
      <div className="h-14 flex items-center px-4"><Logo /></div>
      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-5 scroll-thin">
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="px-2 mb-1.5 t-xs font-medium t-muted">{g.group}</div>
            <div className="space-y-0.5">
              {g.items.map((i) => (
                <a key={i.id} href={`#${i.id}`} className="nav-item" aria-current={route === i.id ? 'page' : undefined}>{i.icon}{i.label}</a>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="p-3 border-t space-y-2" style={{ borderColor: 'var(--border)' }}>
        <SystemStatus health={health} />
        <div className="flex gap-1">
          <button className="btn btn-ghost btn-sm flex-1" onClick={() => setTheme(dark ? 'light' : 'dark')} aria-label="Toggle dark mode">
            {dark ? <Sun /> : <Moon />}{dark ? 'Light' : 'Dark'}
          </button>
          <button className="btn btn-ghost btn-sm flex-1" onClick={() => setLarge(!large)} aria-pressed={large}><Type />{large ? 'Normal text' : 'Larger text'}</button>
        </div>
      </div>
    </nav>
  )

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <a href="#main" className="sr-only focus:not-sr-only">Skip to content</a>
      <aside className="hidden lg:block sticky top-0 h-screen border-r" style={{ background: 'var(--sidebar)', borderColor: 'var(--border)' }}>{sidebar}</aside>
      {/* mobile top bar + drawer */}
      <div className="lg:hidden sticky top-0 z-[900] h-14 flex items-center gap-2 px-3 border-b" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
        <button className="btn btn-ghost btn-icon" onClick={() => setMenu(true)} aria-label="Open menu"><Menu /></button>
        <Logo />
      </div>
      {menu && (
        <div className="lg:hidden fixed inset-0 z-[1000]">
          <div className="absolute inset-0" style={{ background: 'rgba(9,9,11,.35)' }} onClick={() => setMenu(false)} />
          <div className="absolute left-0 top-0 h-full w-[270px]" style={{ background: 'var(--sidebar)' }}>
            <button className="btn btn-ghost btn-icon absolute right-2 top-3" onClick={() => setMenu(false)} aria-label="Close menu"><X /></button>
            {sidebar}
          </div>
        </div>
      )}
      <main id="main" className="min-w-0 px-4 sm:px-6 lg:px-10 py-7 max-w-[1320px] w-full">{page}</main>
      <AskDrawer />
    </div>
  )
}

function Logo() {
  return (
    <a href="#resident" className="flex items-center gap-2.5" aria-label="Boston 311 Copilot home">
      <img src="/logo.svg" alt="" width={26} height={26} />
      <span className="font-semibold tracking-tight">Boston 311 <span className="t-muted font-medium">Copilot</span></span>
    </a>
  )
}

function SystemStatus({ health }: { health: any }) {
  const ok = health?.ok
  return (
    <div className="inset px-2.5 py-2 t-xs space-y-1">
      <div className="flex items-center gap-2"><Activity size={13} className="t-muted" /><span className="font-medium">System</span>
        <span className={`ml-auto badge ${ok ? 'badge-good' : 'badge-danger'}`} style={{ height: 18 }}><span className="dot" />{ok ? 'Online' : 'Offline'}</span></div>
      <div className="flex justify-between t-muted"><span>Local LLM</span><span>{health?.intake_model_ready ? health.intake_model : 'off'}</span></div>
      <div className="flex justify-between t-muted"><span>Speech-to-text</span><span>{health?.speech ? 'Whisper (local)' : 'off'}</span></div>
      <div className="flex justify-between t-muted"><span>Data</span><span>311 · 2022–2025</span></div>
    </div>
  )
}

function store(k: string, v?: string) {
  try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v) } catch { /* private mode */ }
  return null
}
