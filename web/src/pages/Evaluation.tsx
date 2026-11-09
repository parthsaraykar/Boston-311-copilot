import { useEffect, useState } from 'react'
import { CheckCircle2, ChevronRight, X, XCircle } from 'lucide-react'
import { get, pct } from '../api'
import { CurveChart, RateBars } from '../charts'
import { Card, Note, PageHeader, Segmented, Stat } from '../ui'

const LANG: Record<string, string> = { en: 'English', es: 'Spanish', ht: 'Haitian Creole', zh: 'Chinese', vi: 'Vietnamese', pt: 'Portuguese' }
const SLICE: Record<string, string> = { common: 'Common requests', long_tail: 'Long-tail categories', ambiguous: 'Ambiguous', multilingual: 'Other languages', emergency: 'Emergencies', guardrail: 'Off-topic & injection' }

export default function Evaluation() {
  const [ev, setEv] = useState<any>(null)
  const [mode, setMode] = useState<string>('retrieval')
  const [filter, setFilter] = useState<{ slice?: string; language?: string; label?: string }>({})
  const [cases, setCases] = useState<any[] | null>(null)

  useEffect(() => { get('/eval').then((e) => { setEv(e); setMode(e.primary || 'retrieval') }).catch(() => setEv({})) }, [])
  useEffect(() => {
    if (!filter.label) { setCases(null); return }
    const q = new URLSearchParams({ mode, ...(filter.slice ? { slice: filter.slice } : {}), ...(filter.language ? { language: filter.language } : {}) })
    get(`/eval/cases?${q}`).then(setCases).catch(() => setCases([]))
  }, [filter, mode])

  if (!ev) return <div className="skeleton h-96" />
  const m = ev[mode]
  if (!m) return <Card>No evaluation results yet. Run <code>make eval</code>.</Card>
  const o = m.overall
  const show = (label: string, f: { slice?: string; language?: string } = {}) => setFilter({ ...f, label })
  const modes = ['retrieval', 'llm'].filter((k) => ev[k])

  return (
    <div>
      <PageHeader eyebrow="Quality" title="Evaluation"
        description={`${m.n_messages} hand-labelled test messages, labelled before any model run. Select a figure to see the cases behind it.`}
        actions={modes.length > 1 && (
          <Segmented label="Routing engine" value={mode} onChange={setMode}
            options={modes.map((k) => ({ value: k, label: k === 'llm' ? 'Local LLM (qwen2.5 3B)' : 'Retrieval (default)' }))} />
        )} />

      <div className="grid gap-4 grid-cols-2 xl:grid-cols-4 mb-6">
        <button className="text-left" onClick={() => show('All routed requests')}><Stat label="Request type accuracy" value={pct(o.type_accuracy)} foot={`Keyword baseline ${pct(o.baseline_tfidf_type_accuracy)}`} /></button>
        <button className="text-left" onClick={() => show('All routed requests')}><Stat label="Department accuracy" value={pct(o.dept_accuracy)} foot={`Right answer in top 10: ${pct(o.top10_hit_rate)}`} /></button>
        <button className="text-left" onClick={() => show('Emergencies', { slice: 'emergency' })}><Stat label="Emergencies caught" value={`${Math.round(m.emergency_recall * m.emergency_n)} / ${m.emergency_n}`} foot={`False alarms ${pct(m.false_emergency_rate)}`} /></button>
        <button className="text-left" onClick={() => show('Off-topic & injection', { slice: 'guardrail' })}><Stat label="Off-topic & injection refused" value={`${Math.round(m.guardrail_refusal_rate * m.guardrail_n)} / ${m.guardrail_n}`} foot={`Real requests refused ${pct(m.wrongly_refused_rate)}`} /></button>
      </div>

      {ev.llm && ev.retrieval && (
        <div className="mb-6"><Note>
          <strong>Engine comparison.</strong> Retrieval routed {pct(ev.retrieval.overall.type_accuracy)} correctly; the local 3B LLM {pct(ev.llm.overall.type_accuracy)}, at a median {Math.round(ev.llm.latency_ms_p50 / 1000)} s per request. The LLM overrode correct matches with near-synonyms and rarely asked a follow-up question, so retrieval is the default.
          {m.leakage_check && <> On the {m.leakage_check.n_clean} messages that aren’t near-copies of category examples, accuracy is {pct(m.leakage_check.type_accuracy_excluding_near_copies)}.</>}
        </Note></div>
      )}

      {cases && (
        <Card title={filter.label} className="mb-6" actions={<button className="btn btn-ghost btn-sm" onClick={() => setFilter({})}><X />Close</button>} bodyClass="p-0">
          <div className="overflow-x-auto max-h-[420px] scroll-thin">
            <table className="data">
              <thead><tr><th></th><th>Message</th><th>Expected</th><th>Got</th><th className="r">Confidence</th></tr></thead>
              <tbody>{cases.map((c) => (
                <tr key={c.id}>
                  <td>{c.ok ? <CheckCircle2 size={16} style={{ color: 'var(--good)' }} aria-label="correct" /> : <XCircle size={16} style={{ color: 'var(--danger)' }} aria-label="wrong" />}</td>
                  <td className="max-w-[420px]">{c.text}</td><td className="t-2">{c.label}</td><td>{c.pred}</td>
                  <td className="r">{c.confidence != null ? pct(c.confidence, 0) : '–'}</td></tr>))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Accuracy by language" description="4 messages per non-English language, so treat these as indicative">
          <RateBars data={Object.entries(m.by_language).map(([k, v]: any) => ({ name: LANG[k] || k, value: v.type_accuracy }))} height={210} />
          <Breakdown rows={Object.entries(m.by_language).map(([k, v]: any) => ({ key: k, name: LANG[k] || k, v, onClick: () => show(LANG[k] || k, { language: k }) }))} />
        </Card>
        <Card title="Accuracy by test slice">
          <RateBars data={Object.entries(m.by_slice).map(([k, v]: any) => ({ name: (SLICE[k] || k).split(' ')[0], value: v.type_accuracy }))} height={210} />
          <Breakdown rows={Object.entries(m.by_slice).map(([k, v]: any) => ({ key: k, name: SLICE[k] || k, v, onClick: () => show(SLICE[k] || k, { slice: k }) }))} baseline />
          <p className="t-xs t-muted mt-3">Ambiguous messages: {pct(m.ambiguous_first_pass_accuracy)} on the first try, {pct(m.ambiguous_after_followup_accuracy)} after one follow-up question. {pct(m.clarify_share)} of all messages got a follow-up.</p>
        </Card>
        <Card title="Human review cut-off" description="Share routed automatically, and how accurate those are, at each confidence cut-off">
          <CurveChart curve={m.review_queue_curve} height={240} />
        </Card>
        <Card title="Confusion by department" description="Rows: correct department · columns: predicted">
          <Confusion conf={m.confusion_by_department} />
        </Card>
        <Card title="Queue from location" description="Real 2025 cases: given the true type and coordinates, did we pick the queue the city used?">
          {ev.queue_from_location && (
            <div className="grid grid-cols-3 gap-4">
              <div><div className="eyebrow">Exact queue</div><div className="text-xl font-semibold num">{pct(ev.queue_from_location.queue_accuracy)}</div></div>
              <div><div className="eyebrow">Department</div><div className="text-xl font-semibold num">{pct(ev.queue_from_location.dept_accuracy)}</div></div>
              <div><div className="eyebrow">Multi-district types</div><div className="text-xl font-semibold num">{pct(ev.queue_from_location.multi_queue_accuracy)}</div></div>
            </div>
          )}
          <p className="t-xs t-muted mt-3">{ev.queue_from_location?.cases} cases. Some real queues fall outside the 170 catalog combinations, which caps this score.</p>
        </Card>
        <Card title="Speed and cost">
          <div className="grid grid-cols-3 gap-4">
            <div><div className="eyebrow">Median latency</div><div className="text-xl font-semibold num">{fmtMs(m.latency_ms_p50)}</div></div>
            <div><div className="eyebrow">95th percentile</div><div className="text-xl font-semibold num">{fmtMs(m.latency_ms_p95)}</div></div>
            <div><div className="eyebrow">Cost per request</div><div className="text-xl font-semibold num">${m.cost_per_request_usd.toFixed(2)}</div></div>
          </div>
          <p className="t-xs t-muted mt-3">{m.tokens_per_request} tokens per request. Everything runs on local models, so there’s no per-request API cost.</p>
        </Card>
      </div>

      {m.failures?.length > 0 && (
        <Card title={`Known failure cases (${m.failures.length})`} className="mt-6" bodyClass="p-0">
          <div className="overflow-x-auto max-h-[360px] scroll-thin">
            <table className="data">
              <thead><tr><th>ID</th><th>Slice</th><th>Language</th><th>Expected</th><th>Got</th></tr></thead>
              <tbody>{m.failures.map((f: any) => (
                <tr key={f.id}><td className="mono t-xs">{f.id}</td><td>{SLICE[f.slice] || f.slice}</td><td>{LANG[f.language] || f.language}</td><td className="t-2">{f.label}</td><td>{f.pred ?? f.status}</td></tr>))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

function Breakdown({ rows, baseline }: { rows: { key: string; name: string; v: any; onClick: () => void }[]; baseline?: boolean }) {
  return (
    <div className="overflow-x-auto mt-3 rounded-lg border" style={{ borderColor: 'var(--border)' }}>
      <table className="data">
        <thead><tr><th>{baseline ? 'Slice' : 'Language'}</th><th className="r">n</th><th className="r">Type</th><th className="r">Department</th>{baseline && <th className="r">Keyword baseline</th>}<th></th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.key} className="cursor-pointer" onClick={r.onClick}>
            <td>{r.name}</td><td className="r">{r.v.n}</td><td className="r font-medium">{pct(r.v.type_accuracy)}</td><td className="r">{pct(r.v.dept_accuracy)}</td>
            {baseline && <td className="r t-muted">{pct(r.v.baseline_tfidf_type_accuracy)}</td>}
            <td className="r"><ChevronRight size={14} className="t-muted inline" /></td></tr>))}
        </tbody>
      </table>
    </div>
  )
}

function Confusion({ conf }: { conf: Record<string, Record<string, number>> }) {
  const labels = Object.keys(conf)
  const cols = Array.from(new Set(labels.concat(...Object.values(conf).map((r) => Object.keys(r)))))
  return (
    <div className="overflow-x-auto">
      <table className="data">
        <thead><tr><th></th>{cols.map((c) => <th key={c} className="r mono">{c}</th>)}</tr></thead>
        <tbody>{labels.map((l) => (
          <tr key={l}><td className="mono t-xs font-medium">{l}</td>{cols.map((c) => {
            const v = conf[l][c] || 0
            return <td key={c} className="r" style={{ background: v && c === l ? 'var(--accent-soft)' : v ? 'var(--danger-soft)' : undefined, color: v && c !== l ? 'var(--danger)' : undefined }}>{v || ''}</td>
          })}</tr>))}
        </tbody>
      </table>
    </div>
  )
}

const fmtMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`)
