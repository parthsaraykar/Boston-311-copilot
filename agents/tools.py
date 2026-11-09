"""One tool registry for every agent, the API and the MCP server. Tools are plain functions returning JSON.

No tool commits a plan: propose_plan only writes a draft; a person approves it through POST /plan/approve.
"""
from __future__ import annotations

import json
import shutil
import time
from functools import lru_cache
from pathlib import Path

import pandas as pd

from core import db
from forecast.model import load_forecast
from intake import geo, retrieve
from intake.catalog import DEPT_NAMES, cards_by_type, resolve_route
from optimizer.model import MONTHS, load_params, simulate, solve, staffing_of, with_overrides

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
DEPTS = ["Public Works", "Transportation", "Parks", "Inspectional Services"]
CODE_TO_DEPT = {"PWDx": "Public Works", "BTDT": "Transportation", "PARK": "Parks", "ISD": "Inspectional Services"}
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------- helpers ----------

def _plan() -> dict:
    return json.loads((CONTRACTS / "plan.json").read_text())


def _norm_dept(dept: str | None) -> str | None:
    if not dept:
        return None
    d = dept.strip().lower()
    for name in DEPTS:
        if d in (name.lower(), name.lower().split()[0]) or name.lower().startswith(d):
            return name
    aliases = {"pw": "Public Works", "pwd": "Public Works", "btd": "Transportation", "transport": "Transportation",
               "isd": "Inspectional Services", "inspections": "Inspectional Services", "park": "Parks"}
    return aliases.get(d, CODE_TO_DEPT.get(dept))


def _norm_month(month) -> int | None:
    """1-12 from 4, '4', 'April', 'apr', '2025-04'."""
    if month is None or month == "":
        return None
    if isinstance(month, (int, float)):
        return int(month) if 1 <= int(month) <= 12 else None
    m = str(month).strip().lower()
    if "-" in m:
        m = m.split("-")[-1]
    if m.isdigit():
        return int(m) if 1 <= int(m) <= 12 else None
    for i, name in enumerate(MONTH_NAMES):
        if m.startswith(name.lower()):
            return i + 1
    return None


def _money(x: float) -> str:
    return f"${x:,.0f}"


# ---------- intake tools ----------

def search_categories(text: str, k: int = 5) -> dict:
    """Closest category cards for a message."""
    hits = retrieve.search(text, k=int(k))
    return {"categories": [{"id": h["card"]["id"], "type": h["card"]["type"], "name": h["card"]["name"],
                            "department": h["card"]["main_department"], "score": round(h["score"], 3)} for h in hits]}


def classify_request(text: str, clarification: str | None = None) -> dict:
    """Full intake pipeline (safety, privacy, retrieval, classifier, routing)."""
    from intake.classify import classify
    return classify(text, clarification=clarification)


def geocode_place(place: str) -> dict:
    point = geo.geocode(place)
    if not point:
        return {"found": False, "place": place}
    return {"found": True, **point, **geo.locate(point["lat"], point["lon"])}


def find_duplicates(type: str, lat: float, lon: float) -> dict:  # noqa: A002
    return {"similar_open": geo.find_duplicates(type, float(lat), float(lon))}


def get_expected_fix(type: str, neighborhood: str | None = None) -> dict:  # noqa: A002
    card = cards_by_type().get(type)
    if not card:
        return {"error": f"unknown type {type}"}
    route, share = resolve_route(card, neighborhood)
    return {"type": type, "department": route["department"], "queue": route["queue"],
            "median_days_to_close": route["median_days_to_close"], "on_time_rate": route["on_time_rate"]}


def file_request(classification: dict, as_of_month: int | None = None) -> dict:
    """File a routed request: logs the scrubbed text and adds 1 to live demand for that department."""
    if classification.get("status") not in ("routed", "clarify") or not classification.get("type"):
        return {"filed": False, "reason": "only routed requests can be filed"}
    rid = db.log_intake(classification, filed=True, plan_month=as_of_month or current_month())
    return {"filed": True, "request_id": rid, "queue": classification.get("queue"),
            "department": classification.get("department")}


# ---------- planning tools ----------

def get_plan(dept: str | None = None, month=None) -> dict:
    """The saved (approved) plan: totals, or one department / month."""
    p = _plan()
    d, m = _norm_dept(dept), _norm_month(month)
    out = {"on_time_target": p["on_time_target"], "plan_year": p["plan_year"]}
    if d is None and m is None:
        out["totals"] = p["totals"]
        out["by_dept"] = {k: {kk: v[kk] for kk in ("total_cost", "on_time_rate", "peak_crews")} for k, v in p["by_dept"].items()}
        out["crews"] = p["crews"]
        out["seasonal"] = p["seasonal"]
        return out
    rows = [r for r in p["rows"] if (d is None or r["dept"] == d) and (m is None or r["month"] == m)]
    out["rows"] = rows
    if d and m is None:
        out["dept_totals"] = p["by_dept"][d]
    return out


def get_forecast(dept: str | None = None, month=None) -> dict:
    f = load_forecast()
    d, m = _norm_dept(dept), _norm_month(month)
    if d:
        f = f[f["dept"] == d]
    if m:
        f = f[f["month"] == f"2025-{m:02d}"]
    cols = ["dept", "month", "mean", "p10", "p90", "model", "backtest_wape"]
    return {"forecast": f[cols].to_dict("records")}


def explain_month(dept: str, month) -> dict:
    """Why the plan does what it does in one department-month: demand vs capacity, hires, seasonals and the
    shadow value (late cost saved by one more crew that month, from the LP relaxation)."""
    d, m = _norm_dept(dept), _norm_month(month)
    if not d or not m:
        return {"error": "need a department and a month"}
    p = _plan()
    rows = {r["month"]: r for r in p["rows"] if r["dept"] == d}
    r = rows[m]
    k = p["params"]["departments"][d]["requests_per_crew_month"]
    crew_month = p["params"]["departments"][d]["crew_cost"] / 12
    prev = rows.get(m - 1)
    nxt = rows.get(m + 1)
    f = load_forecast()
    fr = f[(f["dept"] == d) & (f["month"] == f"2025-{m:02d}")].iloc[0]
    return {
        "dept": d, "month": m, "month_name": MONTH_NAMES[m - 1],
        "forecast_demand": r["demand"], "forecast_p10": float(fr["p10"]), "forecast_p90": float(fr["p90"]),
        "crews": r["crews"], "seasonal_crews": r["seasonal"], "hires_this_month": r["hires"],
        "releases_this_month": r["releases"], "capacity": r["capacity"], "served": r["served"],
        "backlog_end": r["backlog"], "on_time_rate": r["on_time_rate"],
        "requests_per_crew_month": k, "crew_cost_per_month": round(crew_month, 2),
        "shadow_value_one_more_crew": r.get("shadow_value"),
        "net_value_one_more_crew": r.get("net_value_extra_crew"),
        "hires_in_previous_month": prev["hires"] if prev else 0,
        "demand_next_month": nxt["demand"] if nxt else None,
        "training_months": p["params"]["training_months"],
        "note": "Hires train for one month before they are productive, so crews needed in month m are hired in m-1.",
    }


def compare_baselines() -> dict:
    b = json.loads((CONTRACTS / "baselines.json").read_text())
    return {k: {"total_cost": v["totals"]["total_cost"], "on_time_rate": v["totals"]["on_time_rate"]}
            for k, v in b.items() if isinstance(v, dict)} | {"saving_vs_flat": b["saving_vs_flat"],
                                                              "saving_vs_level": b["saving_vs_level"]}


def run_scenario(demand_mult: float = 1.0, storm: bool = False, late_cost: float | None = None,
                 severance_rate: float | None = None, seasonal_premium: float | None = None,
                 crew_output_mult: float | None = None, training_months: int | None = None,
                 target: float | None = None) -> dict:
    """What-if: the locked (saved) plan vs a re-planned one under changed demand or costs. Read-only."""
    from scenarios.scenario import scenario
    overrides = {k: v for k, v in {"late_cost": late_cost, "severance_rate": severance_rate,
                                   "seasonal_premium": seasonal_premium, "crew_output_mult": crew_output_mult,
                                   "training_months": training_months}.items() if v is not None}
    s = scenario(demand_mult=float(demand_mult), storm=bool(storm), overrides=overrides, target=target)
    return {
        "inputs": s["inputs"],
        "locked_total_cost": s["locked"]["totals"]["total_cost"], "locked_on_time": s["locked"]["totals"]["on_time_rate"],
        "replanned_total_cost": s["replanned"]["totals"]["total_cost"],
        "replanned_on_time": s["replanned"]["totals"]["on_time_rate"],
        "base_total_cost": s["base"]["totals"]["total_cost"],
        "cost_of_not_replanning": s["cost_of_not_replanning"],
        "locked_by_dept": {d: {"on_time_rate": v["on_time_rate"], "total_cost": v["total_cost"]} for d, v in s["locked"]["by_dept"].items()},
        "replanned_peak_crews": {d: max(c) for d, c in s["replanned"]["crews"].items()},
        "replanned_hires": {d: sum(h) for d, h in s["replanned"]["hires"].items()},
    }


def solve_plan(target: float | None = None, demand_mult: float = 1.0) -> dict:
    """Solve a fresh plan (what-if only; does not change the saved plan)."""
    from optimizer.run import forecast_demand
    D = {d: [v * float(demand_mult) for v in vals] for d, vals in forecast_demand().items()}
    p = solve(D, load_params(), target=target)
    if not p.get("rows"):
        return {"feasible": False}
    return {"feasible": True, "totals": p["totals"], "by_dept": {d: {"on_time_rate": v["on_time_rate"], "total_cost": v["total_cost"]}
                                                                 for d, v in p["by_dept"].items()},
            "crews": p["crews"], "seasonal": p["seasonal"]}


# ---------- live loop / monitor tools ----------

@lru_cache(maxsize=1)
def _actual_2025() -> pd.DataFrame:
    m = pd.read_parquet(ROOT / "data" / "processed" / "monthly.parquet")
    m["month"] = pd.to_datetime(m["month"])
    return m[m["month"].dt.year == 2025]


_demo_state = {"as_of_month": 6, "spike": {}}


def current_month() -> int:
    return _demo_state["as_of_month"]


def set_demo_state(as_of_month: int | None = None, spike: dict | None = None) -> dict:
    if as_of_month:
        _demo_state["as_of_month"] = int(as_of_month)
    if spike is not None:
        _demo_state["spike"] = spike
    return dict(_demo_state)


def get_live_demand(as_of_month: int | None = None) -> dict:
    """Actual 2025 demand so far (replayed from the real data up to as_of_month) plus requests filed in this app,
    against the forecast band."""
    M = int(as_of_month or current_month())
    act = _actual_2025()
    f = load_forecast()
    live = db.rows("select dept_code, plan_month, count(*) n from intake_log where filed=1 group by 1, 2")
    out = {}
    for d in DEPTS:
        rows = []
        for t in range(1, M + 1):
            a = act[(act["dept"] == d) & (act["month"].dt.month == t)]["requests"]
            actual = float(a.iloc[0]) if len(a) else 0.0
            app = sum(r["n"] for r in live if CODE_TO_DEPT.get(r["dept_code"]) == d and r["plan_month"] == t)
            spike = float(_demo_state["spike"].get(d, 0.0)) if t == M else 0.0
            total = actual * (1 + spike) + app
            fr = f[(f["dept"] == d) & (f["month"] == f"2025-{t:02d}")].iloc[0]
            rows.append({"month": t, "actual": round(total, 1), "from_city_data": actual, "filed_in_app": app,
                         "demo_spike_pct": spike, "forecast": float(fr["mean"]), "p10": float(fr["p10"]),
                         "p90": float(fr["p90"]),
                         "outside_band": "above" if total > fr["p90"] else ("below" if total < fr["p10"] else None)})
        ytd_a = sum(r["actual"] for r in rows)
        ytd_f = sum(r["forecast"] for r in rows)
        out[d] = {"months": rows, "ytd_actual": round(ytd_a, 1), "ytd_forecast": round(ytd_f, 1),
                  "ytd_ratio": round(ytd_a / ytd_f, 4) if ytd_f else None}
    return {"as_of_month": M, "departments": out}


def propose_plan(reason: str, as_of_month: int | None = None, created_by: str = "monitor") -> dict:
    """Draft a re-plan for the rest of the year from live demand. Months already past stay as they were.
    Writes a DRAFT only; a person must approve it."""
    from optimizer.run import forecast_demand
    M = int(as_of_month or current_month())
    live = get_live_demand(M)
    base = _plan()
    fc = forecast_demand()
    D = {}
    for d in DEPTS:
        months = live["departments"][d]["months"]
        ratio = live["departments"][d]["ytd_ratio"] or 1.0
        recent = months[-1]["actual"] / months[-1]["forecast"] if months[-1]["forecast"] else 1.0
        adj = 0.5 * ratio + 0.5 * recent  # blend year-to-date and the latest month
        D[d] = [months[t]["actual"] if t < M else fc[d][t] * adj for t in range(MONTHS)]
    params = load_params()
    staffing = staffing_of(base)
    new = solve(D, params, target=base["on_time_target"], locked=staffing, lock_until=M)
    if not new.get("rows"):
        new = solve(D, params, target=None, locked=staffing, lock_until=M)
    keep = simulate(staffing, D, params)
    pid = db.new_id("prop")
    changes = []
    for d in DEPTS:
        for t in range(M, MONTHS):
            a, b = staffing["crews"][d][t] + staffing["seasonal"][d][t], new["crews"][d][t] + new["seasonal"][d][t]
            if abs(a - b) >= 1:
                changes.append({"dept": d, "month": t + 1, "crews_before": a, "crews_after": b})
    summary = {
        "as_of_month": M, "reason": reason,
        "keep_plan_cost": keep["totals"]["total_cost"], "keep_plan_on_time": keep["totals"]["on_time_rate"],
        "new_plan_cost": new["totals"]["total_cost"], "new_plan_on_time": new["totals"]["on_time_rate"],
        "saving_vs_keeping": round(keep["totals"]["total_cost"] - new["totals"]["total_cost"], 2),
        "changes": changes[:24],
        "by_dept_keep": {d: keep["by_dept"][d]["on_time_rate"] for d in DEPTS},
        "by_dept_new": {d: new["by_dept"][d]["on_time_rate"] for d in DEPTS},
    }
    plan_doc = {**base, **{k: new[k] for k in ("rows", "by_dept", "totals", "crews", "hires", "releases", "seasonal")},
                "replanned_from_month": M, "demand_used": D}
    db.execute("insert into proposals values (?,?,?,?,?,?,?,?)",
               (pid, time.time(), created_by, reason, json.dumps(plan_doc), json.dumps(summary), "pending", None))
    return {"proposal_id": pid, "status": "pending approval", **summary}


def approve_proposal(proposal_id: str, approve: bool = True) -> dict:
    """Called only by the API when a person clicks Approve/Reject. Not exposed to agents."""
    r = db.rows("select * from proposals where id=?", (proposal_id,))
    if not r:
        return {"error": "not found"}
    if r[0]["status"] != "pending":
        return {"error": f"already {r[0]['status']}"}
    if approve:
        hist = CONTRACTS / "plan_history"
        hist.mkdir(exist_ok=True)
        shutil.copy(CONTRACTS / "plan.json", hist / f"plan_before_{proposal_id}.json")
        (CONTRACTS / "plan.json").write_text(r[0]["plan"])
        from scenarios.scenario import base_plan_cached
        base_plan_cached.cache_clear()
    db.execute("update proposals set status=?, decided_ts=? where id=?",
               ("approved" if approve else "rejected", time.time(), proposal_id))
    return {"proposal_id": proposal_id, "status": "approved" if approve else "rejected"}


def ask_stress_test(focus: str = "") -> dict:
    """Hand-off: run the Stress-test agent and return its ranked worst cases."""
    from agents.stress import run_stress_test
    return run_stress_test(focus)


# ---------- registry ----------

def _fn(name, desc, props, required=()):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(required)}}}


S = {"type": "string"}
N = {"type": "number"}
DEPT = {"type": "string", "enum": DEPTS}
MONTH = {"type": "integer", "description": "1-12 (2025)"}

REGISTRY = {
    "search_categories": (search_categories, _fn("search_categories", "Closest 311 categories for a message.", {"text": S, "k": {"type": "integer"}}, ["text"])),
    "classify": (classify_request, _fn("classify", "Classify and route a resident message.", {"text": S, "clarification": S}, ["text"])),
    "geocode": (geocode_place, _fn("geocode", "Find a Boston place: lat/lon and neighborhood.", {"place": S}, ["place"])),
    "find_duplicates": (find_duplicates, _fn("find_duplicates", "Open reports of the same type within 200 m.", {"type": S, "lat": N, "lon": N}, ["type", "lat", "lon"])),
    "get_expected_fix": (get_expected_fix, _fn("get_expected_fix", "Typical days to close and on-time rate.", {"type": S, "neighborhood": S}, ["type"])),
    "file_request": (file_request, _fn("file_request", "File a classified request.", {"classification": {"type": "object"}}, ["classification"])),
    "get_plan": (get_plan, _fn("get_plan", "The saved 2025 crew plan. Optional department and month.", {"dept": DEPT, "month": MONTH})),
    "get_forecast": (get_forecast, _fn("get_forecast", "2025 demand forecast (mean, p10, p90).", {"dept": DEPT, "month": MONTH})),
    "explain_month": (explain_month, _fn("explain_month", "Why the plan staffs a department-month the way it does, with the value of one more crew.", {"dept": DEPT, "month": MONTH}, ["dept", "month"])),
    "compare_baselines": (compare_baselines, _fn("compare_baselines", "Cost and on-time of flat, level and optimised plans.", {})),
    "run_scenario": (run_scenario, _fn("run_scenario", "What-if: locked plan vs re-planned under changed demand or costs.", {
        "demand_mult": {"type": "number", "description": "1.1 = demand 10% higher"}, "storm": {"type": "boolean"},
        "late_cost": N, "severance_rate": N, "seasonal_premium": N, "crew_output_mult": N, "training_months": {"type": "integer"}})),
    "solve_plan": (solve_plan, _fn("solve_plan", "Solve a what-if plan for an on-time target (0-1). Does not save.", {"target": N, "demand_mult": N})),
    "get_live_demand": (get_live_demand, _fn("get_live_demand", "Demand so far in 2025 vs the forecast band.", {"as_of_month": MONTH})),
    "propose_plan": (propose_plan, _fn("propose_plan", "Draft a re-plan for the rest of the year. Needs human approval.", {"reason": S, "as_of_month": MONTH}, ["reason"])),
    "ask_stress_test": (ask_stress_test, _fn("ask_stress_test", "Run the Stress-test agent: worst demand cases and cheapest fixes.", {"focus": S})),
}


def call(name: str, args: dict, allowlist: list[str] | None = None):
    if allowlist is not None and name not in allowlist:
        return {"error": f"tool {name} is not allowed for this agent"}
    if name not in REGISTRY:
        return {"error": f"unknown tool {name}"}
    fn = REGISTRY[name][0]
    import inspect
    params = inspect.signature(fn).parameters
    # small models sometimes pass arguments that belong to another tool: drop them rather than fail
    args = {k: v for k, v in (args or {}).items() if k in params and v is not None}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}
    except Exception as e:  # tools never crash an agent loop
        return {"error": str(e)[:300]}


def schemas(names: list[str]) -> list[dict]:
    return [REGISTRY[n][1] for n in names]
