import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { get } from './api'

type Data = {
  plan: any; baselines: any; frontier: any[]; forecast: any; scenarios: any; health: any
  loading: boolean; error: string | null; reload: () => void
  askOpen: boolean; openAsk: (q?: string) => void; closeAsk: () => void; askDraft: string
  traceId: string | null; setTraceId: (id: string | null) => void
}
const Ctx = createContext<Data | null>(null)

export function DataProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<any>({ plan: null, baselines: null, frontier: [], forecast: null, scenarios: null })
  const [health, setHealth] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [askOpen, setAskOpen] = useState(false)
  const [askDraft, setAskDraft] = useState('')
  const [traceId, setTraceId] = useState<string | null>(null)

  const reload = useCallback(() => {
    setLoading(true)
    Promise.all([get('/plan'), get('/plan/baselines'), get('/plan/frontier'), get('/forecast'), get('/scenarios')])
      .then(([plan, baselines, frontier, forecast, scenarios]) => { setState({ plan, baselines, frontier, forecast, scenarios }); setError(null) })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    reload()
    const h = () => get('/health').then(setHealth).catch(() => setHealth({ ok: false }))
    h()
    const id = setInterval(h, 30000)
    return () => clearInterval(id)
  }, [reload])

  return (
    <Ctx.Provider value={{
      ...state, health, loading, error, reload, askOpen, askDraft, traceId, setTraceId,
      openAsk: (q?: string) => { setAskDraft(q ?? ''); setAskOpen(true) }, closeAsk: () => setAskOpen(false),
    }}>{children}</Ctx.Provider>
  )
}

export function useData() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useData outside provider')
  return c
}
