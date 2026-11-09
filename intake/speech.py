"""Local speech-to-text with Whisper (faster-whisper, CPU). Works in every browser: the page records audio,
converts it to 16 kHz mono WAV and posts it here. Audio is transcribed in memory and never stored.

Whisper (CTranslate2) and the embedding model (PyTorch) each ship their own OpenMP runtime and deadlock when
loaded into one process, so Whisper runs in a separate worker process started on first use.

WHISPER_MODEL env: tiny | base | small (default) | medium.
"""
from __future__ import annotations

import base64
import io
import multiprocessing as mp
import os
import threading
import time
import wave

import numpy as np

# Whisper language codes for the languages the app supports; None = detect.
LANGUAGES = {"auto": None, "en": "en", "es": "es", "ht": "ht", "zh": "zh", "vi": "vi", "pt": "pt"}
_lock = threading.Lock()
_worker: dict = {"proc": None, "conn": None}


def available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        return False


def _serve(conn, model_size: str) -> None:
    """Worker process: load Whisper once, then transcribe float32 audio sent over the pipe."""
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    conn.send({"ready": True})
    while True:
        msg = conn.recv()
        if msg is None:
            break
        try:
            segments, info = model.transcribe(msg["audio"], beam_size=1, vad_filter=True, language=msg["language"],
                                              condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segments).strip()
            conn.send({"text": text, "language": info.language, "language_probability": float(info.language_probability)})
        except Exception as e:  # keep the worker alive
            conn.send({"error": str(e)[:200]})


def _ensure_worker(timeout: float = 120):
    p = _worker["proc"]
    if p is not None and p.is_alive():
        return _worker["conn"]
    ctx = mp.get_context("spawn")  # fresh interpreter: no PyTorch / OpenMP state inherited
    parent, child = ctx.Pipe()
    proc = ctx.Process(target=_serve, args=(child, os.getenv("WHISPER_MODEL", "small")), daemon=True)
    proc.start()
    if not parent.poll(timeout):
        proc.kill()
        raise RuntimeError("speech worker did not start")
    parent.recv()
    _worker.update(proc=proc, conn=parent)
    return parent


def warm_up() -> None:
    """Start the worker in the background so the first recording isn't slow."""
    if available():
        def _go():
            with _lock:
                try:
                    _ensure_worker()
                except Exception:
                    pass
        threading.Thread(target=_go, daemon=True).start()


def _decode_wav(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2:
            raise ValueError("expected 16-bit PCM WAV")
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            frames = frames.reshape(-1, w.getnchannels()).mean(axis=1)
        rate = w.getframerate()
    if rate != 16000:  # simple linear resample; the browser normally sends 16 kHz already
        n = int(len(frames) * 16000 / rate)
        frames = np.interp(np.linspace(0, len(frames) - 1, n), np.arange(len(frames)), frames).astype(np.float32)
    return frames


def transcribe(audio_b64: str, language: str | None = "auto", timeout: float = 120) -> dict:
    t0 = time.time()
    audio = _decode_wav(base64.b64decode(audio_b64))
    if len(audio) < 16000 * 0.3:
        return {"text": "", "language": None, "latency_ms": 0, "error": "Recording was too short."}
    with _lock:  # one transcription at a time on CPU
        conn = _ensure_worker()
        conn.send({"audio": audio, "language": LANGUAGES.get(language or "auto")})
        if not conn.poll(timeout):
            _worker["proc"].kill()
            _worker.update(proc=None, conn=None)
            raise RuntimeError("transcription timed out")
        out = conn.recv()
    if out.get("error"):
        raise RuntimeError(out["error"])
    return {**out, "language_probability": round(out["language_probability"], 3),
            "duration_s": round(len(audio) / 16000, 1), "latency_ms": round((time.time() - t0) * 1000)}
