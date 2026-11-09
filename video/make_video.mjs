// Records the product demo video by driving the real app in Chrome.
// Usage: make api (in another terminal), then: make video
// Env: APP_URL (default http://localhost:8000), VOICE (macOS voice name), CHROME (path), RATE (speech rate, wpm)
import puppeteer from 'puppeteer-core'
import { execFileSync } from 'child_process'
import fs from 'fs'
import path from 'path'

const BASE = process.env.APP_URL || 'http://localhost:8000'
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.resolve('out')
const TMP = path.join(OUT, 'tmp')
const W = 1920, H = 1080
const RATE = process.env.RATE || '178'
fs.mkdirSync(TMP, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ---------- narration ----------
function pickVoice() {
  if (process.env.VOICE) return process.env.VOICE
  const list = execFileSync('say', ['-v', '?']).toString()
  for (const v of ['Ava (Premium)', 'Zoe (Premium)', 'Evan (Premium)', 'Nathan (Premium)', 'Ava (Enhanced)', 'Zoe (Enhanced)', 'Evan (Enhanced)', 'Samantha (Enhanced)', 'Samantha']) {
    if (list.split('\n').some((l) => l.startsWith(v + ' ') || l.startsWith(v + '\t'))) return v
  }
  return 'Samantha'
}
const KOKORO = fs.existsSync(path.resolve('models/kokoro-v1.0.onnx')) && fs.existsSync(path.resolve('.tts/bin/python')) && process.env.TTS !== 'say'
const NARRATOR = process.env.NARRATOR || 'af_heart'     // Kokoro voice for the narrator
const RESIDENT = process.env.RESIDENT || 'am_michael'   // Kokoro voice for the resident speaking into the mic
const VOICE = KOKORO ? `Kokoro ${NARRATOR}` : pickVoice()
const spoken = (t) => t.replace(/\b311\b/g, 'three one one')

/** Render many lines in one Kokoro process; returns durations. */
function kokoroBatch(items, voice, speed = Number(process.env.SPEED || 1.0)) {
  const batch = path.join(TMP, `batch-${voice}.json`)
  fs.writeFileSync(batch, JSON.stringify(items.map((i) => ({ text: spoken(i.text), out: i.out }))))
  const out = execFileSync(path.resolve('.tts/bin/python'), [path.resolve('tts.py'), '--batch', batch, '--voice', voice, '--speed', String(speed)]).toString()
  const d = Object.fromEntries(out.trim().split('\n').map((l) => { const [dur, f] = l.split('\t'); return [f, Number(dur)] }))
  return items.map((i) => d[i.out])
}

function tts(text, file) {
  const aiff = file.replace(/\.wav$/, '.aiff')
  execFileSync('say', ['-v', VOICE, '-r', RATE, '-o', aiff, spoken(text)])
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', aiff, '-ar', '48000', '-ac', '1', file])
  fs.unlinkSync(aiff)
  return Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file]).toString().trim())
}

// ---------- the story ----------
const SCENES = [
  { id: 'intro', tag: null, title: ['Boston 311 Copilot', 'Route every request right, then staff for it.'],
    say: 'Boston’s 311 line takes about eight hundred and forty requests a day. Whether they get fixed on time comes down to two things: sending each one to the right crew, and having enough crews when demand peaks. Boston 311 Copilot does both.',
    run: async (a) => { await a.go('#resident') } },
  { id: 'route', tag: 'Resident intake',
    say: 'A resident describes the problem in their own words. The copilot matches it to one of a hundred and seventy city service queues, uses the location to pick the Jamaica Plain district crew, and shows the expected fix time.',
    run: async (a) => {
      await a.type('#problem', 'big hole near the Jackson Sq T stop, almost blew a tire')
      await a.clickText('Submit request')
      await a.waitText('Request filed')
      await a.hover('.leaflet-container')
    } },
  { id: 'spanish', tag: 'Any language',
    say: 'It works in other languages too. This message in Spanish lands in the same pothole queue.',
    run: async (a) => {
      await a.clickText('Start over')
      await a.type('#problem', 'Un bache enorme en la calle Centre en Jamaica Plain, peligroso para los carros')
      await a.clickText('Submit request')
      await a.waitText('Request filed')
    } },
  { id: 'voice', tag: 'Voice, transcribed on the device',
    say: 'Residents can also just talk. Speech is transcribed by a local model, so nothing leaves the city’s servers and no audio is stored.',
    run: async (a) => {
      await a.clickText('Start over')
      await a.clickText('Speak')
      await sleep(5200)
      await a.clickText('Stop')
      await a.waitValue('#problem')
      await sleep(500)
      await a.clickText('Submit request')
      await a.waitText('Request filed')
    } },
  { id: 'safety', tag: 'Safety first',
    say: 'Anything dangerous, like a sparking wire or a gas smell, gets a call nine one one response instead of a ticket. In testing it caught all fifteen emergencies, with no false alarms.',
    run: async (a) => {
      await a.clickText('Start over')
      await a.type('#problem', 'downed wire sparking')
      await a.type('#where', 'Washington St, Roslindale')
      await a.clickText('Submit request')
      await a.waitText('Call 911 now')
    } },
  { id: 'plan', tag: '2025 crew plan',
    say: 'On the planning side, the copilot builds the cheapest twenty twenty-five crew plan for four departments. It costs seventeen point three million dollars, two point one million less than keeping today’s crews, and closes ninety-two percent of requests on time instead of seventy-five.',
    run: async (a) => {
      await a.go('#plan')
      await a.waitText('Demand and staffing by month')
      await sleep(1500)
      await a.hover('.recharts-wrapper', 1)
      await sleep(1200)
      await a.clickText('Parks', 'button')
    } },
  { id: 'ask', tag: 'Ask the plan',
    say: 'Planners can ask why. Every number in the answer comes from the plan itself, and the tools it used are listed underneath.',
    run: async (a) => {
      await a.clickText('Ask the plan')
      await sleep(600)
      await a.clickText('Why hire Parks crews in April?')
      await a.waitText('Verified')
      await sleep(1500)
      await a.click('[aria-label="Close panel"]')
    } },
  { id: 'scenario', tag: 'What if?',
    say: 'What if demand comes in ten percent higher? Keeping the plan would drop on time to fifty-five percent. Re-planning brings it back to ninety-one.',
    run: async (a) => {
      await a.go('#scenarios')
      await a.waitText('Inputs')
      await a.click('#sl-Demandvsforecast')
      await a.keys('ArrowRight', 2)
      await a.waitText('Keep the saved plan')
    } },
  { id: 'agents', tag: 'Agents, with a human in charge',
    say: 'Agents do the routine watching. The stress test agent hunts for the scenarios that hurt the plan most. The monitor compares live demand with the forecast, spots the drift, and drafts a re-plan, which only takes effect when a person approves it.',
    run: async (a) => {
      await a.go('#agents')
      await a.waitText('Stress test')
      await a.clickExact('Run')
      await a.waitText('Matches brute-force worst case')
      await a.clickText('Run monitor')
      await a.waitText('Re-plan awaiting approval', 30000)
      await a.scrollTo('text=Re-plan awaiting approval')
      await sleep(900)
      await a.clickText('Approve')
    } },
  { id: 'replay', tag: 'Proof on real data',
    say: 'Does it hold up? Replaying real twenty twenty-five demand month by month, the plan with the monitor would have saved half a million dollars and lifted on time from seventy-eight to ninety percent, taking Transportation from forty-five to ninety-eight percent.',
    run: async (a) => {
      await a.go('#replay')
      await a.waitText('Cumulative cost through 2025')
      await sleep(2500)
      await a.scrollBy(620)
    } },
  { id: 'pulse', tag: 'City pulse',
    say: 'City pulse shows where requests are open right now, how every neighborhood has been served, and new reports as they arrive.',
    run: async (a) => {
      await a.go('#pulse')
      await a.waitText('Least on time')
      await sleep(2200)
      await a.clickText('Longwood')
    } },
  { id: 'eval', tag: 'Tested, not assumed',
    say: 'And it is tested. On two hundred and one hand-labelled messages it picks the right request type ninety-four percent of the time, against eighty-three for a keyword baseline.',
    run: async (a) => {
      await a.go('#eval')
      await a.waitText('Request type accuracy')
      await sleep(2500)
      await a.scrollBy(520)
    } },
  { id: 'outro', tag: null, title: ['Boston 311 Copilot', 'Runs on a laptop with free, local models · github.com/parthsaraykar/Boston-311-copilot'],
    say: 'Boston 311 Copilot. Route every request right, then staff for it.',
    run: async () => {} },
]

// ---------- in-page overlay: cursor, captions, title cards ----------
const OVERLAY = () => {
  const css = `
  #vx-cursor{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;transition:transform .6s cubic-bezier(.3,.7,.2,1),opacity .3s;transform:translate(960px,600px)}
  #vx-ripple{position:fixed;width:36px;height:36px;margin:-18px 0 0 -18px;border-radius:99px;border:2px solid #1f4fd8;z-index:2147483646;pointer-events:none;opacity:0}
  #vx-ripple.go{animation:vxr .5s ease-out}
  @keyframes vxr{0%{opacity:.9;transform:scale(.3)}100%{opacity:0;transform:scale(1.6)}}
  #vx-cap{position:fixed;left:50%;bottom:44px;transform:translateX(-50%);max-width:1240px;z-index:2147483645;pointer-events:none;text-align:center;transition:opacity .3s}
  #vx-cap .tag{display:inline-block;font:600 15px Geist,system-ui;letter-spacing:.02em;color:#fff;background:#1f4fd8;padding:5px 12px;border-radius:8px;margin-bottom:10px}
  #vx-cap .line{font:500 27px/1.4 Geist,system-ui;color:#fff;background:rgba(9,9,11,.82);padding:10px 20px;border-radius:12px;display:inline-block;box-shadow:0 8px 30px rgba(0,0,0,.25)}
  #vx-title{position:fixed;inset:0;z-index:2147483644;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;
    background:radial-gradient(1200px 700px at 30% 20%,#2f63ea 0%,#1f4fd8 35%,#13318d 100%);color:#fff;transition:opacity .7s;opacity:0;pointer-events:none}
  #vx-title .t{font:700 84px Geist,system-ui;letter-spacing:-.03em} #vx-title .s{font:500 30px Geist,system-ui;opacity:.9;max-width:1300px;text-align:center}
  #vx-title img{width:96px;height:96px;filter:drop-shadow(0 6px 20px rgba(0,0,0,.25))}`
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st)
  const cur = document.createElement('div'); cur.id = 'vx-cursor'
  cur.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l15 9-7 1.6L9 20z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>'
  const rip = document.createElement('div'); rip.id = 'vx-ripple'
  const cap = document.createElement('div'); cap.id = 'vx-cap'
  const title = document.createElement('div'); title.id = 'vx-title'
  document.body.append(cur, rip, cap, title)
  window.__vx = {
    move: (x, y) => { cur.style.transform = `translate(${x - 4}px, ${y - 3}px)` },
    ripple: (x, y) => { rip.style.left = x + 'px'; rip.style.top = y + 'px'; rip.classList.remove('go'); void rip.offsetWidth; rip.classList.add('go') },
    caption: (tag, line) => {
      cap.innerHTML = (tag ? `<div><span class="tag">${tag}</span></div>` : '') + (line ? `<div class="line">${line}</div>` : '')
      cap.style.opacity = line || tag ? '1' : '0'
    },
    title: (t, s, show) => {
      cur.style.opacity = show ? '0' : '1'
      title.innerHTML = `<img src="/logo.svg" alt=""><div class="t">${t}</div><div class="s">${s}</div>`
      title.style.opacity = show ? '1' : '0'
    },
  }
}

// ---------- helpers bound to the page ----------
function actions(page) {
  const pos = { x: 960, y: 600 }
  const center = async (handle) => {
    await handle.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }))
    await sleep(450)
    const b = await handle.boundingBox()
    if (!b) throw new Error('element not visible')
    return { x: b.x + b.width / 2, y: b.y + b.height / 2 }
  }
  const moveTo = async (x, y) => {
    await page.evaluate((x, y) => window.__vx.move(x, y), x, y)
    pos.x = x; pos.y = y
    await sleep(650)
  }
  const clickAt = async (x, y) => {
    await moveTo(x, y)
    await page.evaluate((x, y) => window.__vx.ripple(x, y), x, y)
    await page.mouse.click(x, y)
    await sleep(350)
  }
  const byText = async (text, tag = '*', exact = false) => {
    const xp = exact ? `//${tag}[normalize-space()='${text}']` : `//${tag}[contains(normalize-space(), '${text}')][not(.//${tag}[contains(normalize-space(), '${text}')])]`
    for (let i = 0; i < 40; i++) {
      const hs = await page.$$(`xpath/.${xp}`)
      for (const h of hs) { if (await h.boundingBox()) return h }
      await sleep(250)
    }
    throw new Error(`no element with text "${text}"`)
  }
  return {
    go: async (hash) => { await page.evaluate((h) => { window.location.hash = h }, hash); await sleep(900) },
    click: async (sel) => { const h = await page.waitForSelector(sel, { visible: true }); const c = await center(h); await clickAt(c.x, c.y) },
    clickText: async (text, tag = 'button') => { const h = await byText(text, tag); const c = await center(h); await clickAt(c.x, c.y) },
    clickExact: async (text, tag = 'button') => { const h = await byText(text, tag, true); const c = await center(h); await clickAt(c.x, c.y) },
    hover: async (sel, idx = 0) => { const hs = await page.$$(sel); const h = hs[idx] || hs[0]; if (!h) return; const c = await center(h); await moveTo(c.x, c.y); await page.mouse.move(c.x, c.y) },
    type: async (sel, text) => {
      const h = await page.waitForSelector(sel, { visible: true }); const c = await center(h); await clickAt(c.x - 120, c.y)
      await page.keyboard.type(text, { delay: 32 })
      await sleep(300)
    },
    keys: async (key, n = 1) => { for (let i = 0; i < n; i++) { await page.keyboard.press(key); await sleep(380) } },
    waitText: async (text, timeout = 20000) => { await page.waitForFunction((t) => document.body.innerText.includes(t), { timeout }, text); await sleep(300) },
    waitValue: async (sel, timeout = 60000) => { await page.waitForFunction((s) => document.querySelector(s)?.value?.length > 0, { timeout }, sel) },
    scrollBy: async (dy) => { await page.evaluate((dy) => window.scrollBy({ top: dy, behavior: 'smooth' }), dy); await sleep(1200) },
    scrollTo: async (sel) => {
      if (sel.startsWith('text=')) { const h = await byText(sel.slice(5), '*'); await h.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' })) }
      else await page.$eval(sel, (el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }))
      await sleep(900)
    },
  }
}

// captions show numbers the way people read them on screen; the voice keeps the spoken form
const CAPTION_NUMBERS = [
  ['eight hundred and forty', '840'], ['a hundred and seventy', '170'], ['two hundred and one', '201'],
  ['twenty twenty-five', '2025'], ['seventeen point three million dollars', '$17.3M'], ['two point one million', '$2.1M'],
  ['ninety-two percent', '92%'], ['instead of seventy-five', 'instead of 75%'], ['ten percent', '10%'],
  ['fifty-five percent', '55%'], ['back to ninety-one', 'back to 91%'], ['half a million dollars', '$0.5M'],
  ['from seventy-eight to ninety percent', 'from 78% to 90%'], ['from forty-five to ninety-eight percent', 'from 45% to 98%'],
  ['ninety-four percent', '94%'], ['eighty-three for', '83% for'], ['all fifteen', 'all 15'], ['nine one one', '911'],
]
const toCaption = (t) => CAPTION_NUMBERS.reduce((s, [a, b]) => s.split(a).join(b), t)

function splitSentences(text) {
  return text.match(/[^.!?]+[.!?]+/g)?.map((s) => s.trim()) || [text]
}

async function post(p, body) {
  const r = await fetch(BASE + p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  return r.json()
}

// ---------- main ----------
async function main() {
  console.log(`Voice: ${VOICE}`)
  // 1. narration audio
  for (const s of SCENES) s.audio = path.join(TMP, `${s.id}.wav`)
  const micText = 'There is a broken streetlight outside my house on Adams Street in Dorchester. It has been dark for a week.'
  const micWav = path.join(TMP, 'mic.wav')
  if (KOKORO) {
    const durs = kokoroBatch(SCENES.map((s) => ({ text: s.say, out: s.audio })), NARRATOR)
    SCENES.forEach((s, i) => { s.dur = durs[i] })
    kokoroBatch([{ text: micText, out: micWav }], RESIDENT)
    // Kokoro renders 24 kHz; the fake mic and the mix are happier at 48 kHz
    for (const f of [...SCENES.map((s) => s.audio), micWav]) {
      const tmp = f.replace(/\.wav$/, '.48k.wav')
      execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', f, '-ar', '48000', '-ac', '1', tmp]); fs.renameSync(tmp, f)
    }
  } else {
    for (const s of SCENES) s.dur = tts(s.say, s.audio)
    tts(micText, micWav)
  }
  const total = SCENES.reduce((n, s) => n + s.dur + 0.9, 0)
  console.log(`Narration: ${total.toFixed(0)} s over ${SCENES.length} scenes`)

  // 2. warm caches so nothing on screen waits on the CPU (geocoding, stress test, scenario)
  console.log('Warming up…')
  for (const t of ['big hole near the Jackson Sq T stop, almost blew a tire', 'Un bache enorme en la calle Centre en Jamaica Plain, peligroso para los carros'])
    await post('/intake/classify', { text: t, mode: 'fast', file: false })
  await post('/intake/classify', { text: 'downed wire sparking', location_text: 'Washington St, Roslindale', mode: 'fast', file: false })
  await post('/agent/stress-test', {})
  await post('/scenario', { target: 0.85, demand_mult: 1.1, storm: false, late_cost: 20, severance_rate: 0.25, seasonal_premium: 0.3, crew_output_mult: 1, training_months: 1 })
  await post('/demo/state', { as_of_month: 6, spike: {} })

  // 3. browser with a stand-in microphone that "speaks" the resident's sentence
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new', defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
    args: [`--window-size=${W},${H}`, '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required', '--hide-scrollbars'],
  })
  const page = await browser.newPage()
  page.on('pageerror', (e) => console.log('page error:', e.message))
  const micB64 = fs.readFileSync(micWav).toString('base64')
  await page.evaluateOnNewDocument((b64) => {
    try { localStorage.setItem('theme', 'light') } catch {}
    navigator.mediaDevices.getUserMedia = async () => {
      const ac = new AudioContext()
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
      const buf = await ac.decodeAudioData(bytes.buffer)
      const src = ac.createBufferSource(); src.buffer = buf
      const dest = ac.createMediaStreamDestination(); src.connect(dest); src.start(ac.currentTime + 0.3)
      return dest.stream
    }
  }, micB64)
  await page.goto(BASE + '/#resident', { waitUntil: 'networkidle0' })
  await page.evaluate(OVERLAY)
  await page.evaluate(() => document.fonts.ready)
  const a = actions(page)

  // 4. record: every frame is saved with the time it arrived, so quiet moments keep their real length
  const FR = path.join(TMP, 'frames')
  fs.rmSync(FR, { recursive: true, force: true }); fs.mkdirSync(FR)
  const frames = []
  const cdp = await page.createCDPSession()
  const t0 = Date.now()
  let n = 0
  cdp.on('Page.screencastFrame', async ({ data, sessionId }) => {
    const file = path.join(FR, `f${String(++n).padStart(6, '0')}.jpg`)
    frames.push({ file, t: (Date.now() - t0) / 1000 })
    fs.writeFile(file, Buffer.from(data, 'base64'), () => {})
    try { await cdp.send('Page.screencastFrameAck', { sessionId }) } catch {}
  })
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 88, maxWidth: W, maxHeight: H, everyNthFrame: 1 })
  await sleep(400)
  for (const s of SCENES) {
    s.start = (Date.now() - t0) / 1000
    console.log(`  ${s.id.padEnd(9)} ${s.start.toFixed(1)}s  (${s.dur.toFixed(1)}s narration)`)
    if (s.title) await page.evaluate((t, st) => window.__vx.title(t, st, true), s.title[0], s.title[1])
    // captions: one sentence at a time, timed by length
    const sentences = splitSentences(s.say).map(toCaption)
    const chars = sentences.reduce((n, l) => n + l.length, 0)
    const captionTimer = (async () => {
      for (const l of sentences) {
        await page.evaluate((tag, line) => window.__vx.caption(tag, line), s.title ? null : s.tag, l)
        await sleep((l.length / chars) * s.dur * 1000)
      }
    })()
    const minTime = sleep(s.dur * 1000 + 700)
    try { await s.run(a) } catch (e) { console.log(`    ! ${s.id}: ${e.message}`) }
    await Promise.all([minTime, captionTimer])
    if (s.title) { await page.evaluate(() => window.__vx.title('', '', false)); await sleep(500) }
    await page.evaluate(() => window.__vx.caption(null, null))
    await sleep(200)
  }
  await page.evaluate(() => window.__vx.title('Boston 311 Copilot', 'Route every request right, then staff for it.', true))
  await sleep(2500)
  const tEnd = (Date.now() - t0) / 1000
  await cdp.send('Page.stopScreencast')
  await sleep(500)
  await browser.close()
  // concat list with each frame held until the next one arrived
  const list = ['ffconcat version 1.0']
  frames.forEach((f, i) => {
    const next = i + 1 < frames.length ? frames[i + 1].t : tEnd
    list.push(`file '${f.file}'`, `duration ${Math.max(0.001, next - f.t).toFixed(4)}`)
  })
  list.push(`file '${frames[frames.length - 1].file}'`)
  const listFile = path.join(TMP, 'frames.txt')
  fs.writeFileSync(listFile, list.join('\n'))
  const lead = frames[0].t  // video starts at the first frame; shift audio by the same amount
  console.log(`Captured ${frames.length} frames over ${tEnd.toFixed(1)} s`)

  // 5. mux narration onto the recording
  const out = path.join(OUT, 'boston-311-copilot-demo.mp4')
  const inputs = ['-f', 'concat', '-safe', '0', '-i', listFile]
  const filters = []
  SCENES.forEach((s, i) => {
    inputs.push('-i', s.audio)
    const ms = Math.max(0, Math.round((s.start - lead + 0.25) * 1000))
    filters.push(`[${i + 1}:a]adelay=${ms}|${ms}[a${i}]`)
  })
  filters.push(`${SCENES.map((_, i) => `[a${i}]`).join('')}amix=inputs=${SCENES.length}:normalize=0:dropout_transition=0,apad[aout]`)
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...inputs, '-filter_complex', filters.join(';'),
    '-map', '0:v', '-map', '[aout]', '-shortest', '-fps_mode', 'cfr', '-r', '30', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', out], { stdio: 'inherit' })
  const dur = Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out]).toString())
  console.log(`\nDone: ${out}  (${dur.toFixed(0)} s, ${(fs.statSync(out).size / 1e6).toFixed(1)} MB)`)
}

main().catch((e) => { console.error(e); process.exit(1) })
