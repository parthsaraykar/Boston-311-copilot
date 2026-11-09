import { useEffect, useMemo, useState } from 'react'
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip as LTooltip } from 'react-leaflet'
import { Layers, MapPin, Radio } from 'lucide-react'
import { DEPTS, SHORT, get, num, pct } from '../api'
import { timeAgo } from '../AgentTrace'
import { Card, DeptDot, PageHeader, Segmented, Switch } from '../ui'

// sequential blue ramp (light -> dark = more requests closed late)
const RAMP = ['#dbe8fc', '#b7d3f6', '#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281']
const BREAKS = [0.15, 0.2, 0.25, 0.3, 0.35, 0.42]
const rampColor = (late: number) => RAMP[BREAKS.findIndex((b) => late < b) === -1 ? RAMP.length - 1 : BREAKS.findIndex((b) => late < b)]

export default function Pulse() {
  const [data, setData] = useState<any>(null)
  const [live, setLive] = useState<any[]>([])
  const [dept, setDept] = useState<string>('All')
  const [layers, setLayers] = useState({ ontime: true, open: true, filed: true })
  const [sel, setSel] = useState<any>(null)

  useEffect(() => { get('/pulse').then((d) => { setData(d); setLive(d.filed) }).catch(() => setData({ error: true })) }, [])
  useEffect(() => {
    const id = setInterval(() => get('/pulse/live').then((d) => setLive(d.filed)).catch(() => {}), 5000)
    return () => clearInterval(id)
  }, [])

  const grid = useMemo(() => {
    if (!data?.grid) return []
    return data.grid.map((c: any) => {
      const n = dept === 'All' ? c.n : (c.by_dept[dept] || 0)
      const top = dept === 'All' ? c.top_dept : dept
      return { ...c, n, top }
    }).filter((c: any) => c.n > 0)
  }, [data, dept])
  const maxN = Math.max(1, ...grid.map((c: any) => c.n))
  const feats = data?.neighborhoods?.features || []
  const ranked = [...feats].sort((a: any, b: any) => a.properties.on_time - b.properties.on_time)

  if (!data) return <div className="skeleton h-[600px]" />
  if (data.error) return <Card>Map layers aren’t built yet. Run <code>python -m data.pulse</code>.</Card>

  return (
    <div>
      <PageHeader eyebrow="Intake · Live" title="City pulse"
        description="Where requests are open right now, how each neighborhood has been served, and what’s being filed in this app."
        actions={<span className="badge badge-good"><Radio size={12} />Live · {live.length} filed in app</span>} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
            <Segmented label="Department" value={dept} onChange={setDept}
              options={[{ value: 'All', label: 'All' }, ...DEPTS.map((d) => ({ value: d, label: <><DeptDot dept={d} /><span className="hidden md:inline">{SHORT[d]}</span></> }))]} />
            <div className="flex items-center gap-4 ml-auto t-sm">
              <Layers size={15} className="t-muted" />
              <Switch checked={layers.ontime} onChange={(v) => setLayers({ ...layers, ontime: v })} label="On-time" />
              <Switch checked={layers.open} onChange={(v) => setLayers({ ...layers, open: v })} label="Open now" />
              <Switch checked={layers.filed} onChange={(v) => setLayers({ ...layers, filed: v })} label="Filed here" />
            </div>
          </div>
          <div style={{ height: 620 }} className="map-muted relative">
            <MapContainer center={[42.315, -71.08]} zoom={12} style={{ height: '100%', width: '100%' }} scrollWheelZoom preferCanvas>
              <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} attribution="© OpenStreetMap contributors" />
              {layers.ontime && (
                <GeoJSON key={`nb-${dept}`} data={data.neighborhoods}
                  style={(f: any) => {
                    const p = f.properties
                    const ot = dept === 'All' ? p.on_time : p.by_dept[dept]?.on_time
                    return { color: '#ffffff', weight: 1.2, fillColor: ot == null ? '#d4d4d8' : rampColor(1 - ot), fillOpacity: 0.62 }
                  }}
                  onEachFeature={(f: any, layer: any) => {
                    layer.on({ click: () => setSel(f.properties) })
                    const p = f.properties
                    const ot = dept === 'All' ? p.on_time : p.by_dept[dept]?.on_time
                    layer.bindTooltip(`<strong>${p.name}</strong><br/>${ot == null ? 'No data' : `${Math.round(ot * 100)}% on time`} · ${p.open_now.toLocaleString()} open`, { sticky: true })
                  }} />
              )}
              {layers.open && grid.map((c: any, i: number) => (
                <CircleMarker key={`${dept}-${i}`} center={[c.lat, c.lon]} radius={2 + 11 * Math.sqrt(c.n / maxN)}
                  pathOptions={{ color: '#ffffff', weight: 0.8, fillColor: '#27272a', fillOpacity: 0.55 }}>
                  <LTooltip>{c.n.toLocaleString()} open · mostly {c.top}</LTooltip>
                </CircleMarker>
              ))}
              {layers.filed && live.map((r: any) => (
                <CircleMarker key={r.id} center={[r.lat, r.lon]} radius={8} pathOptions={{ color: '#18181b', weight: 3, fillColor: '#ffffff', fillOpacity: 1 }}>
                  <LTooltip>{r.type} · {r.neighborhood} · {timeAgo(r.ts)}</LTooltip>
                </CircleMarker>
              ))}
            </MapContainer>
            <Legend dept={dept} />
          </div>
        </div>

        <div className="space-y-6">
          {sel ? (
            <Card title={sel.name} description="Requests 2023–2025" actions={<button className="btn btn-ghost btn-sm" onClick={() => setSel(null)}>Clear</button>}>
              <div className="grid grid-cols-2 gap-4">
                <div><div className="eyebrow">On time</div><div className="text-xl font-semibold num">{pct(sel.on_time, 0)}</div></div>
                <div><div className="eyebrow">Open now</div><div className="text-xl font-semibold num">{num(sel.open_now)}</div></div>
              </div>
              <table className="data mt-4">
                <thead><tr><th>Department</th><th className="r">Requests</th><th className="r">On time</th></tr></thead>
                <tbody>{DEPTS.filter((d) => sel.by_dept[d]).map((d) => (
                  <tr key={d}><td><span className="flex items-center gap-2"><DeptDot dept={d} />{SHORT[d]}</span></td>
                    <td className="r">{num(sel.by_dept[d].requests)}</td><td className="r">{pct(sel.by_dept[d].on_time, 0)}</td></tr>))}
                </tbody>
              </table>
            </Card>
          ) : (
            <Card title="Least on time" description="Click a neighborhood on the map for details" bodyClass="p-0">
              <ul className="divide">
                {ranked.slice(0, 6).map((f: any) => (
                  <li key={f.properties.name}>
                    <button className="w-full text-left px-4 py-2.5 flex items-center gap-3 t-sm hover:bg-[var(--surface-2)]" onClick={() => setSel(f.properties)}>
                      <span className="w-3 h-3 rounded-sm flex-none" style={{ background: rampColor(1 - f.properties.on_time) }} />
                      <span className="flex-1">{f.properties.name}</span>
                      <span className="num t-2">{pct(f.properties.on_time, 0)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <Card title="Filed in this app" description="Updates every 5 seconds" bodyClass="p-0">
            {live.length === 0 ? <p className="t-sm t-muted p-4">No requests with a location yet. File one from “Report a problem” or the QR code.</p> : (
              <ul className="divide max-h-[300px] overflow-y-auto scroll-thin">
                {live.slice(0, 30).map((r: any) => (
                  <li key={r.id} className="px-4 py-2.5 t-sm flex items-center gap-2">
                    <MapPin size={14} className="flex-none t-2" />
                    <div className="min-w-0 flex-1"><div className="truncate font-medium">{r.type}</div><div className="t-xs t-muted truncate">{r.neighborhood} · {r.department}</div></div>
                    <span className="t-xs t-muted flex-none">{timeAgo(r.ts)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}

function Legend({ dept }: { dept: string }) {
  return (
    <div className="absolute left-3 bottom-3 z-[500] card p-3 t-xs space-y-2" style={{ boxShadow: 'var(--shadow-md)' }}>
      <div>
        <div className="font-medium mb-1">Closed late{dept !== 'All' ? ` · ${SHORT[dept]}` : ''}</div>
        <div className="flex items-center gap-0.5">
          {RAMP.map((c) => <span key={c} style={{ background: c, width: 18, height: 8, display: 'inline-block' }} />)}
        </div>
        <div className="flex justify-between t-muted mt-0.5"><span>&lt;15%</span><span>42%+</span></div>
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: '#27272a', opacity: .6 }} />Open now (size = count)</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: '#fff', boxShadow: '0 0 0 2px #18181b' }} />Filed here</span>
      </div>
    </div>
  )
}
