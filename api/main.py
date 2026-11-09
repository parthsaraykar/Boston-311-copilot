"""FastAPI: the single join point between the modules and the UI.

Run: uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents import tools
from core import db, llm

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "contracts"
CACHE = ROOT / "data" / "demo_cache.json"

app = FastAPI(title="Boston 311 Copilot", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------- public mode: requests arriving through the share tunnel ----------
# Anyone on the internet can file a request and look around; only the laptop running the app can approve plans,
# decide reviews, run agents or use the slow local LLM.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]"}
PUBLIC_POST_ALLOWED = {"/intake/classify", "/intake/transcribe", "/scenario", "/agent/ask"}
PUBLIC_RATE = {"per_minute": 20}
_hits: dict[str, list[float]] = {}


def is_public(request) -> bool:
    host = (request.headers.get("host") or "").split(":")[0].lower()
    return "cf-connecting-ip" in request.headers or host not in LOCAL_HOSTS


@app.middleware("http")
async def public_guard(request, call_next):
    from fastapi.responses import JSONResponse
    if is_public(request) and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.url.path not in PUBLIC_POST_ALLOWED:
            return JSONResponse({"detail": "This action is only available on the planner's own machine."}, status_code=403)
        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
        now = time.time()
        recent = [t for t in _hits.get(ip, []) if now - t < 60]
        if len(recent) >= PUBLIC_RATE["per_minute"]:
            return JSONResponse({"detail": "Too many requests, please wait a minute."}, status_code=429)
        _hits[ip] = recent + [now]
        if int(request.headers.get("content-length") or 0) > 8_000_000:
            return JSONResponse({"detail": "Upload too large."}, status_code=413)
    return await call_next(request)


def public_url() -> str | None:
    p = ROOT / "data" / "public_url.txt"
    return p.read_text().strip() if p.exists() else None


def _clean(o):
    """NaN/inf are not valid JSON; send them as null."""
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def _json(name: str):
    p = C / name
    if not p.exists():
        raise HTTPException(404, f"{name} not built yet")
    return _clean(json.loads(p.read_text()))


# ---------- demo cache: every scripted demo input has a stored answer, so the demo never waits on the model ----------

def _cache_key(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _cache_get(key: str):
    try:
        return json.loads(CACHE.read_text()).get(key)
    except Exception:
        return None


def _cache_put(key: str, value):
    try:
        data = json.loads(CACHE.read_text())
    except Exception:
        data = {}
    data[key] = value
    CACHE.write_text(json.dumps(data, default=str))


# ---------- health ----------

@app.get("/health")
def health(request: Request):
    s = llm.settings()
    return {"ok": True, "public_url": public_url(), "public_request": is_public(request), "ollama": llm.available(), "models": llm.models(), "intake_model": s["intake_model"],
            "agent_model": s["agent_model"], "intake_model_ready": llm.available(s["intake_model"]),
            "speech": __import__("intake.speech", fromlist=["available"]).available(),
            "as_of_month": tools.current_month()}


# ---------- intake ----------

class ClassifyIn(BaseModel):
    text: str
    location_text: str | None = None   # optional "where is it?" field from the form
    image_b64: str | None = None
    clarification: str | None = None
    mode: str = "fast"          # fast = retrieval only, llm = local model, cached = use demo cache if present
    file: bool = True
    source: str = "web"


@app.post("/intake/classify")
def intake_classify(body: ClassifyIn, request: Request):
    from intake.classify import classify
    if len(body.text) > 2000 or (body.location_text and len(body.location_text) > 300):
        raise HTTPException(413, "Message too long.")
    if is_public(request):
        body.mode = "fast"  # the local LLM is too slow to share with the internet
        body.source = "public"
    use_llm = body.mode in ("llm", "cached")
    key = _cache_key("classify", body.text, body.clarification, use_llm, bool(body.image_b64), body.location_text)
    res = _cache_get(key) if body.mode == "cached" and not body.image_b64 else None
    if res is not None:
        res = {**res, "cached": True}
    else:
        location = None
        if body.location_text and body.location_text.strip():
            from intake import geo
            location = geo.geocode(body.location_text.strip())
        res = classify(body.text, image_b64=body.image_b64, clarification=body.clarification, use_llm=use_llm,
                       location=location)
        if location:
            res["location_text"] = body.location_text.strip()
            if res.get("location"):
                res["location"]["display"] = location.get("display")
        if use_llm and res.get("mode") == "llm" and not body.image_b64:
            _cache_put(key, res)
    if body.file and res["status"] in ("routed", "clarify") and res.get("type"):
        review = res["status"] == "clarify" or (res.get("confidence") or 0) < llm.settings()["clarify_threshold"]
        rid = db.log_intake(res, filed=res["status"] == "routed", plan_month=tools.current_month(), source=body.source)
        if review:
            db.execute("update intake_log set review='pending' where id=?", (rid,))
        res["request_id"] = rid
    elif body.file:
        db.log_intake(res, filed=False, source=body.source)
    return res


class TranscribeIn(BaseModel):
    audio_b64: str              # 16-bit PCM WAV, ideally 16 kHz mono
    language: str | None = "auto"


@app.post("/intake/transcribe")
def intake_transcribe(body: TranscribeIn):
    """Local Whisper speech-to-text; audio is processed in memory and not stored."""
    from intake import speech
    if len(body.audio_b64) > 2_600_000:  # ~40 s of 16 kHz mono WAV
        raise HTTPException(413, "Recording too long.")
    if not speech.available():
        raise HTTPException(503, "Speech-to-text is not installed (pip install faster-whisper).")
    try:
        return speech.transcribe(body.audio_b64, body.language)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")


@app.on_event("startup")
def _warm():
    from intake import speech
    speech.warm_up()


@app.get("/intake/live")
def intake_live():
    by_dept = db.rows("select coalesce(department, dept_code) department, count(*) n from intake_log "
                      "where filed=1 group by 1 order by n desc")
    recent = db.rows("select id, ts, text_scrubbed, status, type, department, queue, confidence, language, mode, "
                     "neighborhood, lat, lon, source from intake_log order by ts desc limit 25")
    return {"by_department": by_dept, "recent": recent,
            "total_filed": sum(r["n"] for r in by_dept), "as_of_month": tools.current_month()}


@app.get("/intake/categories")
def intake_categories():
    from intake.catalog import cards
    return [{k: c[k] for k in ("id", "type", "name", "description", "examples", "monthly_volume", "main_department")}
            | {"routes": len(c["routes"])} for c in cards()]


# ---------- forecast / plan / scenarios ----------

@app.get("/forecast")
def forecast(dept: str | None = None):
    f = _json("forecast.json")
    if dept:
        f["forecast"] = [r for r in f["forecast"] if r["dept"] == dept]
        f["history"] = [r for r in f["history"] if r["dept"] == dept]
    return f


@app.get("/plan")
def plan():
    p = _json("plan.json")
    p.pop("demand_used", None)
    return p


class SolveIn(BaseModel):
    target: float | None = None
    demand_mult: float = 1.0
    storm: bool = False
    overrides: dict | None = None
    use_live: bool = False


@app.post("/plan/solve")
def plan_solve(body: SolveIn):
    """What-if solve (not saved). With use_live, re-plan the rest of the year from live demand as a proposal."""
    if body.use_live:
        return tools.propose_plan(reason="Planner pressed Re-plan with live demand", created_by="planner")
    from scenarios.scenario import scenario
    s = scenario(demand_mult=body.demand_mult, storm=body.storm, overrides=body.overrides, target=body.target)
    return s


@app.get("/plan/baselines")
def plan_baselines():
    return _json("baselines.json")


@app.get("/plan/frontier")
def plan_frontier():
    return _json("frontier.json")


class ScenarioIn(BaseModel):
    demand_mult: float = 1.0
    storm: bool = False
    heatwave: bool = False
    late_cost: float | None = None
    severance_rate: float | None = None
    seasonal_premium: float | None = None
    crew_output_mult: float | None = None
    training_months: int | None = None
    target: float | None = None


@app.post("/scenario")
def scenario_ep(body: ScenarioIn):
    from scenarios.scenario import scenario
    overrides = {k: v for k, v in body.model_dump().items()
                 if k not in ("demand_mult", "storm", "heatwave", "target") and v is not None}
    key = _cache_key("scenario", body.model_dump(), (C / "plan.json").stat().st_mtime)
    hit = _cache_get(key)
    if hit:
        return hit
    s = scenario(demand_mult=body.demand_mult, storm=body.storm, heatwave=body.heatwave, overrides=overrides, target=body.target)
    _cache_put(key, s)
    return s


@app.get("/replay")
def replay():
    """Real 2025 demand replayed month by month: flat vs locked plan vs plan + monitor vs hindsight."""
    return _json("replay.json")


@app.get("/pulse")
def pulse():
    """City Pulse: neighborhood on-time layer, grid of open requests, and requests filed in this app."""
    proc = ROOT / "data" / "processed"
    if not (proc / "pulse_neighborhoods.geojson").exists():
        raise HTTPException(404, "Run `python -m data.pulse` first")
    return {"neighborhoods": json.loads((proc / "pulse_neighborhoods.geojson").read_text()),
            "grid": json.loads((proc / "pulse_grid.json").read_text()), **pulse_live()}


@app.get("/pulse/live")
def pulse_live():
    rows = db.rows("select id, ts, type, department, dept_code, queue, neighborhood, lat, lon, status, confidence "
                   "from intake_log where lat is not null and status in ('routed','clarify') order by ts desc limit 200")
    return {"filed": rows, "filed_count": len(rows)}


@app.get("/scenarios")
def scenarios_pre():
    return _json("scenarios.json")


# ---------- agents ----------

class AskIn(BaseModel):
    question: str
    use_llm: bool = False


@app.post("/agent/ask")
@app.post("/agent/planner")
def agent_planner(body: AskIn, request: Request):
    from agents.planner import ask
    if len(body.question) > 500:
        raise HTTPException(413, "Question too long.")
    res = ask(body.question, use_llm=body.use_llm and not is_public(request))
    res.pop("tool_outputs", None)
    return res


class IntakeTurn(BaseModel):
    session_id: str | None = None
    message: str


@app.post("/agent/intake")
def agent_intake(body: IntakeTurn):
    from agents.intake_agent import step
    return step(body.session_id, body.message)


class StressIn(BaseModel):
    focus: str = ""


@app.post("/agent/stress-test")
def agent_stress(body: StressIn):
    """The search takes ~20 s on CPU, so the result is cached per saved-plan version (the trace stays viewable)."""
    from agents.stress import run_stress_test
    key = _cache_key("stress", body.focus, (C / "plan.json").stat().st_mtime)
    hit = _cache_get(key)
    if hit:
        return {**hit, "cached": True}
    res = run_stress_test(body.focus)
    _cache_put(key, res)
    return res


class MonitorIn(BaseModel):
    as_of_month: int | None = None
    spike: dict[str, float] | None = None


@app.post("/agent/monitor/run")
def agent_monitor(body: MonitorIn):
    from agents.monitor import run_monitor
    tools.set_demo_state(body.as_of_month, body.spike)
    return run_monitor()


@app.get("/agent/trace/{run_id}")
def agent_trace(run_id: str):
    return db.trace(run_id)


@app.get("/agent/runs")
def agent_runs(limit: int = 20):
    return db.rows("select run_id, agent, ts, input, answer, status, mode, steps, latency_ms, sources, grounded "
                   "from agent_runs order by ts desc limit ?", (limit,))


@app.get("/live-demand")
def live_demand(as_of_month: int | None = None):
    return tools.get_live_demand(as_of_month)


class DemoState(BaseModel):
    as_of_month: int | None = None
    spike: dict[str, float] | None = None


@app.post("/demo/state")
def demo_state(body: DemoState):
    return tools.set_demo_state(body.as_of_month, body.spike)


@app.get("/proposals")
def proposals():
    rows = db.rows("select id, ts, created_by, reason, summary, status, decided_ts from proposals order by ts desc limit 20")
    for r in rows:
        r["summary"] = json.loads(r["summary"])
    return rows


@app.post("/plan/approve/{proposal_id}")
def plan_approve(proposal_id: str):
    """A person clicked Approve. This is the only path that changes the saved plan."""
    out = tools.approve_proposal(proposal_id, True)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@app.post("/plan/reject/{proposal_id}")
def plan_reject(proposal_id: str):
    out = tools.approve_proposal(proposal_id, False)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


# ---------- evaluation, review queue, equity, monitor quality, memo ----------

@app.get("/eval")
def eval_ep():
    return _json("eval.json")


@app.get("/eval/cases")
def eval_cases(mode: str = "retrieval", slice: str | None = None, language: str | None = None):  # noqa: A002
    labels = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "eval" / "testset.jsonl").read_text().splitlines() if l}
    p = ROOT / "eval" / f"results_{mode}.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line:
            continue
        r = json.loads(line)
        lab = labels.get(r["id"], {})
        if slice and r["slice"] != slice or language and r["language"] != language:
            continue
        ok = r["status"] == r["expect"] if r["expect"] != "routed" else (
            r["pred_type"] == lab.get("type") or r["pred_type"] in lab.get("also_ok", []))
        out.append({"id": r["id"], "text": lab.get("text"), "slice": r["slice"], "language": r["language"],
                    "label": lab.get("type") or r["expect"], "pred": r["pred_type"] or r["status"], "ok": ok,
                    "confidence": r.get("confidence"), "latency_ms": r.get("latency_ms")})
    return out


@app.get("/review-queue")
def review_queue():
    return db.rows("select id, ts, text_scrubbed, type, department, queue, confidence, language, review "
                   "from intake_log where review='pending' order by ts desc limit 50")


class ReviewIn(BaseModel):
    decision: str  # accept | reroute
    type: str | None = None


@app.post("/review-queue/{rid}")
def review_decide(rid: str, body: ReviewIn):
    if body.decision == "reroute" and body.type:
        from intake.catalog import cards_by_type, resolve_route
        card = cards_by_type().get(body.type)
        if not card:
            raise HTTPException(400, "unknown type")
        nb = db.rows("select neighborhood from intake_log where id=?", (rid,))
        route, _ = resolve_route(card, nb[0]["neighborhood"] if nb else None)
        db.execute("update intake_log set type=?, department=?, dept_code=?, queue=?, review='rerouted', filed=1 where id=?",
                   (card["type"], route["department"], route["dept_code"], route["queue"], rid))
    else:
        db.execute("update intake_log set review='accepted', filed=1 where id=?", (rid,))
    return {"ok": True}


@app.get("/equity")
def equity():
    """On-time by neighborhood in 2023-24, and whether the plan's gains reach the worst-served areas."""
    nb = pd.read_parquet(ROOT / "data" / "processed" / "neighborhood_ontime.parquet")
    nb = nb[nb["year"].isin([2023, 2024])]
    base = _json("baselines.json")
    gain = {d: base["optimised"]["by_dept"][d]["on_time_rate"] - base["flat"]["by_dept"][d]["on_time_rate"]
            for d in base["optimised"]["by_dept"]}
    rows = []
    for n, g in nb.groupby("neighborhood"):
        req = g.groupby("dept")["requests"].sum()
        if req.sum() < 2000:
            continue
        ot = (g["on_time_rate"] * g["requests"]).sum() / g["requests"].sum()
        mix = req / req.sum()
        exp_gain = float(sum(mix.get(d, 0) * gain.get(d, 0) for d in mix.index))
        rows.append({"neighborhood": n, "requests": int(req.sum()), "on_time_2023_24": round(float(ot), 4),
                     "expected_gain_pts": round(exp_gain * 100, 2),
                     "mix": {d: round(float(v), 3) for d, v in mix.items()}})
    df = pd.DataFrame(rows).sort_values("on_time_2023_24")
    corr = float(df["on_time_2023_24"].corr(df["expected_gain_pts"]))
    worst = df.head(5)["expected_gain_pts"].mean()
    best = df.tail(5)["expected_gain_pts"].mean()
    return {"neighborhoods": df.to_dict("records"), "dept_gain_pts": {d: round(v * 100, 2) for d, v in gain.items()},
            "corr_ontime_vs_gain": round(corr, 3), "worst5_avg_gain_pts": round(float(worst), 2),
            "best5_avg_gain_pts": round(float(best), 2),
            "finding": ("The plan's gains go mostly to the worst-served neighborhoods." if worst > best else
                        "The plan's gains do not favour the worst-served neighborhoods; a per-neighborhood target would be needed.")}


@app.get("/monitor/quality")
def monitor_quality():
    """Production check: share of low-confidence requests and category mix in the app vs city history."""
    from intake.catalog import cards_by_type
    rows = db.rows("select type, confidence, ts from intake_log where type is not null")
    if not rows:
        return {"requests": 0}
    df = pd.DataFrame(rows)
    low = float((df["confidence"].fillna(0) < llm.settings()["clarify_threshold"]).mean())
    mix = df["type"].value_counts(normalize=True).head(8)
    hist_total = sum(c["monthly_volume"] for c in cards_by_type().values())
    compare = [{"type": t, "app_share": round(float(s), 3),
                "history_share": round(cards_by_type()[t]["monthly_volume"] / hist_total, 3) if t in cards_by_type() else None}
               for t, s in mix.items()]
    return {"requests": len(df), "low_confidence_share": round(low, 3), "alert": low > 0.3, "mix_vs_history": compare}


@app.get("/memo.pdf")
def memo():
    from agents.memo import memo_pdf
    return Response(memo_pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=boston-311-crew-plan-memo.pdf"})


# ---------- the built React app, served from the same port ----------

DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
