import { useEffect, useState } from 'react'
import { CheckCircle2, CircleAlert, History } from 'lucide-react'
import { DEPTS, MONTHS, SHORT, get, moneyM, pct } from '../api'
import { useData } from '../data'
import { CrewCompareChart, CumulativeCostChart } from '../charts'
import { Card, DeptDot, Note, PageHeader, Segmented, Stat } from '../ui'

const ORDER = [
  { key: 'flat', label: 'Today’s crews', color: '--neutral' },
  { key: 'locked', label: 'Plan, never changed', color: '--s-bt' },
  { key: 'monitored', label: 'Plan + monitor', color: '--accent' },
  { key: 'hindsight', label: 'Perfect hindsight', color: '--text-2', dashed: true },
]
const POLICY_LABEL: Record<string, string> = {
  every_drift_blend: 'Shipped rule: re-plan on any drift, blend YTD and latest month',
  every_drift_ytd: 'Re-plan on any drift, YTD only',
  persistent_ytd: 'Re-plan after 2 months of drift, YTD only',
  every_drift_ytd_margin: 'Any drift, YTD only, +3 pt target margin',
  persistent_ytd_margin: '2 months of drift, YTD only, +3 pt margin',
  every_drift_blend_cap10: 'Shipped rule + max 10% crew change a month',
  every_drift_blend_cap20: 'Shipped rule + max 20% crew change a month',
  every_drift_ytd_cap10: 'YTD only + max 10% crew change a month',
  every_drift_ytd_cap20: 'YTD only + max 20% crew change a month',
}

export default function Replay() {
  const { plan } = useData()
  const [r, setR] = useState<any>(null)
  const [dept, setDept] = useState<string>('Inspectional Services')
  useEffect(() => { get('/replay').then(setR).catch(() => setR({ error: true })) }, [])
  if (!r) return <div className="skeleton h-96" />
  if (r.error) return <Card>Replay results aren’t built yet. Run <code>make replay</code>.</Card>
  const S = r.strategies, h = r.headline, target = r.target
  const k = plan?.params?.departments?.[dept]?.requests_per_crew_month || 1
  const needed = r.demand.actual[dept].map((v: number) => v / k)

  return (
    <div>
      <PageHeader eyebrow="Planning · Proof" title="2025 replay"
        description="What if Boston had run this in 2025? The real 2025 demand, replayed month by month. The plan starts from the January forecast, and the monitor re-plans when demand drifts outside the band." />

      <div className="grid gap-4 grid-cols-2 xl:grid-cols-4 mb-6">
        <Stat label="Saved vs today’s crews" value={moneyM(h.saving_vs_flat)} foot={`${moneyM(S.monitored.totals.total_cost)} vs ${moneyM(S.flat.totals.total_cost)}`} />
        <Stat label="Closed on time" value={pct(h.on_time_monitored)} foot={`vs ${pct(h.on_time_flat)} with today’s crews`} />
        <Stat label="Worst department, on time" value={pct(S.monitored.worst_dept_on_time)} foot={`vs ${pct(S.flat.worst_dept_on_time)} with today’s crews (${worstName(S.flat)})`} />
        <Stat label="Re-plans proposed" value={`${S.monitored.replans}`} foot="Months where demand left the forecast band" />
      </div>

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card title="Cumulative cost through 2025" description="Same real demand for every strategy">
          <CumulativeCostChart strategies={S} order={ORDER} height={280} />
        </Card>
        <Card title="By department" description={`On time, real 2025 demand · target ${Math.round(target * 100)}%`} bodyClass="p-0 overflow-x-auto">
          <table className="data">
            <thead><tr><th></th>{ORDER.map((o) => <th key={o.key} className="r">{o.label}</th>)}</tr></thead>
            <tbody>
              {DEPTS.map((d) => (
                <tr key={d}><td className="whitespace-nowrap"><span className="flex items-center gap-2"><DeptDot dept={d} />{SHORT[d]}</span></td>
                  {ORDER.map((o) => {
                    const v = S[o.key].by_dept[d].on_time_rate
                    return <td key={o.key} className="r" style={{ color: v < target - 1e-9 ? 'var(--danger)' : undefined }}>{pct(v, 1)}</td>
                  })}</tr>
              ))}
              <tr><td className="font-medium">Total cost</td>{ORDER.map((o) => <td key={o.key} className="r font-medium">{moneyM(S[o.key].totals.total_cost)}</td>)}</tr>
              <tr><td className="font-medium">Departments at target</td>{ORDER.map((o) => <td key={o.key} className="r">{S[o.key].depts_at_target}/4</td>)}</tr>
            </tbody>
          </table>
        </Card>
      </div>

      <div className="mt-6"><Note>
        <strong>How to read this.</strong> 2025 came in well below the forecast: Public Works −16% and Parks −26%. The plan that never changes looks cheap
        only because it ends up overstaffed in those two departments, and it still leaves Inspectional Services at {pct(S.locked.by_dept['Inspectional Services'].on_time_rate, 0)}.
        With the monitor, Inspectional Services reaches {pct(S.monitored.by_dept['Inspectional Services'].on_time_rate, 0)} and every department lands within a point of target, for {moneyM(h.saving_vs_flat)} less than
        today’s crews. Perfect hindsight would save another {moneyM(h.gap_to_hindsight)}. That gap is the value of a better forecast.
      </Note></div>

      <div className="grid gap-6 xl:grid-cols-2 mt-6">
        <Card title="Crews: January plan vs what the monitor ran" description="Dashed: crews the real demand would have needed">
          <div className="mb-3 overflow-x-auto"><Segmented label="Department" value={dept} onChange={setDept} options={DEPTS.map((d) => ({ value: d, label: <><DeptDot dept={d} />{SHORT[d]}</> }))} /></div>
          <CrewCompareChart plan={r.plan_crews[dept]} monitored={r.monitored_crews[dept]} needed={needed} dept={dept} height={240} />
        </Card>
        <Card title="Monitor log" description="Each re-plan, after the month it was triggered" bodyClass="p-0">
          <ol className="divide max-h-[330px] overflow-y-auto scroll-thin">
            {r.events.map((e: any) => (
              <li key={e.after_month} className="px-4 py-2.5 t-sm flex gap-3">
                <History size={15} className="t-muted flex-none mt-0.5" />
                <div className="min-w-0">
                  <div className="font-medium">End of {MONTHS[e.after_month - 1]}: re-planned from {MONTHS[e.after_month]}</div>
                  <div className="t-xs t-2">{Object.entries(e.drift).map(([d, why]: any) => `${SHORT[d]} ${why}`).join(' · ')}</div>
                  {(Object.keys(e.hires_next_month).length > 0 || Object.keys(e.releases_next_month).length > 0) && (
                    <div className="t-xs t-muted mt-0.5">
                      {Object.entries(e.hires_next_month).map(([d, v]: any) => `hire ${v} ${SHORT[d]}`).concat(
                        Object.entries(e.releases_next_month).map(([d, v]: any) => `release ${v} ${SHORT[d]}`)).join(', ')}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <Card title="Monitor rule variants" className="mt-6" bodyClass="p-0 overflow-x-auto"
        description="Checked for transparency. The headline uses the rule as shipped, fixed before this replay was built.">
        <table className="data">
          <thead><tr><th>Rule</th><th className="r">2024 cost</th><th className="r">2024 worst dept</th><th className="r">2025 cost</th><th className="r">2025 worst dept</th><th className="r">2025 re-plans</th></tr></thead>
          <tbody>{Object.keys(r.policy_selection.candidates_2024).map((p) => {
            const a = r.policy_selection.candidates_2024[p], b = r.policy_selection.all_policies_2025[p]
            return (
              <tr key={p}>
                <td>
                  <span className="flex items-center gap-2">{POLICY_LABEL[p] || p}
                    {p === r.policy && <span className="badge badge-accent" style={{ height: 20 }}>Shipped</span>}
                    {p === r.policy_selection.chosen && p !== r.policy && <span className="badge" style={{ height: 20 }}>2024 pick</span>}
                  </span>
                </td>
                <td className="r">{moneyM(a.total_cost)}</td>
                <td className="r">{flag(a.worst_dept_on_time, target)}</td>
                <td className="r">{moneyM(b.total_cost)}</td>
                <td className="r">{flag(b.worst_dept_on_time, target)}</td>
                <td className="r">{b.replans}</td>
              </tr>
            )
          })}</tbody>
        </table>
        <div className="px-4 py-3 t-xs t-muted border-t" style={{ borderColor: 'var(--border)' }}>
          The 2024 replay uses the forecast trained on data through 2023, and crews calibrated on 2023. Capping crew changes makes 2025 cheaper,
          but it lets Parks and Inspectional Services slip well below target. The trade-off is reported, not tuned away.
        </div>
      </Card>
    </div>
  )
}

function flag(v: number, target: number) {
  const ok = v >= target - 0.005
  return <span className="inline-flex items-center gap-1" style={{ color: ok ? undefined : 'var(--danger)' }}>
    {ok ? <CheckCircle2 size={13} style={{ color: 'var(--good)' }} /> : <CircleAlert size={13} />}{pct(v, 0)}
  </span>
}

function worstName(strategy: any) {
  return SHORT[Object.entries(strategy.by_dept).sort((a: any, b: any) => a[1].on_time_rate - b[1].on_time_rate)[0][0]]
}
