"""Thin wrapper around a local Ollama server. Every caller must handle `available() == False`.

Env overrides: OLLAMA_HOST, INTAKE_MODEL, AGENT_MODEL, VISION_MODEL, LLM_DISABLED=1.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def settings() -> dict:
    cfg = yaml.safe_load((ROOT / "params.yaml").read_text()).get("llm", {})
    return {
        "host": os.getenv("OLLAMA_HOST", cfg.get("host", "http://localhost:11434")),
        "intake_model": os.getenv("INTAKE_MODEL", cfg.get("intake_model", "qwen2.5:3b")),
        "agent_model": os.getenv("AGENT_MODEL", cfg.get("agent_model", "qwen2.5:3b")),
        "vision_model": os.getenv("VISION_MODEL", cfg.get("vision_model", "moondream")),
        "clarify_threshold": float(cfg.get("clarify_threshold", 0.6)),
    }


_status = {"checked": 0.0, "models": None}


def models() -> list[str]:
    """Installed model names, or [] if Ollama isn't reachable. Cached for 30 s."""
    if os.getenv("LLM_DISABLED") == "1":
        return []
    if time.time() - _status["checked"] < 30 and _status["models"] is not None:
        return _status["models"]
    try:
        r = httpx.get(f"{settings()['host']}/api/tags", timeout=1.5)
        names = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        names = []
    _status.update(checked=time.time(), models=names)
    return names


def available(model: str | None = None) -> bool:
    names = models()
    if not names:
        return False
    if model is None:
        return True
    return model in names or f"{model}:latest" in names


def chat(messages: list[dict], model: str, tools: list | None = None, format: dict | str | None = None,
         temperature: float = 0.0, timeout: float = 180.0) -> dict:
    """Returns {content, tool_calls: [{name, arguments}], tokens_in, tokens_out, latency_ms, model}."""
    import ollama

    client = ollama.Client(host=settings()["host"], timeout=timeout)
    t0 = time.time()
    kwargs = {"model": model, "messages": messages, "options": {"temperature": temperature, "num_ctx": 4096}}
    if tools:
        kwargs["tools"] = tools
    if format is not None:
        kwargs["format"] = format
    resp = client.chat(**kwargs)
    msg = resp["message"]
    calls = []
    for c in (msg.get("tool_calls") or []):
        fn = c["function"]
        calls.append({"name": fn["name"], "arguments": dict(fn.get("arguments") or {})})
    return {
        "content": msg.get("content") or "",
        "tool_calls": calls,
        "tokens_in": resp.get("prompt_eval_count") or 0,
        "tokens_out": resp.get("eval_count") or 0,
        "latency_ms": round((time.time() - t0) * 1000),
        "model": model,
    }


def describe_image(image_b64: str, prompt: str = "Describe the city problem shown in this photo in one short sentence.") -> dict | None:
    model = settings()["vision_model"]
    if not available(model):
        return None
    try:
        out = chat([{"role": "user", "content": prompt, "images": [image_b64]}], model=model, timeout=120)
        out["content"] = out["content"].strip().split("\n")[0][:300]
        return out
    except Exception:
        return None
