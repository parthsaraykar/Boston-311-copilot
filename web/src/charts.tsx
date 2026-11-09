import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis, Cell, ReferenceDot,
} from 'recharts'
import { CHART_TOKENS, useTokens } from './theme'
import { DEPTS, DEPT_VAR, MONTHS, money, moneyM, num, pct } from './api'

const axis = (t: Record<string, string>) => ({ stroke: t['--grid'], tick: { fill: t['--muted'], fontSize: 11.5 }, tickLine: false, axisLine: false })

function TT({ active, payload, label, fmt = num, title }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="tt">
      <div className="font-semibold mb-1">{title ? title(label) : label}</div>
      {payload.filter((p: any) => p.value != null && !Array.isArray(p.value) && p.name !== 'band').map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span aria-hidden style={{ width: 10, height: 3, background: p.color || p.stroke, display: 'inline-block' }} />
          <span className="text-2">{p.name}</span><span className="ml-auto font-semibold pl-3">{fmt(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

/** Forecast mean with the p10-p90 band, plus 2025 actuals, for one department (or all four as lines). */
export function DemandChart({ forecast, dept, height = 240 }: { forecast: any[]; dept: string; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  if (dept === 'All') {
    const data = MONTHS.map((m, i) => {
      const row: any = { month: m }
      DEPTS.forEach((d) => { row[d] = forecast.find((f) => f.dept === d && f.month === `2025-${String(i + 1).padStart(2, '0')}`)?.mean })
      return row
    })
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 0 }}>
          <CartesianGrid stroke={t['--grid']} vertical={false} />
          <XAxis dataKey="month" {...axis(t)} />
          <YAxis {...axis(t)} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} width={44} />
          <Tooltip content={<TT />} />
          <Legend itemSorter={null} iconSize={9} wrapperStyle={{ fontSize: 12, paddingTop: 4 }} formatter={(v: any) => <span style={{ color: t['--text-2'] }}>{v}</span>} />
          {DEPTS.map((d) => <Line isAnimationActive={false} key={d} dataKey={d} name={d} stroke={t[DEPT_VAR[d]]} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />)}
        </LineChart>
      </ResponsiveContainer>
    )
  }
  const color = t[DEPT_VAR[dept]]
  const data = forecast.filter((f) => f.dept === dept).map((f) => ({
    month: MONTHS[Number(f.month.slice(5)) - 1], mean: f.mean, band: [f.p10, f.p90], actual: f.actual,
    p10: f.p10, p90: f.p90,
  }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="month" {...axis(t)} />
        <YAxis {...axis(t)} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} width={44} />
        <Tooltip content={<TT />} />
        <Legend itemSorter={null} iconSize={9} wrapperStyle={{ fontSize: 12, paddingTop: 4 }} formatter={(v: any) => <span style={{ color: t['--text-2'] }}>{v}</span>} />
        <Area dataKey="band" name="Likely range (p10–p90)" stroke="none" fill={t['--band']} fillOpacity={0.7} isAnimationActive={false} legendType="square" />
        <Line isAnimationActive={false} dataKey="mean" name="Forecast" stroke={color} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
        <Line isAnimationActive={false} dataKey="actual" name="2025 actual" stroke={t['--text-2']} strokeWidth={2} strokeDasharray="4 3" dot={{ r: 3 }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Crews per month. One department: permanent + seasonal stacked. All: stacked by department. */
export function CrewChart({ plan, dept, onMonth, height = 240 }: { plan: any; dept: string; onMonth?: (m: number) => void; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  const data = MONTHS.map((m, i) => {
    const row: any = { month: m, i }
    if (dept === 'All') DEPTS.forEach((d) => { row[d] = plan.crews[d][i] + plan.seasonal[d][i] })
    else {
      row.Permanent = plan.crews[dept][i]
      row.Seasonal = plan.seasonal[dept][i] || null
      row.Hires = plan.hires[dept][i] || null
    }
    return row
  })
  const click = (s: any) => { if (s && onMonth && s.activeTooltipIndex != null) onMonth(Number(s.activeTooltipIndex) + 1) }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 0 }} onClick={click} barCategoryGap="22%">
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="month" {...axis(t)} />
        <YAxis {...axis(t)} width={36} allowDecimals={false} />
        <Tooltip content={<TT fmt={(v: number) => v.toFixed(0)} title={(l: string) => `${l} — click to ask why`} />} cursor={{ fill: t['--grid'], opacity: 0.5 }} />
        <Legend itemSorter={null} iconSize={9} wrapperStyle={{ fontSize: 12, paddingTop: 4 }} formatter={(v: any) => <span style={{ color: t['--text-2'] }}>{v}</span>} />
        {dept === 'All'
          ? DEPTS.map((d, k) => <Bar isAnimationActive={false} key={d} dataKey={d} stackId="a" fill={t[DEPT_VAR[d]]} stroke={t['--surface']} strokeWidth={1}
              radius={k === DEPTS.length - 1 ? [4, 4, 0, 0] : 0} cursor="pointer" />)
          : <>
            <Bar isAnimationActive={false} dataKey="Permanent" stackId="a" fill={t[DEPT_VAR[dept]]} stroke={t['--surface']} strokeWidth={1} cursor="pointer" />
            <Bar isAnimationActive={false} dataKey="Seasonal" name="Seasonal (Parks)" stackId="a" fill={t['--neutral']} stroke={t['--surface']} strokeWidth={1} radius={[4, 4, 0, 0]} cursor="pointer" />
          </>}
      </BarChart>
    </ResponsiveContainer>
  )
}

export function FrontierChart({ frontier, target, height = 220 }: { frontier: any[]; target: number; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  const data = frontier.map((f) => ({ x: Math.round(f.target * 100), cost: f.total_cost, ontime: f.on_time_rate }))
  const sel = data.find((d) => d.x === Math.round(target * 100))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 10, right: 16, left: 8, bottom: 14 }}>
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="x" {...axis(t)} tickFormatter={(v) => `${v}%`} label={{ value: 'On-time target in every department', position: 'insideBottom', offset: -8, fill: t['--muted'], fontSize: 12 }} />
        <YAxis {...axis(t)} tickFormatter={(v) => `$${(v / 1e6).toFixed(1)}M`} width={56} domain={['dataMin - 100000', 'dataMax + 100000']} />
        <Tooltip content={<TT fmt={moneyM} title={(l: number) => `Target ${l}%`} />} />
        <Line isAnimationActive={false} dataKey="cost" name="Cheapest plan cost" stroke={t['--accent']} strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
        {sel && <ReferenceDot x={sel.x} y={sel.cost} r={8} fill={t['--accent']} stroke={t['--surface']} strokeWidth={2} />}
      </LineChart>
    </ResponsiveContainer>
  )
}

/** Diverging bars: change in total cost from the saved plan at the low / high value of each input (re-planned). */
export function TornadoChart({ rows, height = 260 }: { rows: any[]; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  const data = rows.map((r) => ({ input: `${r.input} (${r.range})`, low: r.low_replanned, high: r.high_replanned }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 20, left: 8, bottom: 4 }} barCategoryGap="28%">
        <CartesianGrid stroke={t['--grid']} horizontal={false} />
        <XAxis type="number" {...axis(t)} tickFormatter={(v) => `${v >= 0 ? '+' : '−'}$${Math.abs(v / 1e6).toFixed(1)}M`} />
        <YAxis type="category" dataKey="input" {...axis(t)} width={230} tick={{ fill: t['--text-2'], fontSize: 12 }} />
        <ReferenceLine x={0} stroke={t['--muted']} />
        <Tooltip content={<TT fmt={(v: number) => `${v >= 0 ? '+' : '−'}${money(Math.abs(v))}`} />} />
        <Legend itemSorter={null} iconSize={9} wrapperStyle={{ fontSize: 12, paddingTop: 4 }} formatter={(v: any) => <span style={{ color: t['--text-2'] }}>{v}</span>} />
        <Bar isAnimationActive={false} dataKey="low" name="Low value" fill={t['--s-pw']} radius={[3, 3, 3, 3]} barSize={9} />
        <Bar isAnimationActive={false} dataKey="high" name="High value" fill={t['--s-bt']} radius={[3, 3, 3, 3]} barSize={9} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function HistogramChart({ costs, height = 200 }: { costs: number[]; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  const lo = Math.min(...costs), hi = Math.max(...costs)
  const bins = 14
  const w = (hi - lo) / bins || 1
  const data = Array.from({ length: bins }, (_, i) => ({
    x: lo + w * (i + 0.5), label: `${moneyM(lo + w * i)}–${moneyM(lo + w * (i + 1))}`,
    years: costs.filter((c) => c >= lo + w * i && (i === bins - 1 ? c <= hi : c < lo + w * (i + 1))).length,
  }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="x" {...axis(t)} tickFormatter={(v) => `$${(v / 1e6).toFixed(1)}M`} />
        <YAxis {...axis(t)} width={30} allowDecimals={false} />
        <Tooltip content={({ active, payload }: any) => active && payload?.length ? (
          <div className="tt"><div className="font-semibold">{payload[0].payload.label}</div>{payload[0].value} of 100 years</div>) : null} />
        <Bar isAnimationActive={false} dataKey="years" name="Simulated years" fill={t['--accent']} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Live demand so far vs the forecast band for one department. */
export function LiveChart({ months, dept, height = 200 }: { months: any[]; dept: string; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  const data = months.map((m) => ({ month: MONTHS[m.month - 1], band: [m.p10, m.p90], forecast: m.forecast, actual: m.actual, out: m.outside_band }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="month" {...axis(t)} />
        <YAxis {...axis(t)} width={44} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
        <Tooltip content={<TT />} />
        <Legend itemSorter={null} iconSize={9} wrapperStyle={{ fontSize: 12, paddingTop: 4 }} formatter={(v: any) => <span style={{ color: t['--text-2'] }}>{v}</span>} />
        <Area dataKey="band" name="Forecast band" stroke="none" fill={t['--band']} fillOpacity={0.7} isAnimationActive={false} legendType="square" />
        <Line isAnimationActive={false} dataKey="forecast" name="Forecast" stroke={t[DEPT_VAR[dept]]} strokeWidth={2} dot={false} />
        <Line isAnimationActive={false} dataKey="actual" name="Actual so far" stroke={t['--text']} strokeWidth={2}
          dot={(p: any) => <circle key={p.index} cx={p.cx} cy={p.cy} r={p.payload.out ? 6 : 3.5} fill={p.payload.out ? t['--accent'] : t['--text']} stroke={t['--surface']} strokeWidth={2} />} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export function RateBars({ data, height = 200, fmt = pct }: { data: { name: string; value: number }[]; height?: number; fmt?: (v: number) => string }) {
  const t = useTokens(CHART_TOKENS)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 16, right: 8, left: 0, bottom: 0 }} barCategoryGap="30%">
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="name" {...axis(t)} />
        <YAxis {...axis(t)} width={40} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
        <Tooltip content={<TT fmt={fmt} />} />
        <Bar isAnimationActive={false} dataKey="value" name="Accuracy" fill={t['--accent']} radius={[4, 4, 0, 0]} label={{ position: 'top', fill: t['--text-2'], fontSize: 11, formatter: (v: any) => fmt(Number(v)) }}>
          {data.map((_, i) => <Cell key={i} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function CurveChart({ curve, height = 220 }: { curve: any[]; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  const data = curve.filter((c) => c.accuracy_auto != null).map((c) => ({ cut: c.cutoff, share: c.share_auto, acc: c.accuracy_auto }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 18, right: 12, left: 0, bottom: 14 }}>
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="cut" {...axis(t)} label={{ value: 'Confidence cut-off', position: 'insideBottom', offset: -8, fill: t['--muted'], fontSize: 12 }} />
        <YAxis {...axis(t)} width={40} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
        <Tooltip content={<TT fmt={pct} title={(l: number) => `Cut-off ${l}`} />} />
        <Legend itemSorter={null} verticalAlign="top" iconSize={9} wrapperStyle={{ fontSize: 12, paddingTop: 4 }} formatter={(v: any) => <span style={{ color: t['--text-2'] }}>{v}</span>} />
        <ReferenceLine x={0.6} stroke={t['--muted']} strokeDasharray="3 3" label={{ value: 'in use', fill: t['--muted'], fontSize: 11, position: 'insideBottomRight' }} />
        <Line isAnimationActive={false} dataKey="acc" name="Accuracy of auto-routed" stroke={t['--s-pw']} strokeWidth={2} dot={{ r: 3 }} />
        <Line isAnimationActive={false} dataKey="share" name="Share auto-routed" stroke={t['--s-bt']} strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}

/** Cumulative cost through the year for each strategy (one axis, ≤4 series, direct legend). */
export function CumulativeCostChart({ strategies, order, height = 260 }: { strategies: any; order: { key: string; label: string; color: string; dashed?: boolean }[]; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  const data = MONTHS.map((m, i) => {
    const row: any = { month: m }
    for (const o of order) {
      const rows = strategies[o.key].monthly.filter((r: any) => r.month <= i + 1)
      row[o.key] = rows.reduce((s: number, r: any) => s + r.cost, 0)
    }
    return row
  })
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="month" {...axis(t)} />
        <YAxis {...axis(t)} width={56} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
        <Tooltip content={<TT fmt={moneyM} title={(l: string) => `Cost through ${l}`} />} />
        <Legend itemSorter={null} iconSize={9} wrapperStyle={{ fontSize: 12, paddingTop: 4 }} formatter={(v: any) => <span style={{ color: t['--text-2'] }}>{v}</span>} />
        {order.map((o) => <Line isAnimationActive={false} key={o.key} dataKey={o.key} name={o.label} stroke={t[o.color] || o.color}
          strokeWidth={2} strokeDasharray={o.dashed ? '4 3' : undefined} dot={false} activeDot={{ r: 4 }} />)}
      </LineChart>
    </ResponsiveContainer>
  )
}

/** Crews per month: the January plan vs what the monitor ended up running, against actual demand ÷ crew output. */
export function CrewCompareChart({ plan, monitored, needed, dept, height = 220 }: { plan: number[]; monitored: number[]; needed: number[]; dept: string; height?: number }) {
  const t = useTokens(CHART_TOKENS)
  const data = MONTHS.map((m, i) => ({ month: m, plan: plan[i], monitored: monitored[i], needed: Math.round(needed[i] * 10) / 10 }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={t['--grid']} vertical={false} />
        <XAxis dataKey="month" {...axis(t)} />
        <YAxis {...axis(t)} width={36} allowDecimals={false} />
        <Tooltip content={<TT fmt={(v: number) => v.toFixed(0)} />} />
        <Legend itemSorter={null} iconSize={9} wrapperStyle={{ fontSize: 12, paddingTop: 4 }} formatter={(v: any) => <span style={{ color: t['--text-2'] }}>{v}</span>} />
        <Line isAnimationActive={false} dataKey="needed" name="Crews actual demand needed" stroke={t['--neutral']} strokeWidth={2} strokeDasharray="4 3" dot={false} />
        <Line isAnimationActive={false} dataKey="plan" name="January plan" stroke={t['--text-2']} strokeWidth={2} dot={false} />
        <Line isAnimationActive={false} dataKey="monitored" name="With monitor" stroke={t[DEPT_VAR[dept]]} strokeWidth={2.5} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}
