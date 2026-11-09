import { useEffect, useState } from 'react'
import { Brain, CheckCircle2, ChevronRight, MessageSquare, NotebookPen, TriangleAlert, Wrench } from 'lucide-react'
import { get } from './api'
import { Empty } from './ui'

const AGENT_LABEL: Record<string, string> = { planner: 'Planner', stress_test: 'Stress test', monitor: 'Monitor', intake: 'Intake' }

/** Every step of one agent run: model turns, tool calls (inputs and outputs) and the final answer. */
export function TraceView({ runId }: { runId: string | null }) {
  const [trace, setTrace] = useState<any>(null)
  useEffect(() => { if (runId) get(`/agent/trace/${runId}`).then(setTrace).catch(() => setTrace(null)); else setTrace(null) }, [runId])
  if (!trace?.run) return <Empty icon={<Wrench size={18} />} title="No run selected">Each agent run is logged step by step: which tool it called, with what, and what came back.</Empty>
  const run = trace.run
  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-3">
        <span className="badge badge-accent">{AGENT_LABEL[run.agent] || run.agent}</span>
        <span className="badge">{run.mode === 'scripted' ? 'Scripted policy' : run.mode === 'llm' ? 'Local LLM' : 'LLM → scripted fallback'}</span>
        <span className="badge num">{run.steps} steps</span>
        <span className="badge num">{(run.latency_ms / 1000).toFixed(1)} s</span>
        {run.tokens > 0 && <span className="badge num">{run.tokens.toLocaleString()} tokens</span>}
        {run.grounded != null && (run.grounded
          ? <span className="badge badge-good"><CheckCircle2 size={12} />Numbers verified</span>
          : <span className="badge badge-warn"><TriangleAlert size={12} />Unverified numbers</span>)}
      </div>
      <ol className="relative space-y-2 pl-5" style={{ borderLeft: '1px solid var(--border)' }}>
        {trace.steps.map((s: any, i: number) => (
          <li key={i} className="relative">
            <span className="absolute -left-[27px] top-2 w-[13px] h-[13px] rounded-full grid place-items-center" style={{ background: 'var(--surface)', border: '1px solid var(--border-strong)' }} />
            {s.kind === 'tool' ? (
              <details className="inset group">
                <summary className="flex items-center gap-2 px-3 py-2 cursor-pointer list-none t-sm">
                  <Wrench size={14} className="t-muted" /><span className="mono t-xs font-medium">{s.name}</span>
                  <span className="t-xs t-muted truncate flex-1 mono">{argSummary(s.input)}</span>
                  <span className="t-xs t-muted num">{s.latency_ms} ms</span>
                  <ChevronRight size={14} className="t-muted transition-transform group-open:rotate-90" />
                </summary>
                <pre className="mono t-xs px-3 pb-3 whitespace-pre-wrap break-all t-2 max-h-64 overflow-auto scroll-thin">{JSON.stringify(s.output, null, 2).slice(0, 4000)}</pre>
              </details>
            ) : (
              <div className="px-3 py-2 t-sm flex gap-2">
                {s.kind === 'answer' ? <MessageSquare size={14} className="mt-0.5 t-muted flex-none" /> : s.kind === 'model' ? <Brain size={14} className="mt-0.5 t-muted flex-none" /> : <NotebookPen size={14} className="mt-0.5 t-muted flex-none" />}
                <div className="t-2 whitespace-pre-wrap min-w-0">
                  {s.kind === 'model' ? modelText(s.output) : typeof s.output === 'string' ? s.output : JSON.stringify(s.output)}
                </div>
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}

export function RunList({ selected, onSelect, refreshKey }: { selected: string | null; onSelect: (id: string) => void; refreshKey?: any }) {
  const [runs, setRuns] = useState<any[]>([])
  useEffect(() => { get('/agent/runs?limit=15').then(setRuns).catch(() => {}) }, [refreshKey])
  if (!runs.length) return <p className="t-sm t-muted px-1">No agent runs yet.</p>
  return (
    <ul className="space-y-0.5">
      {runs.map((r) => (
        <li key={r.run_id}>
          <button onClick={() => onSelect(r.run_id)} className="w-full text-left px-2.5 py-2 rounded-lg flex items-center gap-2 t-sm"
            style={{ background: selected === r.run_id ? 'var(--surface-2)' : undefined }}>
            <span className="badge" style={{ height: 20 }}>{AGENT_LABEL[r.agent] || r.agent}</span>
            <span className="truncate flex-1 t-2">{r.input}</span>
            <span className="t-xs t-muted num flex-none">{timeAgo(r.ts)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function argSummary(a: any) {
  if (!a || typeof a !== 'object') return ''
  return Object.entries(a).filter(([k]) => k !== 'classification').map(([k, v]) => `${k}=${typeof v === 'string' ? v.slice(0, 24) : JSON.stringify(v)}`).join(' ')
}
function modelText(o: any) {
  if (!o) return ''
  if (o.tool_calls?.length) return `Decided to call ${o.tool_calls.map((c: any) => c.name).join(', ')}`
  return o.text || ''
}
export function timeAgo(ts: number) {
  const s = Date.now() / 1000 - ts
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
