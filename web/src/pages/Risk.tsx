import { useEffect, useState } from 'react'
import { DEPTS, get, money, moneyM, num, pct } from '../api'
import { useData } from '../data'
import { HistogramChart } from '../charts'
import { Card, DeptDot, Note, PageHeader, Stat } from '../ui'
import { LoadError } from './PlanOverview'

export default function Risk() {
  const { scenarios: s, plan, error } = useData()
  const [eq, setEq] = useState<any>(null)
  useEffect(() => { get('/equity').then(setEq).catch(() => {}) }, [])
  if (error) return <LoadError />
  if (!s || !plan) return <div className="skeleton h-96" />
  const mc = s.monte_carlo, rb = s.robust.monte_carlo, st = s.storm, sm = s.smoothing
  const target = Math.round(plan.on_time_target * 100)

  return (
    <div>
      <PageHeader eyebrow="Planning · 2025" title="Risk & equity"
        description="How the plan holds up when demand doesn’t match the forecast, and who benefits from it." />

      <div className="grid gap-4 grid-cols-2 xl:grid-cols-4 mb-6">
        <Stat label={`Years every dept hits ${target}%`} value={`${mc.years_all_depts_hit_target} / 100`} foot={`Robust plan: ${rb.years_all_depts_hit_target} / 100`} />
        <Stat label="Cost, middle 80% of years" value={`$${(mc.cost_p10 / 1e6).toFixed(1)}–${(mc.cost_p90 / 1e6).toFixed(1)}M`} foot={`Median ${moneyM(mc.cost_p50)}`} />
        <Stat label="Snowstorm impact" value={`+${moneyM(st.extra_cost_locked)}`} foot={`${num(st.extra_late_requests_locked)} more late requests if not re-planned`} />
        <Stat label="Smoothing employee work" value={moneyM(sm.annual_saving)} foot={`A year, by moving ${Math.round(sm.share_moved * 100)}% of employee-logged work off peak months`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Card title="100 simulated demand years" description="Saved plan held fixed; demand drawn from the forecast’s historical errors">
          <HistogramChart costs={mc.costs} height={220} />
          <div className="overflow-x-auto mt-4 rounded-lg border" style={{ borderColor: 'var(--border)' }}>
            <table className="data">
              <thead><tr><th>Department</th><th className="r">Years at target, saved plan</th><th className="r">Robust plan</th></tr></thead>
              <tbody>{DEPTS.map((d) => (
                <tr key={d}><td><span className="flex items-center gap-2"><DeptDot dept={d} />{d}</span></td>
                  <td className="r">{mc.years_dept_hit_target[d]}</td><td className="r">{rb.years_dept_hit_target[d]}</td></tr>))}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="space-y-6">
          <Card title="Robust plan">
            <p className="t-sm t-2">Optimised across 20 sampled demand years instead of the average forecast.</p>
            <table className="data mt-3">
              <thead><tr><th></th><th className="r">Saved plan</th><th className="r">Robust</th></tr></thead>
              <tbody>
                <tr><td>All departments at target</td><td className="r">{mc.years_all_depts_hit_target}/100</td><td className="r">{rb.years_all_depts_hit_target}/100</td></tr>
                <tr><td>Median cost</td><td className="r">{moneyM(mc.cost_p50)}</td><td className="r">{moneyM(rb.cost_p50)}</td></tr>
                <tr><td>On time, median year</td><td className="r">{pct(mc.on_time_p50, 0)}</td><td className="r">{pct(rb.on_time_p50, 0)}</td></tr>
              </tbody>
            </table>
          </Card>
          <Card title="Snowstorms from real data">
            <ul className="space-y-1.5 t-sm">
              {st.storms.map((x: any) => (
                <li key={x.day} className="flex justify-between"><span className="num">{x.day}</span><span className="t-muted num">{x.ratio}× a normal day</span></li>
              ))}
            </ul>
            <p className="t-sm t-2 mt-3">The extra requests from the two worst storms, added to January and February 2025, cost {moneyM(st.extra_cost_locked)} if the plan doesn’t change. Re-planning ahead recovers {money(st.hiring_ahead_saves)}.</p>
          </Card>
        </div>
      </div>

      <Card title="Equity by neighborhood" className="mt-6" bodyClass="p-0"
        description={eq ? eq.finding : 'Loading…'}>
        {eq && (
          <>
            <div className="grid sm:grid-cols-3 gap-4 p-4 border-b" style={{ borderColor: 'var(--border)' }}>
              <div><div className="eyebrow">5 worst-served areas</div><div className="text-xl font-semibold num">+{eq.worst5_avg_gain_pts} pts</div><div className="t-xs t-muted">average expected gain</div></div>
              <div><div className="eyebrow">5 best-served areas</div><div className="text-xl font-semibold num">+{eq.best5_avg_gain_pts} pts</div><div className="t-xs t-muted">average expected gain</div></div>
              <div><div className="eyebrow">Gain by department</div><div className="t-sm mt-1 space-y-0.5">{Object.entries(eq.dept_gain_pts).map(([d, v]: any) => (
                <div key={d} className="flex items-center gap-2"><DeptDot dept={d} /><span className="flex-1">{d}</span><span className="num" style={{ color: v < 0 ? 'var(--danger)' : undefined }}>{v > 0 ? '+' : ''}{v} pts</span></div>))}</div></div>
            </div>
            <div className="overflow-x-auto max-h-[420px] scroll-thin">
              <table className="data">
                <thead><tr><th>Neighborhood</th><th className="r">On time, 2023–24</th><th className="r">Expected gain</th><th className="r">Requests</th></tr></thead>
                <tbody>{eq.neighborhoods.map((n: any) => (
                  <tr key={n.neighborhood}><td>{n.neighborhood}</td><td className="r">{pct(n.on_time_2023_24)}</td>
                    <td className="r">+{n.expected_gain_pts} pts</td><td className="r">{num(n.requests)}</td></tr>))}
                </tbody>
              </table>
            </div>
            <div className="p-4"><Note>Expected gain weights each neighborhood’s mix of requests by department by that department’s change in on-time rate (optimised vs flat staffing). Transportation gains most because it is the most short-staffed today.</Note></div>
          </>
        )}
      </Card>
    </div>
  )
}
