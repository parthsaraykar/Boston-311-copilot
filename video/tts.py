"""Natural narration with Kokoro (open-source neural TTS, runs locally on CPU).

python tts.py --voice af_heart --speed 1.0 --out line.wav "Text to say"
Voices: af_heart, af_bella, am_michael, am_adam, bf_emma, bm_george, ... (see kokoro-onnx docs)
"""
import argparse
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
_k = None


def model() -> Kokoro:
    global _k
    if _k is None:
        _k = Kokoro(str(HERE / "models" / "kokoro-v1.0.onnx"), str(HERE / "models" / "voices-v1.0.bin"))
    return _k


def speak(text: str, out: str, voice: str = "af_heart", speed: float = 1.0) -> float:
    samples, rate = model().create(text, voice=voice, speed=speed, lang="en-us")
    sf.write(out, samples, rate)
    return len(samples) / rate


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?")
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", required=False)
    ap.add_argument("--batch", help="JSON file: [{text, out}] to render in one process")
    a = ap.parse_args()
    if a.batch:
        import json
        for item in json.loads(Path(a.batch).read_text()):
            d = speak(item["text"], item["out"], a.voice, a.speed)
            print(f"{d:.2f}\t{item['out']}", flush=True)
    else:
        print(f"{speak(a.text, a.out, a.voice, a.speed):.2f}")
