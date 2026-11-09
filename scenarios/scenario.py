"""Sensitivity analysis: locked plan (robustness) vs re-planned (what we'd pick knowing the change).

Run: python -m scenarios.scenario   -> contracts/scenarios.json
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from optimizer.model import MONTHS, ROOT, load_params, simulate, solve, staffing_of, with_overrides

CONTRACTS = ROOT / "contracts"
PROCESSED = ROOT / "data" / "processed"


# ---------- inputs ----------

def base_demand() -> dict[str, list[float]]:
    from optimizer.run import forecast_demand
    return forecast_demand()


@lru_cache(maxsize=1)
def base_plan_cached() -> str:
    return (CONTRACTS / "plan.json").read_text()


def base_plan() -> dict:
    return json.loads(base_plan_cached())


def restaff(staffing: dict, params: dict) -> dict:
    """Recompute the crew path from hires and releases under (possibly changed) training lag."""
    L = int(params["training_months"])
    out = copy.deepcopy(staffing)
    for d in staffing["crews"]:
        x = [float(params["starting_crews"][d])]
        for t in range(MONTHS - 1):
            joined = staffing["hires"][d][t + 1 - L] if t + 1 - L >= 0 else 0.0
            x.append(max(0.0, x[-1] + joined - staffing["releases"][d][t]))
        out["crews"][d] = x
    return out


# ---------- storm from real data ----------

def find_storms(top_n: int = 3, months=(12, 1, 2, 3)) -> list[dict]:
    """Days whose citywide count (four depts) is far above the 28-day rolling median, in the given months
    (winter = snowstorms; summer = heat waves)."""
    daily = pd.read_parquet(PROCESSED / "daily.parquet")
    daily["day"] = pd.to_datetime(daily["day"])
    total = daily.groupby("day")["requests"].sum().asfreq("D", fill_value=0)
    base = total.rolling(28, center=True, min_periods=7).median()
    ratio = total / base
    winter = ratio[ratio.index.month.isin(list(months)) & (ratio.index.year <= 2024)]
    storms, used = [], set()
    for day, rv in winter.sort_values(ascending=False).items():
        if any(abs((day - u).days) < 10 for u in used):
            continue
        window = pd.date_range(day - pd.Timedelta(days=1), day + pd.Timedelta(days=6))
        by_dept = {}
        for dept, g in daily.groupby("dept"):
            s = g.set_index("day")["requests"].asfreq("D", fill_value=0)
            b = s.rolling(28, center=True, min_periods=7).median()
            extra = float((s.reindex(window, fill_value=0) - b.reindex(window).fillna(0)).clip(lower=0).sum())
            by_dept[dept] = round(extra, 0)
        storms.append({"day": day.strftime("%Y-%m-%d"), "ratio": round(float(rv), 2), "extra_requests": by_dept})
        used.add(day)
        if len(storms) == top_n:
            break
    return storms


HEAT_MONTHS = (6, 7, 8)


def storm_demand(demand: dict, storms: list[dict] | None = None, into=(0, 1)) -> dict:
    """Inject the worst real spike into the first month in `into` and the second worst into the next
    (snowstorms into January-February by default; heat waves into July-August)."""
    storms = storms or find_storms(2)
    out = copy.deepcopy(demand)
    for month, storm in zip(into, storms):
        for d in out:
            out[d][month] += storm["extra_requests"].get(d, 0.0)
    return out


# ---------- core ----------

def scale_demand(demand: dict, mult: float) -> dict:
    return {d: [v * mult for v in vals] for d, vals in demand.items()}


def scenario(demand_mult: float = 1.0, storm: bool = False, overrides: dict | None = None,
             target: float | None = None, demand: dict | None = None, heatwave: bool = False) -> dict:
    """Locked = keep the saved plan and live with the new world. Replanned = solve again in the new world."""
    params0 = load_params()
    params = with_overrides(params0, overrides)
    plan = base_plan()
    target = plan["on_time_target"] if target is None else target
    D = demand or base_demand()
    D = scale_demand(D, demand_mult)
    if storm:
        D = storm_demand(D)
    if heatwave:
        D = storm_demand(D, find_storms(2, HEAT_MONTHS), into=(6, 7))
    locked = simulate(restaff(staffing_of(plan), params), D, params)
    replanned = solve(D, params, target=target)
    if not replanned.get("rows"):  # target infeasible: fall back to the cheapest plan
        replanned = solve(D, params, target=None)
    summarize = lambda p: {"totals": p["totals"], "by_dept": p["by_dept"]}  # noqa: E731
    return {
        "inputs": {"demand_mult": demand_mult, "storm": storm, "heatwave": heatwave, "overrides": overrides or {}, "target": target},
        "locked": summarize(locked),
        "replanned": {**summarize(replanned), "crews": replanned["crews"], "seasonal": replanned["seasonal"],
                      "hires": replanned["hires"]},
        "base": {"totals": plan["totals"]},
        "cost_of_not_replanning": round(locked["totals"]["total_cost"] - replanned["totals"]["total_cost"], 2),
    }


# ---------- 100 simulated years ----------

def sample_paths(n: int = 100, seed: int = 7, demand: dict | None = None) -> list[dict]:
    """Bootstrap monthly relative errors from the forecast backtest, plus a shared year-level shock."""
    rng = np.random.default_rng(seed)
    resid = json.loads((ROOT / "forecast" / "residuals.json").read_text())
    D = demand or base_demand()
    paths = []
    for _ in range(n):
        path = {}
        for d, vals in D.items():
            e = np.asarray(resid[d])
            year_shock = rng.choice(e)  # errors are correlated within a year; carry half of one draw
            monthly = rng.choice(e, size=MONTHS) - e.mean()
            path[d] = [max(0.0, v * (1 + 0.5 * year_shock + 0.5 * monthly[t])) for t, v in enumerate(vals)]
        paths.append(path)
    return paths


def monte_carlo(staffing: dict | None = None, n: int = 100, target: float | None = None, seed: int = 7) -> dict:
    params = load_params()
    plan = base_plan()
    staffing = staffing or staffing_of(plan)
    target = plan["on_time_target"] if target is None else target
    costs, hits, ontime = [], 0, []
    dept_hits = {d: 0 for d in staffing["crews"]}
    for path in sample_paths(n, seed):
        sim = simulate(staffing, path, params)
        costs.append(sim["totals"]["total_cost"])
        ontime.append(sim["totals"]["on_time_rate"])
        ok = all(v["on_time_rate"] >= target for v in sim["by_dept"].values())
        hits += ok
        for d, v in sim["by_dept"].items():
            dept_hits[d] += v["on_time_rate"] >= target
    q = lambda a, p: round(float(np.quantile(a, p)), 2)  # noqa: E731
    return {
        "years": n, "target": target, "years_all_depts_hit_target": hits, "years_dept_hit_target": dept_hits,
        "cost_p10": q(costs, 0.1), "cost_p50": q(costs, 0.5), "cost_p90": q(costs, 0.9),
        "on_time_p10": q(ontime, 0.1), "on_time_p50": q(ontime, 0.5), "on_time_p90": q(ontime, 0.9),
        "costs": [round(c, 0) for c in costs],
    }


def robust_plan(n_paths: int = 20, target: float | None = None) -> dict:
    """Choose one plan that minimises expected cost across sampled demand paths."""
    params = load_params()
    plan = base_plan()
    target = plan["on_time_target"] if target is None else target
    D = base_demand()
    paths = sample_paths(n_paths, seed=11)
    robust = solve(D, params, target=target, paths=paths)
    return {"plan": robust, "monte_carlo": monte_carlo(staffing_of(robust), seed=7)}


# ---------- employee work smoothing ----------

def smoothing_demand(share_moved: float = 0.3) -> dict:
    """Move `share_moved` of employee-logged work in above-average months into below-average months."""
    m = pd.read_parquet(PROCESSED / "monthly.parquet")
    m["month"] = pd.to_datetime(m["month"])
    emp = m[m["month"].dt.year.isin([2023, 2024])].groupby(["dept", m["month"].dt.month])["employee_share"].mean()
    D = base_demand()
    out = {}
    for d, vals in D.items():
        v = np.array(vals, float)
        emp_work = v * np.array([emp.get((d, t + 1), 0.4) for t in range(MONTHS)])
        mean = v.mean()
        excess = np.clip(v - mean, 0, None)
        movable = np.minimum(excess, emp_work) * share_moved
        deficit = np.clip(mean - v, 0, None)
        add = deficit / deficit.sum() * movable.sum() if deficit.sum() else 0
        out[d] = (v - movable + add).tolist()
    return out


def smoothing(share_moved: float = 0.3) -> dict:
    params = load_params()
    plan = base_plan()
    D = smoothing_demand(share_moved)
    smooth = solve(D, params, target=plan["on_time_target"])
    peak = lambda p: {d: max(p["crews"][d][t] + p["seasonal"][d][t] for t in range(MONTHS)) for d in p["crews"]}  # noqa
    return {
        "share_moved": share_moved,
        "peak_crews_base": peak(plan), "peak_crews_smoothed": peak(smooth),
        "cost_base": plan["totals"]["total_cost"], "cost_smoothed": smooth["totals"]["total_cost"],
        "annual_saving": round(plan["totals"]["total_cost"] - smooth["totals"]["total_cost"], 2),
        "demand_smoothed": {d: [round(x, 1) for x in v] for d, v in D.items()},
    }


# ---------- tornado ----------

TORNADO_INPUTS = [
    ("Demand", {"demand_mult": 0.9}, {"demand_mult": 1.1}, "-10% / +10%"),
    ("Crew output k", {"overrides": {"crew_output_mult": 0.9}}, {"overrides": {"crew_output_mult": 1.1}}, "-10% / +10%"),
    ("Crew cost", {"overrides": {"crew_cost_mult": 0.9}}, {"overrides": {"crew_cost_mult": 1.1}}, "-10% / +10%"),
    ("Late cost", {"overrides": {"late_cost": 10}}, {"overrides": {"late_cost": 40}}, "$10 / $40"),
    ("30+ day late cost", {"overrides": {"late30_cost": 50}}, {"overrides": {"late30_cost": 200}}, "$50 / $200"),
    ("Severance", {"overrides": {"severance_rate": 0.125}}, {"overrides": {"severance_rate": 0.5}}, "12.5% / 50%"),
    ("Seasonal premium", {"overrides": {"seasonal_premium": 0.15}}, {"overrides": {"seasonal_premium": 0.5}}, "15% / 50%"),
    ("Training time", {"overrides": {"training_months": 0}}, {"overrides": {"training_months": 2}}, "0 / 2 months"),
]


def tornado() -> list[dict]:
    base = base_plan()["totals"]["total_cost"]
    rows = []
    for name, lo, hi, label in TORNADO_INPUTS:
        a, b = scenario(**lo), scenario(**hi)
        rows.append({
            "input": name, "range": label,
            "low_replanned": a["replanned"]["totals"]["total_cost"] - base,
            "high_replanned": b["replanned"]["totals"]["total_cost"] - base,
            "low_locked": a["locked"]["totals"]["total_cost"] - base,
            "high_locked": b["locked"]["totals"]["total_cost"] - base,
        })
    rows.sort(key=lambda r: -max(abs(r["low_replanned"]), abs(r["high_replanned"])))
    return rows


# ---------- precompute ----------

def run() -> dict:
    storms = find_storms(3)
    cases = {}
    for mult in (0.8, 0.9, 1.1, 1.2):
        cases[f"demand_x{mult}"] = scenario(demand_mult=mult)
    cases["storm"] = scenario(storm=True)
    cases["heatwave"] = scenario(heatwave=True)
    cases["late_cost_40"] = scenario(overrides={"late_cost": 40})
    cases["severance_50"] = scenario(overrides={"severance_rate": 0.5})
    cases["seasonal_premium_50"] = scenario(overrides={"seasonal_premium": 0.5})
    cases["crew_output_minus10"] = scenario(overrides={"crew_output_mult": 0.9})
    cases["training_2_months"] = scenario(overrides={"training_months": 2})

    # does hiring ahead of the storm pay off? compare locked plan vs the storm-aware plan on storm demand
    st = cases["storm"]
    storm_summary = {
        "storms": storms,
        "extra_cost_locked": round(st["locked"]["totals"]["total_cost"] - st["base"]["totals"]["total_cost"], 2),
        "extra_late_requests_locked": round(
            st["locked"]["totals"]["demand"] * (1 - st["locked"]["totals"]["on_time_rate"])
            - base_plan()["totals"]["demand"] * (1 - base_plan()["totals"]["on_time_rate"]), 0),
        "hiring_ahead_saves": st["cost_of_not_replanning"],
    }
    hw = cases["heatwave"]
    heat_summary = {
        "spikes": find_storms(3, HEAT_MONTHS),
        "extra_cost_locked": round(hw["locked"]["totals"]["total_cost"] - hw["base"]["totals"]["total_cost"], 2),
        "on_time_locked": hw["locked"]["totals"]["on_time_rate"],
        "replanning_saves": hw["cost_of_not_replanning"],
    }
    mc = monte_carlo()
    robust = robust_plan()
    out = {
        "cases": cases, "storm": storm_summary, "heatwave": heat_summary, "monte_carlo": mc,
        "robust": {"crews": robust["plan"]["crews"], "seasonal": robust["plan"]["seasonal"],
                   "totals_on_mean": robust["plan"]["totals"], "monte_carlo": robust["monte_carlo"]},
        "smoothing": smoothing(0.3),
        "tornado": tornado(),
    }
    CONTRACTS.mkdir(exist_ok=True)
    (CONTRACTS / "scenarios.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    out = run()
    for k, c in out["cases"].items():
        print(f"{k:22s} locked ${c['locked']['totals']['total_cost']:>12,.0f} ({c['locked']['totals']['on_time_rate']:.1%})"
              f"  replanned ${c['replanned']['totals']['total_cost']:>12,.0f} ({c['replanned']['totals']['on_time_rate']:.1%})")
    print("storms:", [(s["day"], s["ratio"]) for s in out["storm"]["storms"]])
    print("storm:", {k: v for k, v in out["storm"].items() if k != "storms"})
    print("heat wave:", [(x["day"], x["ratio"]) for x in out["heatwave"]["spikes"]], {k: v for k, v in out["heatwave"].items() if k != "spikes"})
    mc = out["monte_carlo"]
    print(f"monte carlo: all depts hit {mc['target']:.0%} in {mc['years_all_depts_hit_target']}/100 years; "
          f"cost p10/p50/p90 {mc['cost_p10']:,.0f} / {mc['cost_p50']:,.0f} / {mc['cost_p90']:,.0f}; per dept {mc['years_dept_hit_target']}")
    rmc = out["robust"]["monte_carlo"]
    print(f"robust plan: hit in {rmc['years_all_depts_hit_target']}/100, cost p50 {rmc['cost_p50']:,.0f}; per dept {rmc['years_dept_hit_target']}")
    sm = out["smoothing"]
    print("smoothing:", sm["peak_crews_base"], "->", sm["peak_crews_smoothed"], "saving", sm["annual_saving"])
    for t in out["tornado"]:
        print(f"  {t['input']:20s} {t['range']:14s} {t['low_replanned']:>12,.0f} {t['high_replanned']:>12,.0f}")
