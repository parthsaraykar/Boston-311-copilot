"""What if Boston had used this in 2025? Replay the real 2025 demand month by month.

Strategies, all scored on the same actual 2025 demand:
  flat      today's crews all year (what happens without a plan)
  locked    the forecast-based optimised plan, never changed
  monitored the optimised plan, plus the Monitor's rule each month: when demand drifts outside the forecast band,
            re-plan the rest of the year (past months stay as they were; hires still need a month of training)
  hindsight the best plan had 2025 demand been known in January (a lower bound no real plan can beat)

Run: python -m scenarios.replay -> contracts/replay.json
"""
from __future__ import annotations

import json

from forecast.model import load_forecast
from optimizer.model import MONTHS, ROOT, fixed_plan, flat_staffing, load_params, simulate, solve, staffing_of

CONTRACTS = ROOT / "contracts"
YTD_TOLERANCE = 0.08


# ---------- the Monitor's rules, shared with agents/monitor.py and agents/tools.propose_plan ----------

def drift(actual: list[float], forecast: list[float], p10: list[float], p90: list[float], M: int) -> str | None:
    """Drift through month M (1-12): the latest month outside the p10-p90 band, or year to date off by >8%."""
    last = actual[M - 1]
    if last > p90[M - 1]:
        return "above the band"
    if last < p10[M - 1]:
        return "below the band"
    ytd = sum(actual[:M]) / sum(forecast[:M])
    if abs(ytd - 1) > YTD_TOLERANCE:
        return f"year to date {ytd - 1:+.0%}"
    return None


def adjusted_demand(actual: list[float], forecast: list[float], M: int, recent_weight: float = 0.0) -> list[float]:
    """Known actuals for months < M; the rest of the forecast scaled by the year-to-date actual/forecast ratio
    (optionally blended with the latest month's ratio, which is noisier)."""
    ratio = sum(actual[:M]) / sum(forecast[:M]) if sum(forecast[:M]) else 1.0
    recent = actual[M - 1] / forecast[M - 1] if forecast[M - 1] else 1.0
    adj = (1 - recent_weight) * ratio + recent_weight * recent
    return [actual[t] if t < M else forecast[t] * adj for t in range(MONTHS)]


# The Monitor rule as it shipped in the app, fixed before any replay was run. The replay reports this one.
SHIPPED_POLICY = "every_drift_blend"
# Variants, shown for transparency on both years (none of them changes the headline).
POLICIES = {
    "every_drift_blend": {"recent_weight": 0.5, "persist": 1, "margin": 0.0},
    "every_drift_ytd": {"recent_weight": 0.0, "persist": 1, "margin": 0.0},
    "persistent_ytd": {"recent_weight": 0.0, "persist": 2, "margin": 0.0},
    "every_drift_ytd_margin": {"recent_weight": 0.0, "persist": 1, "margin": 0.03},
    "persistent_ytd_margin": {"recent_weight": 0.0, "persist": 2, "margin": 0.03},
    # HR capacity: at most 10% / 20% of a department's crews hired or released in any one month
    "every_drift_blend_cap10": {"recent_weight": 0.5, "persist": 1, "margin": 0.0, "cap": 0.10},
    "every_drift_blend_cap20": {"recent_weight": 0.5, "persist": 1, "margin": 0.0, "cap": 0.20},
    "every_drift_ytd_cap10": {"recent_weight": 0.0, "persist": 1, "margin": 0.0, "cap": 0.10},
    "every_drift_ytd_cap20": {"recent_weight": 0.0, "persist": 1, "margin": 0.0, "cap": 0.20},
}


# ---------- replay ----------

def _summ(sim: dict) -> dict:
    return {"totals": sim["totals"], "by_dept": sim["by_dept"],
            "monthly": [{"dept": r["dept"], "month": r["month"], "demand": r["demand"], "crews": r["crews"] + r["seasonal"],
                         "cost": round(r["cost_crew"] + r["cost_seasonal"] + r["cost_severance"] + r["cost_late"] + r["cost_late30"], 2),
                         "on_time_rate": r["on_time_rate"]} for r in sim["rows"]]}


def _inputs(year: int):
    """Forecast, band, actuals, starting crews and the base plan as they would have been known in January."""
    import numpy as np
    from optimizer.run import actual_demand, calibrate

    params = load_params()
    f = load_forecast().sort_values(["dept", "month"])
    depts = sorted(f["dept"].unique())
    lo = {d: (g["p10"] / g["mean"]).tolist() for d, g in f.groupby("dept")}
    hi = {d: (g["p90"] / g["mean"]).tolist() for d, g in f.groupby("dept")}
    if year == 2025:
        F = {d: g["mean"].tolist() for d, g in f.groupby("dept")}
        plan_path = CONTRACTS / "plan_history" / "plan_original.json"
        plan = json.loads((plan_path if plan_path.exists() else CONTRACTS / "plan.json").read_text())
    elif year == 2024:
        # the 2024 forecast from the backtest (trained on data through 2023), and crews calibrated on 2023
        bt = json.loads((CONTRACTS / "forecast.json").read_text())["backtests"]
        F = {d: list(np.maximum(bt[d]["series_2024"]["pred"], 0)) for d in depts}
        if not params.get("starting_crews_fixed"):
            params = {**params, "starting_crews": calibrate(params, year=2023)}
        plan = None
    else:
        raise ValueError(year)
    A = actual_demand(year)
    A = {d: A[d] for d in depts}
    P10 = {d: [F[d][t] * lo[d][t] for t in range(MONTHS)] for d in depts}
    P90 = {d: [F[d][t] * hi[d][t] for t in range(MONTHS)] for d in depts}
    target = params["default_on_time_target"]
    if plan is None:
        plan = solve(F, params, target=target)
        plan["on_time_target"] = target
    return params, plan, F, P10, P90, A, depts


def replay(year: int, policy: str) -> dict:
    params, plan, F, P10, P90, A, depts = _inputs(year)
    pol = POLICIES[policy]
    target = plan["on_time_target"]
    staffing = staffing_of(plan)
    events, streak = [], {d: 0 for d in depts}
    for M in range(1, MONTHS):  # after month 12 there's nothing left to re-plan
        flagged = {d: drift(A[d], F[d], P10[d], P90[d], M) for d in depts}
        for d in depts:
            streak[d] = streak[d] + 1 if flagged[d] else 0
        trigger = {d: why for d, why in flagged.items() if why and streak[d] >= pol["persist"]}
        if not trigger:
            continue
        D = {d: adjusted_demand(A[d], F[d], M, pol["recent_weight"]) for d in depts}
        cap = pol.get("cap")
        new = solve(D, params, target=min(0.99, target + pol["margin"]), locked=staffing, lock_until=M, max_change_frac=cap)
        if not new.get("rows"):
            new = solve(D, params, target=None, locked=staffing, lock_until=M, max_change_frac=cap)
        if not new.get("rows"):
            continue
        before = staffing
        staffing = staffing_of(new)
        changes = {d: sum(abs((staffing["crews"][d][t] + staffing["seasonal"][d][t]) - (before["crews"][d][t] + before["seasonal"][d][t]))
                          for t in range(M, MONTHS)) for d in depts}
        events.append({"after_month": M, "drift": trigger,
                       "crew_months_changed": {d: round(v) for d, v in changes.items() if v >= 1},
                       "hires_next_month": {d: staffing["hires"][d][M] for d in depts if staffing["hires"][d][M]},
                       "releases_next_month": {d: staffing["releases"][d][M] for d in depts if staffing["releases"][d][M]}})
    sim = simulate(staffing, A, params)
    return {"sim": sim, "staffing": staffing, "events": events}


def _score(sim: dict, target: float) -> tuple:
    worst = min(v["on_time_rate"] for v in sim["by_dept"].values())
    feasible = worst >= target - 1e-9
    return (0 if feasible else 1, sim["totals"]["total_cost"] if feasible else -worst)


def select_policy() -> dict:
    """Choose the monitor policy on the 2024 replay only."""
    out = {}
    for name in POLICIES:
        r = replay(2024, name)
        s = r["sim"]
        out[name] = {"total_cost": s["totals"]["total_cost"], "on_time_rate": s["totals"]["on_time_rate"],
                     "worst_dept_on_time": min(v["on_time_rate"] for v in s["by_dept"].values()), "replans": len(r["events"])}
    target = load_params()["default_on_time_target"]
    best = min(out, key=lambda k: (0 if out[k]["worst_dept_on_time"] >= target - 1e-9 else 1,
                                   out[k]["total_cost"] if out[k]["worst_dept_on_time"] >= target - 1e-9 else -out[k]["worst_dept_on_time"]))
    return {"chosen": best, "candidates_2024": out}


def run() -> dict:
    sel = select_policy()
    chosen = SHIPPED_POLICY
    params, plan, F, P10, P90, A, depts = _inputs(2025)
    target = plan["on_time_target"]
    flat = fixed_plan(A, params, flat_staffing(depts, params))
    locked = simulate(staffing_of(plan), A, params)
    hindsight = solve(A, params, target=target)
    mon = replay(2025, chosen)
    all_2025 = {name: (lambda r: {"total_cost": r["sim"]["totals"]["total_cost"], "on_time_rate": r["sim"]["totals"]["on_time_rate"],
                                  "worst_dept_on_time": min(v["on_time_rate"] for v in r["sim"]["by_dept"].values()),
                                  "replans": len(r["events"])})(replay(2025, name)) for name in POLICIES}

    out = {
        "year": 2025, "target": target, "policy": chosen, "policy_params": POLICIES[chosen],
        "policy_note": ("The headline uses the Monitor rule as it shipped, fixed before the replay was built. Variants are "
                        "shown for both years; the one a 2024-only selection would pick is marked."),
        "policy_selection": {**sel, "all_policies_2025": all_2025},
        "strategies": {
            "flat": {"label": "Today’s crews all year", **_summ(flat)},
            "locked": {"label": "Optimised plan, never changed", **_summ(locked)},
            "monitored": {"label": "Optimised plan + monitor", **_summ(mon["sim"]), "replans": len(mon["events"])},
            "hindsight": {"label": "Perfect hindsight (lower bound)", **_summ(hindsight)},
        },
        "events": mon["events"],
        "monitored_crews": {d: [mon["staffing"]["crews"][d][t] + mon["staffing"]["seasonal"][d][t] for t in range(MONTHS)] for d in depts},
        "plan_crews": {d: [plan["crews"][d][t] + plan["seasonal"][d][t] for t in range(MONTHS)] for d in depts},
        "demand": {"actual": A, "forecast": F, "p10": P10, "p90": P90},
    }
    st = out["strategies"]
    for k in st:
        st[k]["depts_at_target"] = sum(v["on_time_rate"] >= target - 1e-9 for v in st[k]["by_dept"].values())
        st[k]["worst_dept_on_time"] = min(v["on_time_rate"] for v in st[k]["by_dept"].values())
    fl, mo, lo, hi = (st[k]["totals"] for k in ("flat", "monitored", "locked", "hindsight"))
    out["headline"] = {
        "saving_vs_flat": round(fl["total_cost"] - mo["total_cost"], 2),
        "saving_vs_locked": round(lo["total_cost"] - mo["total_cost"], 2),
        "gap_to_hindsight": round(mo["total_cost"] - hi["total_cost"], 2),
        "on_time_flat": fl["on_time_rate"], "on_time_monitored": mo["on_time_rate"],
    }
    (CONTRACTS / "replay.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    out = run()
    for k, s in out["strategies"].items():
        t = s["totals"]
        print(f"{s['label']:38s} [{s['depts_at_target']}/4 at target] ${t['total_cost']:>13,.0f}  on time {t['on_time_rate']:.1%}  "
              + "  ".join(f"{d.split()[0]} {v['on_time_rate']:.0%}" for d, v in s["by_dept"].items()))
    print("shipped policy:", out["policy"], "| 2024 selection would pick:", out["policy_selection"]["chosen"])
    print("all policies on 2025:", out["policy_selection"]["all_policies_2025"])
    print("re-plans:", [(e["after_month"], list(e["drift"])) for e in out["events"]])
    print("headline:", out["headline"])
