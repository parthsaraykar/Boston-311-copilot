import { useEffect, useState } from 'react'
import { Check, CheckCircle2, Play, Radar, RefreshCcw, ShieldCheck, X, XCircle } from 'lucide-react'
import { DEPTS, MONTHS, get, moneyM, num, pct, post } from '../api'
import { SHORT } from '../api'
import { useData } from '../data'
import { LiveChart } from '../charts'
import { RunList, TraceView, timeAgo } from '../AgentTrace'
import { Card, DeptDot, Empty, PageHeader, Segmented, Slider, Spinner } from '../ui'

export default function Agents() {
  const { reload, plan } = useData()
  const [run, setRun] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const onRun = (id: string) => { setRun(id); setRefresh((x) => x + 1) }
  return (
    <div>
      <PageHeader eyebrow="Planning · Agents" title="Agents"
        description="Agents probe the plan, watch live demand and draft changes. Nothing changes the saved plan until a person approves it." />
      <div className="grid gap-6 xl:grid-cols-2">
        <StressTest onRun={onRun} />
        <Monitor onRun={onRun} onPlanChanged={() => { reload(); setRefresh((x) => x + 1) }} plan={plan} />
      </div>
      <Card title="Activity" description="Every agent run, step by step" className="mt-6" bodyClass="p-0">
        <div className="grid lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="p-2 lg:border-r max-h-[520px] overflow-y-auto scroll-thin" style={{ borderColor: 'var(--border)' }}>
            <RunList selected={run} onSelect={setRun} refreshKey={refresh} />
          </div>
          <div className="p-4 max-h-[520px] overflow-y-auto scroll-thin"><TraceView runId={run} /></div>
        </div>
      </Card>
    </div>
  )
}

function StressTest({ onRun }: { onRun: (id: string) => void }) {
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  async function go() {
    setBusy(true)
    try { const r = await post('/agent/stress-test', {}); setRes(r); onRun(r.run_id) } finally { setBusy(false) }
  }
  return (
    <Card title="Stress test" description="Searches demand rises, storms, slower crews and slower hiring for the cases that hurt the plan most"
      actions={<button className="btn btn-primary" onClick={go} disabled={busy}>{busy ? <Spinner /> : <Play />}{busy ? 'Probing…' : 'Run'}</button>}>
      {!res ? (
        <Empty icon={<Radar size={18} />} title="Find the plan’s weak spots">The agent probes one change at a time, keeps the worst, and reports the cheapest fix. Its answer is checked against a brute-force grid of every combination.</Empty>
      ) : (
        <div className="space-y-4">
          <ol className="space-y-2">
            {res.worst_cases.map((w: any, i: number) => (
              <li key={i} className="inset p-3">
                <div className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-md grid place-items-center t-xs font-semibold flex-none num" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>{i + 1}</span>
                  <div className="min-w-0">
                    <div className="font-medium t-sm">{cap(w.label)}</div>
                    <div className="t-sm t-2 mt-0.5">Keeping the plan: <span className="num">{moneyM(w.locked_total_cost)}</span>, <span style={{ color: 'var(--danger)' }}>{pct(w.locked_on_time, 0)} on time</span></div>
                    <div className="t-sm t-2">Fix: re-plan ({w.fix}). Saves <span className="num font-medium" style={{ color: 'var(--text)' }}>{moneyM(w.cost_of_not_replanning)}</span></div>
                  </div>
                </div>
              </li>
            ))}
          </ol>
          <div className="flex items-center gap-2 t-sm">
            {res.grid_check.agent_found_grid_worst
              ? <span className="badge badge-good"><CheckCircle2 size={13} />Matches brute-force worst case</span>
              : <span className="badge badge-warn"><XCircle size={13} />Missed the brute-force worst case</span>}
            <span className="t-muted">{res.grid_check.agent_probes} probes vs {res.grid_check.grid_size} in the full grid</span>
          </div>
        </div>
      )}
    </Card>
  )
}

function Monitor({ onRun, onPlanChanged, plan }: { onRun: (id: string) => void; onPlanChanged: () => void; plan: any }) {
  const [asOf, setAsOf] = useState(6)
  const [spike, setSpike] = useState<string>('')
  const [live, setLive] = useState<any>(null)
  const [dept, setDept] = useState<string>('Public Works')
  const [result, setResult] = useState<any>(null)
  const [proposals, setProposals] = useState<any[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const spikeObj = spike ? { [spike]: 0.35 } : {}
  const loadProps = () => get('/proposals').then(setProposals).catch(() => {})
  useEffect(() => { loadProps() }, [])
  useEffect(() => {
    post('/demo/state', { as_of_month: asOf, spike: spikeObj }).then(() => get(`/live-demand?as_of_month=${asOf}`)).then(setLive).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asOf, spike])

  async function runMonitor() {
    setBusy('monitor')
    try { const r = await post('/agent/monitor/run', { as_of_month: asOf, spike: spikeObj }); setResult(r); onRun(r.run_id); loadProps() } finally { setBusy(null) }
  }
  async function replan() {
    setBusy('replan')
    try { await post('/plan/solve', { use_live: true }); loadProps() } finally { setBusy(null) }
  }
  async function decide(id: string, ok: boolean) {
    setBusy(id)
    try { await post(`/plan/${ok ? 'approve' : 'reject'}/${id}`); loadProps(); if (ok) onPlanChanged() } finally { setBusy(null) }
  }
  const pending = proposals.filter((p) => p.status === 'pending')
  const d = live?.departments?.[dept]

  return (
    <Card title="Demand monitor" description="City data replayed through the chosen month, plus app filings"
      actions={<>
        <button className="btn" onClick={replan} disabled={!!busy}>{busy === 'replan' ? <Spinner /> : <RefreshCcw />}Re-plan</button>
        <button className="btn btn-primary" onClick={runMonitor} disabled={!!busy}>{busy === 'monitor' ? <Spinner /> : <Play />}Run monitor</button>
      </>}>
      <div className="grid sm:grid-cols-2 gap-4 mb-4">
        <Slider label="Replay through" value={asOf} min={1} max={12} step={1} onChange={setAsOf} format={(v) => MONTHS[v - 1] + ' 2025'} />
        <div>
          <label htmlFor="spike" className="t-sm t-2 block mb-1">Simulate a spike this month</label>
          <select id="spike" className="select" value={spike} onChange={(e) => setSpike(e.target.value)}>
            <option value="">None</option>
            {DEPTS.map((x) => <option key={x} value={x}>{x} +35%</option>)}
          </select>
        </div>
      </div>
      <Segmented label="Department" value={dept} onChange={setDept}
        options={DEPTS.map((x) => ({ value: x, label: <><DeptDot dept={x} />{SHORT[x]}</> }))} />
      {d && (
        <>
          <div className="mt-3"><LiveChart months={d.months} dept={dept} height={210} /></div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 t-sm t-2 mt-1">
            <span>Year to date <span className="num font-medium" style={{ color: 'var(--text)' }}>{num(d.ytd_actual)}</span> vs <span className="num">{num(d.ytd_forecast)}</span> forecast</span>
            <span className="num" style={{ color: Math.abs((d.ytd_ratio ?? 1) - 1) > 0.08 ? 'var(--warn)' : 'var(--good)' }}>{pctSigned((d.ytd_ratio ?? 1) - 1)}</span>
            <span>Filed in app: <span className="num">{d.months.reduce((s: number, m: any) => s + m.filed_in_app, 0)}</span></span>
          </div>
        </>
      )}
      {result && <p className="t-sm mt-4 inset p-3">{result.answer}</p>}

      {pending.length > 0 && <div className="mt-4 space-y-3">{pending.map((p) => (
        <div key={p.id} className="rounded-[10px] overflow-hidden" style={{ border: '1px solid var(--accent-border)' }}>
          <div className="px-3 py-2 flex items-center gap-2 t-sm" style={{ background: 'var(--accent-soft)' }}>
            <ShieldCheck size={15} style={{ color: 'var(--accent)' }} /><span className="font-medium">Re-plan awaiting approval</span>
            <span className="t-xs t-muted ml-auto">from {MONTHS[p.summary.as_of_month] ?? '—'} · by {p.created_by} · {timeAgo(p.ts)}</span>
          </div>
          <div className="p-3 space-y-3">
            <p className="t-sm t-2">{p.reason}</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="inset p-2.5"><div className="t-xs t-muted">Keep current plan</div><div className="num font-medium">{moneyM(p.summary.keep_plan_cost)} <span className="t-muted t-sm font-normal">· {pct(p.summary.keep_plan_on_time)}</span></div></div>
              <div className="inset p-2.5" style={{ borderColor: 'var(--accent-border)' }}><div className="t-xs t-muted">Proposed</div><div className="num font-medium">{moneyM(p.summary.new_plan_cost)} <span className="t-muted t-sm font-normal">· {pct(p.summary.new_plan_on_time)}</span></div></div>
            </div>
            {p.summary.changes?.length > 0 && (
              <div className="t-xs t-2 flex flex-wrap gap-1">{p.summary.changes.slice(0, 8).map((ch: any, i: number) => (
                <span key={i} className="badge num" style={{ height: 20 }}>{SHORT[ch.dept]} {MONTHS[ch.month - 1]} {ch.crews_before}→{ch.crews_after}</span>))}
                {p.summary.changes.length > 8 && <span className="t-muted">+{p.summary.changes.length - 8} more</span>}</div>
            )}
            <div className="flex gap-2">
              <button className="btn btn-primary btn-sm" onClick={() => decide(p.id, true)} disabled={!!busy}><Check />Approve</button>
              <button className="btn btn-sm" onClick={() => decide(p.id, false)} disabled={!!busy}><X />Reject</button>
            </div>
          </div>
        </div>))}
      </div>}
      {plan?.replanned_from_month && <p className="t-xs t-muted mt-3">The saved plan was re-planned from {MONTHS[plan.replanned_from_month]} after an approval.</p>}
    </Card>
  )
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const pctSigned = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)}%`
