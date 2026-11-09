import { useEffect, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Check, Copy, Inbox, Smartphone } from 'lucide-react'
import { get, pct, post } from '../api'
import { timeAgo } from '../AgentTrace'
import { Card, Empty, PageHeader } from '../ui'

export default function Review() {
  const [rows, setRows] = useState<any[]>([])
  const [cats, setCats] = useState<any[]>([])
  const [live, setLive] = useState<any>(null)
  const [copied, setCopied] = useState(false)
  const load = () => { get('/review-queue').then(setRows).catch(() => {}); get('/intake/live').then(setLive).catch(() => {}) }
  useEffect(() => { load(); get('/intake/categories').then(setCats).catch(() => {}); const id = setInterval(load, 6000); return () => clearInterval(id) }, [])
  async function decide(id: string, decision: string, type?: string) { await post(`/review-queue/${id}`, { decision, type }); load() }
  const url = `${window.location.origin}${window.location.pathname}#file`

  return (
    <div>
      <PageHeader eyebrow="Intake" title="Review queue"
        description="Requests the router wasn’t sure about wait here for 311 staff instead of going straight to a crew." />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] items-start">
        <Card title="Waiting for review" description={`${rows.length} request${rows.length === 1 ? '' : 's'} under the 60% confidence cut-off`} bodyClass="p-0">
          {rows.length === 0 ? <Empty icon={<Inbox size={18} />} title="All clear">Low-confidence requests will appear here.</Empty> : (
            <ul className="divide">
              {rows.map((r) => (
                <li key={r.id} className="p-4">
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="t-sm">“{r.text_scrubbed}”</p>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        <span className="badge">{r.type}</span>
                        <span className="badge badge-warn num">{pct(r.confidence, 0)} confidence</span>
                        <span className="badge">{r.language}</span>
                        <span className="t-xs t-muted self-center">{timeAgo(r.ts)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-3">
                    <button className="btn btn-sm" onClick={() => decide(r.id, 'accept')}><Check />Accept</button>
                    <select aria-label="Re-route to another category" className="select" style={{ height: 28, width: 'auto', fontSize: '.8rem' }} defaultValue=""
                      onChange={(e) => e.target.value && decide(r.id, 'reroute', e.target.value)}>
                      <option value="">Re-route to…</option>
                      {cats.map((c) => <option key={c.id} value={c.type}>{c.name}</option>)}
                    </select>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-6">
          <Card title="File from your phone" description="Opens the resident form; filed requests count toward live demand">
            <div className="flex gap-4 items-center">
              <div className="p-2 rounded-lg bg-white border flex-none" style={{ borderColor: 'var(--border)' }}><QRCodeSVG value={url} size={112} /></div>
              <div className="min-w-0 space-y-2">
                <div className="flex items-center gap-1.5 t-sm"><Smartphone size={15} className="t-muted" />Scan to report a problem</div>
                <button className="btn btn-sm" onClick={() => { navigator.clipboard?.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>
                  {copied ? <Check /> : <Copy />}{copied ? 'Copied' : 'Copy link'}</button>
                <p className="t-xs t-muted break-all">{url}</p>
              </div>
            </div>
          </Card>
          <Card title="Recent requests" description={live ? `${live.total_filed} filed in this app` : ''} bodyClass="p-0">
            {!live?.recent?.length ? <Empty title="Nothing yet">Requests filed from the resident form appear here.</Empty> : (
              <ul className="divide max-h-[420px] overflow-y-auto scroll-thin">
                {live.recent.map((r: any) => (
                  <li key={r.id} className="px-4 py-2.5">
                    <div className="flex items-center gap-2 t-sm">
                      <span className="font-medium truncate flex-1">{r.type || (r.status === 'emergency' ? 'Emergency (911 shown)' : 'Not a city request')}</span>
                      <span className="t-xs t-muted flex-none">{timeAgo(r.ts)}</span>
                    </div>
                    <div className="t-xs t-muted truncate">{r.department || '—'}{r.neighborhood ? ` · ${r.neighborhood}` : ''}</div>
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
