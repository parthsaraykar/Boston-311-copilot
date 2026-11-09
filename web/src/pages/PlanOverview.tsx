import { useState } from 'react'
import { Download, Sparkles, TrendingDown, TrendingUp, Users } from 'lucide-react'
import { API, DEPTS, MONTHS, SHORT, money, moneyM, num, pct } from '../api'
import { useData } from '../data'
import { CrewChart, DemandChart } from '../charts'
import { Card, DeptDot, PageHeader, Segmented, Stat } from '../ui'

export default function PlanOverview() {
  const { plan, baselines, forecast, loading, error, openAsk } = useData()
  const [dept, setDept] = useState<string>('All')

  if (error) return <LoadError />
  const ready = plan && baselines && forecast && !loading
  const flat = baselines?.flat?.totals
  const peak = ready ? Math.max(...MONTHS.map((_, i) => DEPTS.reduce((s, d) => s + plan.crews[d][i] + plan.seasonal[d][i], 0))) : 0

  return (
    <div>
      <PageHeader
        eyebrow="Planning · 2025"
        title="Crew plan"
        description="The lowest-cost monthly crew plan for Public Works, Transportation, Parks and Inspectional Services. It meets an 85% on-time target in every department."
        actions={<>
          <a className="btn" href={`${API}/memo.pdf`}><Download />Budget memo</a>
          <button className="btn btn-primary" onClick={() => openAsk()}><Sparkles />Ask the plan</button>
        </>}
      />

      <div className="grid gap-4 grid-cols-2 xl:grid-cols-4 mb-6">
        <Stat loading={!ready} label="Total cost, 2025" value={ready && moneyM(plan.totals.total_cost)}
          delta={ready ? `${pct((plan.totals.total_cost - flat.total_cost) / flat.total_cost, 1)}` : undefined} deltaGood foot={ready && `vs ${moneyM(flat.total_cost)} with today’s crews`} />
        <Stat loading={!ready} label="Closed on time" value={ready && pct(plan.totals.on_time_rate)}
          foot={ready && `vs ${pct(flat.on_time_rate)} with today’s crews`} />
        <Stat loading={!ready} label="Saving vs flat staffing" value={ready && moneyM(baselines.saving_vs_flat)}
          foot={ready && `${moneyM(baselines.saving_vs_level)} vs a level crew all year`} />
        <Stat loading={!ready} label="Peak crews" value={ready && num(peak)} foot="Busiest month, incl. Parks seasonals" />
      </div>

      <Card
        title="Demand and staffing by month"
        description={dept === 'All' ? 'All four departments' : `${dept} · forecast model ${forecast?.backtests?.[dept]?.chosen?.replace(/_/g, ' ')}`}
        actions={
          <Segmented label="Department" value={dept} onChange={setDept}
            options={[{ value: 'All', label: 'All' }, ...DEPTS.map((d) => ({ value: d, label: <><DeptDot dept={d} /><span className="hidden md:inline">{SHORT[d]}</span></> }))]} />
        }
        bodyClass="p-0"
      >
        {ready ? (
          <div className="grid xl:grid-cols-2">
            <div className="p-4 xl:border-r" style={{ borderColor: 'var(--border)' }}>
              <div className="t-sm font-medium">Forecast requests</div>
              <div className="t-xs t-muted mb-2">{dept === 'All' ? 'Monthly forecast per department' : 'Forecast with its likely range, and 2025 actuals'}</div>
              <DemandChart forecast={forecast.forecast} dept={dept} height={260} />
            </div>
            <div className="p-4 border-t xl:border-t-0" style={{ borderColor: 'var(--border)' }}>
              <div className="t-sm font-medium">Crews per month</div>
              <div className="t-xs t-muted mb-2">Click a month to ask why the plan staffs it that way</div>
              <CrewChart plan={plan} dept={dept} height={260} onMonth={(m) => {
                const d = dept === 'All' ? 'Parks' : dept
                openAsk(`Why does ${d} have ${plan.crews[d][m - 1] + plan.seasonal[d][m - 1]} crews in ${MONTHS[m - 1]}?`)
              }} />
            </div>
          </div>
        ) : <div className="p-4"><div className="skeleton h-[280px]" /></div>}
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] mt-6">
        {ready && (dept === 'All' ? <DeptTable plan={plan} baselines={baselines} /> : <MonthTable plan={plan} dept={dept} />)}
        {ready && <Changes plan={plan} />}
      </div>
    </div>
  )
}

function DeptTable({ plan, baselines }: { plan: any; baselines: any }) {
  return (
    <Card title="By department" bodyClass="overflow-x-auto">
      <table className="data">
        <thead><tr><th>Department</th><th className="r">Cost</th><th className="r">On time</th><th className="r">Flat staffing</th><th className="r">Today’s crews</th><th className="r">Crews (min–max)</th><th className="r">vs flat</th></tr></thead>
        <tbody>{DEPTS.map((d) => {
          const crews = plan.crews[d].map((x: number, i: number) => x + plan.seasonal[d][i])
          const f = baselines.flat.by_dept[d]
          const diff = plan.by_dept[d].total_cost - f.total_cost
          return (
            <tr key={d}>
              <td className="whitespace-nowrap"><span className="flex items-center gap-2"><DeptDot dept={d} />{d}</span></td>
              <td className="r">{moneyM(plan.by_dept[d].total_cost)}</td>
              <td className="r font-medium">{pct(plan.by_dept[d].on_time_rate)}</td>
              <td className="r t-muted">{pct(f.on_time_rate)}</td>
              <td className="r">{plan.starting_crews?.[d]}</td>
              <td className="r">{Math.min(...crews)}–{Math.max(...crews)}</td>
              <td className="r" style={{ color: Math.abs(diff) < 5000 ? 'var(--muted)' : diff < 0 ? 'var(--good)' : 'var(--danger)' }}>{Math.abs(diff) < 5000 ? '—' : `${diff < 0 ? '−' : '+'}${moneyM(Math.abs(diff))}`}</td>
            </tr>
          )
        })}</tbody>
      </table>
    </Card>
  )
}

function MonthTable({ plan, dept }: { plan: any; dept: string }) {
  const rows = plan.rows.filter((r: any) => r.dept === dept)
  return (
    <Card title={`${dept} by month`} description="Value of +1 crew: the late cost an extra crew would save that month (LP shadow price)." bodyClass="overflow-x-auto">
      <table className="data">
        <thead><tr><th>Month</th><th className="r">Demand</th><th className="r">Crews</th><th className="r">Hire</th><th className="r">Release</th><th className="r">Seasonal</th><th className="r">On time</th><th className="r">Cost</th><th className="r">Value of +1 crew</th></tr></thead>
        <tbody>{rows.map((r: any) => (
          <tr key={r.month}>
            <td>{MONTHS[r.month - 1]}</td><td className="r">{num(r.demand)}</td><td className="r">{r.crews}</td>
            <td className="r">{r.hires || '–'}</td><td className="r">{r.releases || '–'}</td><td className="r">{r.seasonal || '–'}</td>
            <td className="r">{pct(r.on_time_rate, 0)}</td>
            <td className="r">{money(r.cost_crew + r.cost_seasonal + r.cost_severance + r.cost_late + r.cost_late30)}</td>
            <td className="r">{r.shadow_value ? money(r.shadow_value) : '–'}</td>
          </tr>))}
        </tbody>
      </table>
    </Card>
  )
}

/** Plain-language list of what the plan changes, generated from the plan itself. */
function Changes({ plan }: { plan: any }) {
  const items: { icon: any; text: string }[] = []
  for (const d of DEPTS) {
    const hires = plan.hires[d].map((h: number, i: number) => [h, i]).filter(([h]: number[]) => h > 0)
    const rel = plan.releases[d].map((h: number, i: number) => [h, i]).filter(([h]: number[]) => h > 0)
    const seas = plan.seasonal[d].map((h: number, i: number) => [h, i]).filter(([h]: number[]) => h > 0)
    if (hires.length) items.push({ icon: TrendingUp, text: `${d}: hire ${hires.map(([h, i]: number[]) => `${h} in ${MONTHS[i]}`).join(', ')} (productive a month later).` })
    if (rel.length) items.push({ icon: TrendingDown, text: `${d}: release ${rel.map(([h, i]: number[]) => `${h} after ${MONTHS[i]}`).join(', ')}.` })
    if (seas.length) items.push({ icon: Users, text: `${d}: seasonal crews ${seas.map(([h, i]: number[]) => `${MONTHS[i]} ${h}`).join(' · ')}.` })
    if (!hires.length && !rel.length && !seas.length) items.push({ icon: Users, text: `${d}: hold at ${plan.crews[d][0]} crews all year.` })
  }
  return (
    <Card title="What the plan changes">
      <ul className="space-y-3">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2.5 t-sm"><it.icon size={16} className="t-muted flex-none mt-0.5" /><span>{it.text}</span></li>
        ))}
      </ul>
    </Card>
  )
}

export function LoadError() {
  return <Card><div className="t-sm">Couldn’t load planning data. Check that the API is running on port 8000.</div></Card>
}
