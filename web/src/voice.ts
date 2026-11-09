import { useEffect, useRef, useState } from 'react'
import { post } from './api'

export type VoiceState = 'idle' | 'recording' | 'transcribing'
const MAX_SECONDS = 30
const TARGET_RATE = 16000

/**
 * Record from the mic and transcribe with local Whisper.
 * Captures raw PCM samples straight from the Web Audio graph (no MediaRecorder, no codecs), so it behaves the
 * same in Chrome, Edge, Brave, Firefox and Safari. Samples are downsampled to 16 kHz mono WAV in the page.
 */
export function useVoice(onText: (text: string, language?: string) => void) {
  const [state, setState] = useState<VoiceState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [seconds, setSeconds] = useState(0)
  const [level, setLevel] = useState(0)
  const stream = useRef<MediaStream | null>(null)
  const ctx = useRef<AudioContext | null>(null)
  const nodes = useRef<{ src?: MediaStreamAudioSourceNode; proc?: ScriptProcessorNode; mute?: GainNode }>({})
  const chunks = useRef<Float32Array[]>([])
  const timer = useRef<number | null>(null)
  const langRef = useRef('auto')
  const recording = useRef(false)

  const release = () => {
    if (timer.current) window.clearInterval(timer.current)
    timer.current = null
    try { nodes.current.src?.disconnect(); nodes.current.proc?.disconnect(); nodes.current.mute?.disconnect() } catch { /* already gone */ }
    if (nodes.current.proc) nodes.current.proc.onaudioprocess = null
    nodes.current = {}
    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null
    ctx.current?.close().catch(() => {})
    ctx.current = null
    setLevel(0)
  }
  useEffect(() => release, [])

  async function start(language = 'auto') {
    setError(null)
    langRef.current = language
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError('The microphone needs a secure page (https or localhost). Open the app on localhost, or type your message.')
      return
    }
    const AC: typeof AudioContext | undefined = window.AudioContext || (window as any).webkitAudioContext
    if (!AC) { setError('This browser can’t record audio. Please type your message.'); return }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
    } catch (e: any) {
      setError(e?.name === 'NotAllowedError' || e?.name === 'SecurityError'
        ? 'Microphone access is blocked. Allow it for this site in the browser’s address bar, then try again.'
        : e?.name === 'NotFoundError' ? 'No microphone was found.' : `Couldn’t open the microphone (${e?.name || e}).`)
      return
    }
    try {
      const ac = new AC()
      ctx.current = ac
      if (ac.state === 'suspended') await ac.resume()
      const src = ac.createMediaStreamSource(stream.current)
      const proc = ac.createScriptProcessor(4096, 1, 1)
      const mute = ac.createGain()
      mute.gain.value = 0 // the processor must reach the destination to run; keep it silent
      chunks.current = []
      proc.onaudioprocess = (ev) => {
        if (!recording.current) return
        const input = ev.inputBuffer.getChannelData(0)
        chunks.current.push(new Float32Array(input))
        let peak = 0
        for (let i = 0; i < input.length; i += 8) peak = Math.max(peak, Math.abs(input[i]))
        setLevel(Math.min(1, peak * 3))
      }
      src.connect(proc)
      proc.connect(mute)
      mute.connect(ac.destination)
      nodes.current = { src, proc, mute }
    } catch (e: any) {
      release()
      setError(`Couldn’t start recording (${e?.message || e}).`)
      return
    }
    recording.current = true
    setSeconds(0)
    setState('recording')
    const t0 = Date.now()
    timer.current = window.setInterval(() => {
      const s = Math.floor((Date.now() - t0) / 1000)
      setSeconds(s)
      if (s >= MAX_SECONDS) stop()
    }, 250)
  }

  async function stop() {
    if (!recording.current) return
    recording.current = false
    const rate = ctx.current?.sampleRate || 48000
    const captured = chunks.current
    chunks.current = []
    release()
    const total = captured.reduce((n, c) => n + c.length, 0)
    if (total < rate * 0.4) {
      setState('idle')
      setError('That was too short. Press Speak, say your message, then press Stop.')
      return
    }
    const pcm = new Float32Array(total)
    let o = 0, peak = 0
    for (const c of captured) { pcm.set(c, o); o += c.length }
    for (let i = 0; i < pcm.length; i += 4) peak = Math.max(peak, Math.abs(pcm[i]))
    if (peak < 0.003) {
      // the browser got a stream but it's silent: usually the OS hasn't given the browser mic access
      setState('idle')
      setError('The microphone sent only silence. On a Mac, check System Settings → Privacy & Security → Microphone and allow your browser, then reload. Also check the input device in Sound settings.')
      return
    }
    setState('transcribing')
    try {
      const wav = encodeWav(downsample(pcm, rate, TARGET_RATE), TARGET_RATE)
      const r = await post('/intake/transcribe', { audio_b64: wav, language: langRef.current })
      if (r.error || !r.text) setError(r.error || 'I couldn’t make out any words. Try again a little closer to the mic.')
      else onText(r.text, r.language)
    } catch (e: any) {
      const msg = String(e?.message || e)
      setError(msg.includes('503') ? 'Speech-to-text isn’t installed on the server.'
        : msg.includes('Failed to fetch') ? 'Couldn’t reach the server. Is the API running?'
        : `Couldn’t transcribe the recording (${msg.slice(0, 120)}).`)
    } finally {
      setState('idle')
    }
  }

  return { state, error, seconds, level, start, stop, clearError: () => setError(null), maxSeconds: MAX_SECONDS }
}

/** Average-based downsampling (acts as a simple low-pass filter). */
function downsample(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return input
  const ratio = from / to
  const out = new Float32Array(Math.floor(input.length / ratio))
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(input.length, Math.floor((i + 1) * ratio))
    let sum = 0
    for (let j = start; j < end; j++) sum += input[j]
    out[i] = sum / Math.max(1, end - start)
  }
  return out
}

function encodeWav(pcm: Float32Array, rate: number): string {
  const out = new DataView(new ArrayBuffer(44 + pcm.length * 2))
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) out.setUint8(o + i, s.charCodeAt(i)) }
  w(0, 'RIFF'); out.setUint32(4, 36 + pcm.length * 2, true); w(8, 'WAVE'); w(12, 'fmt ')
  out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true)
  out.setUint32(24, rate, true); out.setUint32(28, rate * 2, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true)
  w(36, 'data'); out.setUint32(40, pcm.length * 2, true)
  for (let i = 0; i < pcm.length; i++) out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, pcm[i])) * 0x7fff, true)
  const bytes = new Uint8Array(out.buffer)
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + 0x8000)))
  return btoa(bin)
}
