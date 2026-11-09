import { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip as LTooltip, useMap } from 'react-leaflet'
import {
  ArrowRight, Camera, CheckCircle2, ChevronDown, CircleHelp, Clock, Languages, Lock, MapPin, Mic, Phone, RotateCcw,
  Route as RouteIcon, ShieldAlert, Square, Trash2, X,
} from 'lucide-react'
import { post, pct } from '../api'
import { useData } from '../data'
import { useVoice } from '../voice'
import { Card, Empty, KV, PageHeader, Spinner } from '../ui'

const EXAMPLES = [
  { text: 'big hole near the Jackson Sq T stop, almost blew a tire' },
  { text: 'Hay un bache enorme en la calle Centre cerca de Hyde Square' },
  { text: 'downed wire sparking', where: 'Washington St, Roslindale' },
  { text: 'rats running around the alley behind our building', where: '45 Dudley St' },
  { text: 'car parked on the sidewalk, strollers have to go in the street', where: 'Boylston St' },
]
const VOICE_LANGS = [
  { v: 'auto', l: 'Detect language' }, { v: 'en', l: 'English' }, { v: 'es', l: 'Español' }, { v: 'ht', l: 'Kreyòl ayisyen' },
  { v: 'zh', l: '中文' }, { v: 'vi', l: 'Tiếng Việt' }, { v: 'pt', l: 'Português' },
]
type Engine = 'fast' | 'cached' | 'llm'

function Recenter({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap()
  useEffect(() => { map.setView([lat, lon], 16) }, [lat, lon, map])
  return null
}

export default function Resident({ kiosk }: { kiosk: boolean }) {
  const { health } = useData()
  const [text, setText] = useState('')
  const [where, setWhere] = useState('')
  const [image, setImage] = useState<{ b64: string; url: string; name: string } | null>(null)
  const [engine, setEngine] = useState<Engine>('fast')
  const [voiceLang, setVoiceLang] = useState('auto')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [followUp, setFollowUp] = useState<{ text: string; question: string } | null>(null)
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)
  const llmReady = !!health?.intake_model_ready

  // links like #file?text=...&where=... prefill the form (e.g. a QR code on a poster); &go=1 submits it
  useEffect(() => {
    const q = new URLSearchParams(window.location.hash.split('?')[1] || '')
    if (q.get('text')) setText(q.get('text')!)
    if (q.get('where')) setWhere(q.get('where')!)
    if (q.get('text') && q.get('go') === '1') submit(undefined, { text: q.get('text')!, where: q.get('where') || '' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const voice = useVoice((t) => {
    setText((prev) => (prev ? prev.trimEnd() + ' ' : '') + t)
    textRef.current?.focus()
  })

  async function submit(clarification?: string, override?: { text: string; where: string }) {
    const body: any = { text: override?.text ?? (followUp ? followUp.text : text), mode: engine === 'fast' || !llmReady ? 'fast' : engine,
      source: kiosk ? 'qr' : 'web', location_text: (override ? override.where : where) || null }
    if (!body.text.trim() && !image) return
    if (clarification) body.clarification = clarification
    if (image) body.image_b64 = image.b64
    setBusy(true); setError(null)
    try {
      const r = await post('/intake/classify', body)
      setResult(r)
      if (r.status === 'clarify' && !clarification) setFollowUp({ text: body.text, question: r.question })
      else setFollowUp(null)
      setAnswer('')
    } catch {
      setError('We couldn’t reach the server. Please try again.')
    } finally { setBusy(false) }
  }

  function reset() {
    setText(''); setWhere(''); setImage(null); setResult(null); setFollowUp(null); setAnswer(''); setError(null)
    textRef.current?.focus()
  }

  function onPhoto(f?: File) {
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      const s = String(reader.result)
      setImage({ b64: s.slice(s.indexOf(',') + 1), url: s, name: f.name })
    }
    reader.readAsDataURL(f)
  }

  const recording = voice.state === 'recording'
  const transcribing = voice.state === 'transcribing'

  return (
    <div>
      <PageHeader
        eyebrow={kiosk ? undefined : 'Resident intake'}
        title="Report a problem"
        description="Describe what’s wrong in your own words, in any language. We’ll send it to the right city team."
        actions={!kiosk && (
          <label className="flex items-center gap-2 t-sm t-2">
            <span className="hidden sm:inline">Routing engine</span>
            <span className="relative">
              <select className="select" style={{ height: 32, width: 'auto' }} value={engine} onChange={(e) => setEngine(e.target.value as Engine)} aria-label="Routing engine">
                <option value="fast">Retrieval (default, most accurate)</option>
                <option value="cached" disabled={!llmReady}>Local LLM, demo cache</option>
                <option value="llm" disabled={!llmReady}>Local LLM, live (~20 s)</option>
              </select>
            </span>
          </label>
        )}
      />

      <div className={`grid gap-6 ${kiosk ? '' : 'xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]'}`}>
        <section className="card" aria-label="New request">
          <form className="card-b space-y-5" onSubmit={(e) => { e.preventDefault(); submit() }}>
            <div>
              <label htmlFor="problem" className="label">What’s the problem?</label>
              <div className="rounded-[10px] border transition-shadow focus-within:shadow-[var(--ring)]"
                style={{ borderColor: recording ? 'var(--danger)' : 'var(--border-strong)', background: 'var(--surface)' }}>
                <textarea id="problem" ref={textRef} rows={4} value={text} onChange={(e) => setText(e.target.value)}
                  className="w-full bg-transparent px-3 pt-3 pb-1 outline-none resize-none" style={{ color: 'var(--text)' }}
                  placeholder="e.g. A large pothole in the right lane, cars are swerving around it"
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit() }} disabled={!!followUp} />
                {image && (
                  <div className="px-3 pb-2">
                    <div className="inline-flex items-center gap-2 inset p-1.5 pr-2">
                      <img src={image.url} alt="Attached photo" className="w-10 h-10 object-cover rounded-md" />
                      <span className="t-xs t-2 max-w-[160px] truncate">{image.name}</span>
                      <button type="button" className="btn btn-ghost btn-sm btn-icon" style={{ width: 24, height: 24 }} onClick={() => setImage(null)} aria-label="Remove photo"><X size={14} /></button>
                    </div>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-1 px-2 py-1.5 border-t" style={{ borderColor: 'var(--border)' }}>
                  {recording ? (
                    <div className="flex items-center gap-3 w-full pl-1" role="status" aria-live="polite">
                      <span className="recording w-2.5 h-2.5 rounded-full" style={{ background: 'var(--danger)' }} />
                      <span className="t-sm num">Recording {fmtTime(voice.seconds)} <span className="t-muted">/ {fmtTime(voice.maxSeconds)}</span></span>
                      <LevelBars level={voice.level} />
                      <button type="button" className="btn btn-sm ml-auto" onClick={voice.stop}><Square size={13} fill="currentColor" />Stop</button>
                    </div>
                  ) : transcribing ? (
                    <div className="pl-1 py-1"><Spinner label="Transcribing on this device…" /></div>
                  ) : (
                    <>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => fileRef.current?.click()} disabled={!!followUp}><Camera />Photo</button>
                      <input ref={fileRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => onPhoto(e.target.files?.[0])} />
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => voice.start(voiceLang)} disabled={!!followUp || health?.speech === false}><Mic />Speak</button>
                      <div className="relative inline-flex items-center">
                        <Languages size={14} className="absolute left-2 t-muted pointer-events-none" />
                        <select aria-label="Spoken language" className="select" value={voiceLang} onChange={(e) => setVoiceLang(e.target.value)}
                          style={{ height: 28, width: 'auto', fontSize: '.8rem', paddingLeft: '1.6rem', border: 'none', background: 'transparent' }}>
                          {VOICE_LANGS.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}
                        </select>
                      </div>
                      <span className="ml-auto t-xs t-muted pr-1 hidden sm:inline">⌘↵ to submit</span>
                    </>
                  )}
                </div>
              </div>
              {voice.error && (
                <div role="alert" className="mt-2 flex items-start gap-2 t-sm" style={{ color: 'var(--danger)' }}>
                  <CircleHelp size={15} className="mt-0.5 flex-none" /><span>{voice.error}</span>
                  <button type="button" className="ml-auto t-xs underline" onClick={voice.clearError}>Dismiss</button>
                </div>
              )}
            </div>

            <div>
              <label htmlFor="where" className="label">Where is it? <span className="t-muted font-normal">Optional</span></label>
              <div className="relative">
                <MapPin size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2 t-muted pointer-events-none" />
                <input id="where" className="input" style={{ paddingLeft: '2rem' }} value={where} onChange={(e) => setWhere(e.target.value)}
                  placeholder="Street address, intersection or landmark" disabled={!!followUp} autoComplete="street-address" />
              </div>
              <p className="hint">The location decides which district crew gets it. You can also mention it in the description.</p>
            </div>

            {followUp && (
              <div className="rounded-[10px] p-4" style={{ background: 'var(--accent-soft)', border: '1px solid var(--accent-border)' }} role="region" aria-label="Follow-up question">
                <div className="flex items-start gap-2.5">
                  <CircleHelp size={18} style={{ color: 'var(--accent)' }} className="flex-none mt-0.5" />
                  <div className="flex-1">
                    <div className="font-medium">One quick question</div>
                    <p className="t-sm t-2 mt-0.5">{followUp.question}</p>
                    <div className="flex gap-2 mt-3">
                      <input className="input" autoFocus value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Your answer"
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); answer.trim() && submit(answer) } }} aria-label="Your answer" />
                      <button type="button" className="btn btn-primary" disabled={!answer.trim() || busy} onClick={() => submit(answer)}>Continue</button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {error && <p role="alert" className="t-sm" style={{ color: 'var(--danger)' }}>{error}</p>}

            {!followUp && (
              <div className="flex flex-wrap items-center gap-2">
                <button type="submit" className="btn btn-primary btn-lg" disabled={busy || (!text.trim() && !image) || recording || transcribing}>
                  {busy ? <Spinner /> : <>Submit request<ArrowRight /></>}
                </button>
                {(text || where || image || result) && <button type="button" className="btn btn-lg btn-ghost" onClick={reset}><RotateCcw />Start over</button>}
              </div>
            )}
            <p className="flex items-center gap-1.5 t-xs t-muted"><Lock size={12} />Phone numbers, emails and names are removed before anything is saved. Voice is transcribed on this server and not stored.</p>
          </form>

          {!kiosk && (
            <div className="border-t" style={{ borderColor: 'var(--border)' }}>
              <details className="group">
                <summary className="flex items-center gap-2 px-4 py-3 cursor-pointer t-sm t-2 list-none">
                  <ChevronDown size={15} className="transition-transform group-open:rotate-180" />Example requests
                </summary>
                <ul className="px-2 pb-3">
                  {EXAMPLES.map((e) => (
                    <li key={e.text}>
                      <button type="button" className="w-full text-left px-2.5 py-2 rounded-lg t-sm hover:bg-[var(--surface-2)] flex items-center gap-2"
                        onClick={() => { reset(); setText(e.text); setWhere(e.where || '') }}>
                        <span className="flex-1 truncate">{e.text}</span>
                        {e.where && <span className="t-xs t-muted flex items-center gap-1 flex-none"><MapPin size={12} />{e.where}</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}
        </section>

        <section aria-live="polite" aria-label="Routing result">
          {!result && <ResultPlaceholder />}
          {result?.status === 'emergency' && <EmergencyResult r={result} />}
          {result?.status === 'refused' && (
            <Card>
              <Empty icon={<CircleHelp size={18} />} title="We can only help with city service requests">{result.message}</Empty>
            </Card>
          )}
          {(result?.status === 'routed' || result?.status === 'clarify') && <RoutedResult r={result} kiosk={kiosk} />}
        </section>
      </div>
    </div>
  )
}

function ResultPlaceholder() {
  const steps = [
    ['Describe it', 'Type, speak or add a photo, in any language.'],
    ['We match the service', 'One of 170 city service queues, with a confidence score.'],
    ['The right crew gets it', 'The location picks the district team, and duplicates are flagged.'],
  ]
  return (
    <div className="card h-full">
      <div className="card-b">
        <div className="eyebrow mb-4">How it works</div>
        <ol className="space-y-5">
          {steps.map(([t, d], i) => (
            <li key={t} className="flex gap-3">
              <span className="w-7 h-7 rounded-full grid place-items-center t-sm font-semibold flex-none inset num">{i + 1}</span>
              <div><div className="font-medium">{t}</div><div className="t-sm t-muted">{d}</div></div>
            </li>
          ))}
        </ol>
        <div className="mt-6 p-3 rounded-lg flex gap-2.5 t-sm" style={{ background: 'var(--danger-soft)', color: 'var(--danger)', border: '1px solid var(--danger-border)' }}>
          <ShieldAlert size={16} className="flex-none mt-0.5" />
          <span>For fires, gas smells, downed wires or anyone hurt, call 911.</span>
        </div>
      </div>
    </div>
  )
}

function EmergencyResult(_props: { r: any }) {
  return (
    <div role="alert" className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--danger-border)', background: 'var(--surface)' }}>
      <div className="p-5 flex items-start gap-3" style={{ background: 'var(--danger)', color: '#fff' }}>
        <ShieldAlert size={26} className="flex-none" />
        <div>
          <div className="text-xl font-semibold tracking-tight">Call 911 now</div>
          <div className="opacity-90 mt-0.5">This sounds like a danger to life or property.</div>
        </div>
      </div>
      <div className="p-5 space-y-4">
        <p>311 can’t send help fast enough for this. Call 911 so responders can come right away.</p>
        <a href="tel:911" className="btn btn-danger btn-lg"><Phone />Call 911</a>
        <ul className="t-sm t-2 list-disc pl-5 space-y-1">
          <li>Stay well away from wires, smoke or the smell of gas.</li>
          <li>Don’t use light switches or open flames if you smell gas.</li>
        </ul>
        <p className="t-xs t-muted">Nothing was filed with 311.</p>
      </div>
    </div>
  )
}

function RoutedResult({ r, kiosk }: { r: any; kiosk: boolean }) {
  const loc = r.location
  const conf = r.confidence ?? 0
  const confLabel = conf >= 0.8 ? 'High' : conf >= 0.6 ? 'Medium' : 'Low'
  const eta = r.expected_fix_days == null ? 'No estimate' : r.expected_fix_days < 1.5 ? 'Usually within a day' : `Usually ~${Math.round(r.expected_fix_days)} days`
  return (
    <div className="card">
      <div className="card-b">
        <div className="flex items-center gap-2">
          {r.status === 'routed'
            ? <span className="badge badge-good"><CheckCircle2 size={13} />Request filed</span>
            : <span className="badge badge-accent"><CircleHelp size={13} />Needs one detail</span>}
          {r.request_id && <span className="t-xs t-muted mono ml-auto">Ref {r.request_id.replace('req_', '').toUpperCase()}</span>}
        </div>
        <div className="mt-3 text-xl font-semibold tracking-tight">{r.type_name}</div>
        <div className="t-2">{r.department}</div>

        <div className="mt-5">
          <KV items={[
            ['Service queue', <span className="mono t-xs break-all">{r.queue}</span>],
            ['Location', loc ? <span>{r.location_text || loc.display}<span className="t-muted"> · {loc.neighborhood}</span></span> : <span className="t-muted">Not found. Add a street or intersection.</span>],
            ['Expected', <span className="inline-flex items-center gap-1.5"><Clock size={13} className="t-muted" />{eta}</span>],
            ['Confidence', (
              <div className="flex items-center gap-3 max-w-[260px]">
                <div className="meter flex-1"><span style={{ width: `${Math.round(conf * 100)}%`, background: conf >= 0.6 ? 'var(--accent)' : 'var(--warn)' }} /></div>
                <span className="t-sm num">{pct(conf, 0)} · {confLabel}</span>
              </div>
            )],
          ]} />
        </div>
        {r.reason && <p className="mt-4 t-sm t-2 pl-3" style={{ borderLeft: '2px solid var(--border-strong)' }}>{r.reason}</p>}
        {r.photo_description && <p className="mt-2 t-sm t-2 flex gap-1.5"><Camera size={14} className="mt-0.5 t-muted" />{r.photo_description}</p>}
      </div>

      {loc && (
        <div className="px-4 pb-4">
          <div style={{ height: 230, borderColor: 'var(--border)' }} className="rounded-[10px] overflow-hidden border map-muted">
            <MapContainer center={[loc.lat, loc.lon]} zoom={16} style={{ height: '100%', width: '100%' }} scrollWheelZoom={false} attributionControl={false}>
              <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
              <Recenter lat={loc.lat} lon={loc.lon} />
              {r.similar_open?.map((d: any) => (
                <CircleMarker key={d.case_id} center={[d.lat, d.lon]} radius={6} pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#71717a', fillOpacity: 1 }}>
                  <LTooltip>Open since {d.opened}</LTooltip>
                </CircleMarker>
              ))}
              <CircleMarker center={[loc.lat, loc.lon]} radius={9} pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#1f4fd8', fillOpacity: 1 }}>
                <LTooltip>Your report</LTooltip>
              </CircleMarker>
            </MapContainer>
          </div>
          <div className="t-xs t-muted mt-1.5">Map © OpenStreetMap contributors</div>
        </div>
      )}

      {r.similar_open?.length > 0 && (
        <div className="border-t px-4 py-3" style={{ borderColor: 'var(--border)' }}>
          <div className="t-sm font-medium mb-1.5">{r.similar_open.length} similar open report{r.similar_open.length > 1 ? 's' : ''} nearby</div>
          <ul className="space-y-1">
            {r.similar_open.map((d: any) => (
              <li key={d.case_id} className="flex items-center gap-2 t-sm">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--neutral)' }} />
                <span className="truncate flex-1">{d.location || 'Nearby'}</span>
                <span className="t-xs t-muted num flex-none">{d.distance_m} m · since {d.opened}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!kiosk && (
        <details className="border-t group" style={{ borderColor: 'var(--border)' }}>
          <summary className="flex items-center gap-2 px-4 py-3 cursor-pointer t-sm t-2 list-none">
            <RouteIcon size={15} className="t-muted" />How this was matched
            <ChevronDown size={15} className="ml-auto transition-transform group-open:rotate-180" />
          </summary>
          <div className="px-4 pb-4 space-y-3">
            <div className="flex flex-wrap gap-1.5">
              <span className="badge">Engine: {r.mode === 'llm' ? 'local LLM' : 'retrieval'}{r.cached ? ' (cached)' : ''}</span>
              <span className="badge num">{r.latency_ms} ms</span>
              <span className="badge">Language: {r.language}</span>
              {r.privacy_removed?.length > 0 && <span className="badge"><Trash2 size={11} />Removed {r.privacy_removed.join(', ')}</span>}
            </div>
            <table className="data">
              <thead><tr><th>Closest categories</th><th className="r">Score</th></tr></thead>
              <tbody>{r.candidates?.slice(0, 5).map((c: any, i: number) => (
                <tr key={c.id}><td className={i === 0 ? 'font-medium' : ''}>{c.name}</td><td className="r num">{c.score.toFixed(2)}</td></tr>))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  )
}

function LevelBars({ level }: { level: number }) {
  return (
    <span className="flex items-end gap-0.5 h-4" aria-hidden>
      {[0.15, 0.35, 0.55, 0.75, 0.9].map((th, i) => (
        <span key={i} className="w-1 rounded-sm transition-all" style={{ height: `${30 + i * 17}%`, background: level >= th ? 'var(--danger)' : 'var(--surface-3)' }} />
      ))}
    </span>
  )
}

const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
