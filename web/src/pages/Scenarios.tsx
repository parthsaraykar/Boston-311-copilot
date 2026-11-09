import { useEffect, useState } from 'react'
import { RotateCcw, Snowflake } from 'lucide-react'
import { DEPTS, moneyM, pct, post } from '../api'
import { SHORT } from '../api'
import { useData } from '../data'
import { FrontierChart, TornadoChart } from '../charts'
import { Card, DeptDot, Note, PageHeader, Segmented, Slider, Spinner, Switch } from '../ui'
import { LoadError } from './PlanOverview'

type Controls = { target: number; demand_mult: number; storm: boolean; late_cost: number; severance_rate: number; seasonal_premium: number; crew_output_mult: number; training_months: number }
const DEFAULTS: Controls = { target: 0.85, demand_mult: 1, storm: false, late_cost: 20, severance_rate: 0.25, seasonal_premium: 0.3, crew_output_mult: 1, training_months: 1 }
const CASE_LABEL: Record<string, string> = {
  'demand_x0.8': 'Demand −20%', 'demand_x0.9': 'Demand −10%', 'demand_x1.1': 'Demand +10%', 'demand_x1.2': 'Demand +20%', storm: 'Snowstorm, Jan–Feb',
  late_cost_40: 'Late cost $40', severance_50: 'Severance 50%', seasonal_premium_50: 'Seasonal premium 50%', crew_output_minus10: 'Crew output −10%', training_2_months: 'Training 2 months',
}

export default function Scenarios() {
  const { plan, frontier, scenarios, error } = useData()
  const [c, setC] = useState<Controls>(DEFAULTS)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const isDefault = (Object.keys(DEFAULTS) as (keyof Controls)[]).every((k) => c[k] === DEFAULTS[k])

  useEffect(() => {
    if (isDefault) { setRes(null); return }
    const id = setTimeout(() => {
      setBusy(true)
      post('/scenario', c).then(setRes).catch(() => setRes(null)).finally(() => setBusy(false))
    }, 400)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(c)])

  if (error) return <LoadError />
  if (!plan || !scenarios) return <div className="skeleton h-96" />
  const up = (k: keyof Controls) => (v: any) => setC({ ...c, [k]: v })
  const base = plan.totals
  const L = res?.locked?.totals, R = res?.replanned?.totals

  return (
    <div>
      <PageHeader eyebrow="Planning · 2025" title="Scenarios"
        description="Change demand or costs and compare two answers: keep the saved plan and live with it, or re-plan knowing the change." />
      <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)] items-start">
        <Card title="Inputs" actions={!isDefault && <button className="btn btn-ghost btn-sm" onClick={() => setC(DEFAULTS)}><RotateCcw />Reset</button>} className="xl:sticky xl:top-6">
          <div className="space-y-5">
            <Slider label="On-time target, each department" value={c.target} min={0.5} max={0.95} step={0.05} onChange={up('target')} format={(v) => `${Math.round(v * 100)}%`} />
            <Slider label="Demand vs forecast" value={c.demand_mult} min={0.8} max={1.2} step={0.05} onChange={up('demand_mult')} format={signedPct} />
            <Switch checked={c.storm} onChange={up('storm')} label={<span className="flex items-center gap-1.5"><Snowflake size={14} className="t-muted" />Snowstorm in Jan–Feb</span>} />
            <hr style={{ borderColor: 'var(--border)' }} />
            <Slider label="Cost of a late request" value={c.late_cost} min={10} max={50} step={5} onChange={up('late_cost')} format={(v) => `$${v}`} />
            <Slider label="Severance, share of salary" value={c.severance_rate} min={0.1} max={0.5} step={0.05} onChange={up('severance_rate')} format={(v) => `${Math.round(v * 100)}%`} />
            <Slider label="Parks seasonal premium" value={c.seasonal_premium} min={0.1} max={0.6} step={0.05} onChange={up('seasonal_premium')} format={(v) => `${Math.round(v * 100)}%`} />
            <Slider label="Crew output" value={c.crew_output_mult} min={0.8} max={1.1} step={0.05} onChange={up('crew_output_mult')} format={signedPct} />
            <div>
              <div className="t-sm t-2 mb-1.5">Training before a new crew is productive</div>
              <Segmented label="Training time" value={String(c.training_months) as '1' | '2'} onChange={(v) => up('training_months')(Number(v))}
                options={[{ value: '1', label: '1 month' }, { value: '2', label: '2 months' }]} />
            </div>
          </div>
        </Card>

        <div className="space-y-6 min-w-0">
          <Card title="Result" description={isDefault ? 'Saved plan, forecast demand' : 'Re-solved for your inputs'} actions={busy && <Spinner label="Solving…" />} bodyClass="p-0">
            <div className="overflow-x-auto">
              <table className="data">
                <thead><tr><th></th><th className="r">Total cost</th><th className="r">On time</th>{DEPTS.map((d) => <th key={d} className="r"><span className="inline-flex items-center gap-1.5"><DeptDot dept={d} />{SHORT[d]}</span></th>)}</tr></thead>
                <tbody>
                  <tr><td className="font-medium">Saved plan, forecast demand</td><td className="r">{moneyM(base.total_cost)}</td><td className="r">{pct(base.on_time_rate)}</td>
                    {DEPTS.map((d) => <td key={d} className="r">{pct(plan.by_dept[d].on_time_rate, 0)}</td>)}</tr>
                  {res && <>
                    <tr><td className="font-medium">Keep the saved plan</td><td className="r">{moneyM(L.total_cost)}</td><td className="r" style={{ color: L.on_time_rate < c.target ? 'var(--danger)' : undefined }}>{pct(L.on_time_rate)}</td>
                      {DEPTS.map((d) => <td key={d} className="r" style={{ color: res.locked.by_dept[d].on_time_rate < c.target ? 'var(--danger)' : undefined }}>{pct(res.locked.by_dept[d].on_time_rate, 0)}</td>)}</tr>
                    <tr><td className="font-medium">Re-plan for it</td><td className="r">{moneyM(R.total_cost)}</td><td className="r">{pct(R.on_time_rate)}</td>
                      {DEPTS.map((d) => <td key={d} className="r">{pct(res.replanned.by_dept[d].on_time_rate, 0)}</td>)}</tr>
                  </>}
                </tbody>
              </table>
            </div>
            {res && (
              <div className="px-4 py-3 border-t t-sm" style={{ borderColor: 'var(--border)' }}>
                {res.cost_of_not_replanning > 1000
                  ? <>Re-planning saves <strong className="num">{moneyM(res.cost_of_not_replanning)}</strong> compared with keeping the saved plan.</>
                  : <>The saved plan holds up: re-planning changes cost by less than $1,000.</>}
              </div>
            )}
          </Card>

          <div className="grid gap-6 2xl:grid-cols-2">
            <Card title="Cost of a higher on-time target" description="Cheapest plan at each target, applied to every department">
              <FrontierChart frontier={frontier} target={c.target} height={240} />
            </Card>
            <Card title="What moves total cost most" description="Change in re-planned cost at each input’s low and high value">
              <TornadoChart rows={scenarios.tornado} height={260} />
            </Card>
          </div>

          <Card title="Precomputed cases" bodyClass="p-0 overflow-x-auto">
            <table className="data">
              <thead><tr><th>Case</th><th className="r">Keep plan: cost</th><th className="r">On time</th><th className="r">Re-plan: cost</th><th className="r">On time</th><th className="r">Re-planning saves</th></tr></thead>
              <tbody>{Object.entries(scenarios.cases).map(([k, v]: any) => (
                <tr key={k}><td>{CASE_LABEL[k] || k}</td>
                  <td className="r">{moneyM(v.locked.totals.total_cost)}</td><td className="r">{pct(v.locked.totals.on_time_rate, 0)}</td>
                  <td className="r">{moneyM(v.replanned.totals.total_cost)}</td><td className="r">{pct(v.replanned.totals.on_time_rate, 0)}</td>
                  <td className="r">{moneyM(v.cost_of_not_replanning)}</td></tr>))}
              </tbody>
            </table>
          </Card>
          <Note>Under-forecasting is the expensive mistake. With +10% demand, keeping the plan drops on-time to about 55%. With lower demand the saved plan is overstaffed: it beats the target but costs more than a re-plan that trims crews.</Note>
        </div>
      </div>
    </div>
  )
}

const signedPct = (v: number) => `${v >= 1 ? '+' : '−'}${Math.abs(Math.round((v - 1) * 100))}%`
