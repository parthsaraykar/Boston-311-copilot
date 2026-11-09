import { useEffect, useRef, useState } from 'react'
import { ArrowUp, CheckCircle2, Sparkles, TriangleAlert } from 'lucide-react'
import { post } from './api'
import { useData } from './data'
import { TraceView } from './AgentTrace'
import { Drawer, Segmented, Spinner, Switch } from './ui'

const SUGGESTIONS = [
  'Why hire Parks crews in April?',
  'How much does the plan save versus flat staffing?',
  'What if demand is 10% higher?',
  'What happens if a snowstorm hits?',
  'What is the Transportation forecast for July?',
  'What are the worst cases for the plan?',
]

type Msg = { role: 'user' | 'agent'; text: string; sources?: string[]; grounded?: boolean; mode?: string; ms?: number; runId?: string }

export default function AskDrawer() {
  const { askOpen, closeAsk, askDraft, health, setTraceId } = useData()
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [useLLM, setUseLLM] = useState(false)
  const [tab, setTab] = useState<'chat' | 'trace'>('chat')
  const [runId, setRunId] = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { if (askOpen) { setQ(askDraft); setTab('chat'); setTimeout(() => inputRef.current?.focus(), 50) } }, [askOpen, askDraft])
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [msgs, busy])

  async function ask(text?: string) {
    const question = (text ?? q).trim()
    if (!question || busy) return
    setMsgs((m) => [...m, { role: 'user', text: question }])
    setQ('')
    setBusy(true)
    try {
      const r = await post('/agent/ask', { question, use_llm: useLLM })
      setMsgs((m) => [...m, { role: 'agent', text: r.answer, sources: r.sources, grounded: r.grounded, mode: r.mode, ms: r.latency_ms, runId: r.run_id }])
      setRunId(r.run_id); setTraceId(r.run_id)
    } catch {
      setMsgs((m) => [...m, { role: 'agent', text: 'The planning assistant is unavailable right now.' }])
    } finally { setBusy(false) }
  }

  return (
    <Drawer open={askOpen} onClose={closeAsk} title={<span className="flex items-center gap-2"><Sparkles size={16} style={{ color: 'var(--accent)' }} />Ask the plan</span>}>
      <div className="px-4 pt-3"><Segmented label="View" value={tab} onChange={setTab} options={[{ value: 'chat', label: 'Conversation' }, { value: 'trace', label: 'Agent trace' }]} /></div>
      {tab === 'trace' ? (
        <div className="flex-1 overflow-y-auto p-4 scroll-thin"><TraceView runId={runId} /></div>
      ) : (
        <>
          <div className="flex-1 overflow-y-auto p-4 space-y-4 scroll-thin">
            {msgs.length === 0 && (
              <div>
                <p className="t-sm t-2">Answers come only from the plan’s own numbers. Each reply lists the tools it used, and every figure is checked against them.</p>
                <div className="mt-4 space-y-1.5">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className="w-full text-left px-3 py-2 rounded-lg t-sm inset hover:border-[var(--border-strong)]" onClick={() => ask(s)}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) => m.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-md px-3.5 py-2 t-sm" style={{ background: 'var(--accent)', color: 'var(--accent-text)' }}>{m.text}</div>
              </div>
            ) : (
              <div key={i} className="max-w-[95%]">
                <div className="t-sm leading-relaxed">{m.text}</div>
                {m.sources && (
                  <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    {m.sources.map((s) => <span key={s} className="badge mono" style={{ height: 20, fontSize: '.7rem' }}>{s}</span>)}
                    {m.grounded != null && (m.grounded
                      ? <span className="badge badge-good" style={{ height: 20 }}><CheckCircle2 size={11} />Verified</span>
                      : <span className="badge badge-warn" style={{ height: 20 }}><TriangleAlert size={11} />Check figures</span>)}
                    <button className="t-xs t-muted underline ml-1" onClick={() => { setRunId(m.runId || null); setTab('trace') }}>View trace</button>
                  </div>
                )}
              </div>
            ))}
            {busy && <Spinner label={useLLM ? 'Thinking with the local model, this can take a minute…' : 'Thinking…'} />}
            <div ref={endRef} />
          </div>
          <div className="p-3 border-t space-y-2" style={{ borderColor: 'var(--border)' }}>
            <form className="flex items-end gap-2 rounded-xl border px-3 py-2 focus-within:shadow-[var(--ring)]" style={{ borderColor: 'var(--border-strong)' }}
              onSubmit={(e) => { e.preventDefault(); ask() }}>
              <label htmlFor="ask-q" className="sr-only">Question about the plan</label>
              <textarea id="ask-q" ref={inputRef} rows={1} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about any department or month…"
                className="flex-1 bg-transparent outline-none resize-none t-sm py-1" style={{ color: 'var(--text)', maxHeight: 120 }}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }} />
              <button className="btn btn-primary btn-sm btn-icon" style={{ width: 30, height: 30 }} disabled={!q.trim() || busy} aria-label="Send"><ArrowUp /></button>
            </form>
            <Switch checked={useLLM} onChange={setUseLLM} label={<span className="t-xs">Use local LLM for tool calls {health?.agent_model ? `(${health.agent_model}, slow on CPU)` : ''}</span>} />
          </div>
        </>
      )}
    </Drawer>
  )
}
