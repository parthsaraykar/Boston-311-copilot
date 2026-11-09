"""run_agent: one tool-use loop shared by every agent. An agent = system prompt + tool allowlist + step limit.

With Ollama available it runs the model's tool calls; otherwise (or if the model fails grounding) it runs the
agent's scripted policy, which calls the same tools. Every step is traced to SQLite.
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable

from agents import tools
from core import db, llm


class Tracer:
    """Passed to scripted policies so their tool calls are traced exactly like the model's."""

    def __init__(self, run_id: str, allowlist: list[str]):
        self.run_id, self.allowlist, self.step, self.sources, self.outputs = run_id, allowlist, 0, [], []

    def call(self, name: str, **args):
        self.step += 1
        t0 = time.time()
        out = tools.call(name, args, self.allowlist)
        db.log_step(self.run_id, self.step, "tool", name, args, out, 0, round((time.time() - t0) * 1000))
        self.sources.append(name)
        self.outputs.append(out)
        return out

    def note(self, text: str):
        self.step += 1
        db.log_step(self.run_id, self.step, "thought", None, None, text)


# ---------- grounding ----------

NUM = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")


def _numbers_in(obj) -> set[float]:
    out = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= _numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _numbers_in(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in NUM.findall(obj):
            try:
                out.add(float(m.replace("$", "").replace(",", "").replace("%", "")))
            except ValueError:
                pass
    return out


def ungrounded_numbers(answer: str, outputs: list) -> list[str]:
    """Numbers in the answer that don't match any tool output (allowing rounding, %, $k / $M, months 1-12)."""
    known = _numbers_in(outputs)
    variants = set()
    for k in known:
        for v in (k, k * 100, k / 1000, k / 1e6, abs(k), abs(k) * 100, abs(k) / 1000, abs(k) / 1e6):
            variants.add(round(v, 0))
            variants.add(round(v, 1))
            variants.add(round(v, 2))
    bad = []
    for m in NUM.findall(answer):
        raw = m.replace("$", "").replace(",", "").replace("%", "").rstrip(".")
        if not raw or raw == "-":
            continue
        try:
            v = float(raw)
        except ValueError:
            continue
        if v in (0, 1, 2, 3, 2025, 2024, 2023) or (v.is_integer() and 1 <= v <= 12):
            continue
        if not any(abs(v - x) <= max(0.051, 0.006 * abs(v)) for x in variants):
            bad.append(m)
    return bad


# ---------- the loop ----------

RULES = """
Rules you must follow:
- Every number in your answer must come from a tool result in this conversation. Never estimate or invent numbers.
- If the tools don't give you the answer, say "I don't have that."
- You cannot change the saved plan. You can only run what-ifs or draft a proposal for a person to approve.
- Answer in 2-4 short sentences, plain words."""


def run_agent(agent: str, system_prompt: str, allowlist: list[str], user_input: str,
              scripted: Callable[[Tracer, str], str] | None = None, max_steps: int = 8,
              use_llm: bool | None = None, model: str | None = None) -> dict:
    model = model or llm.settings()["agent_model"]
    want_llm = llm.available(model) if use_llm is None else (use_llm and llm.available(model))
    mode = "llm" if want_llm else "scripted"
    run_id = db.start_run(agent, user_input, mode)
    t0 = time.time()
    tracer = Tracer(run_id, allowlist)
    tokens = 0
    answer, grounded, status = None, None, "done"

    if want_llm:
        messages = [{"role": "system", "content": system_prompt + RULES}, {"role": "user", "content": user_input}]
        retried = False
        for _ in range(max_steps):
            try:
                out = llm.chat(messages, model=model, tools=tools.schemas(allowlist), timeout=240)
            except Exception as e:
                tracer.note(f"model error: {e}")
                break
            tokens += out["tokens_in"] + out["tokens_out"]
            tracer.step += 1
            db.log_step(run_id, tracer.step, "model", None, None,
                        {"text": out["content"], "tool_calls": out["tool_calls"]}, out["tokens_in"] + out["tokens_out"], out["latency_ms"])
            if out["tool_calls"]:
                messages.append({"role": "assistant", "content": out["content"], "tool_calls": [
                    {"function": {"name": c["name"], "arguments": c["arguments"]}} for c in out["tool_calls"]]})
                for c in out["tool_calls"][:3]:
                    res = tracer.call(c["name"], **c["arguments"])
                    messages.append({"role": "tool", "content": json.dumps(res, default=str)[:6000], "tool_name": c["name"]})
                continue
            text = out["content"].strip()
            if not text:
                break
            bad = ungrounded_numbers(text, tracer.outputs)
            if not tracer.outputs and NUM.search(text) and not retried:
                bad = bad or ["(no tool used)"]
            if bad and not retried:
                retried = True
                messages += [{"role": "assistant", "content": text},
                             {"role": "user", "content": f"These numbers are not in any tool result: {bad}. "
                                                         "Call a tool to get them, or answer without them."}]
                continue
            gave_up = text.lower().startswith("i don't have") or "error" in json.dumps(tracer.outputs[-1:])
            if gave_up and scripted is not None:
                tracer.note("LLM could not answer from its tools; trying the scripted policy.")
                break
            answer, grounded = text, not bad
            break
        if answer is None or grounded is False:
            tracer.note("LLM answer missing or not grounded; using the scripted policy instead.")
            mode = "llm+scripted"

    if answer is None or grounded is False:
        if scripted is None:
            answer, grounded, status = "I don't have that.", True, "no_answer"
        else:
            answer = scripted(tracer, user_input)
            grounded = not ungrounded_numbers(answer, tracer.outputs)

    sources = list(dict.fromkeys(tracer.sources))
    latency = round((time.time() - t0) * 1000)
    db.log_step(run_id, tracer.step + 1, "answer", None, None, answer)
    db.finish_run(run_id, answer, status, tracer.step, tokens, latency, sources, grounded, mode)
    return {"run_id": run_id, "agent": agent, "answer": answer, "sources": sources, "grounded": grounded,
            "mode": mode, "steps": tracer.step, "tokens": tokens, "latency_ms": latency,
            "tool_outputs": tracer.outputs}
