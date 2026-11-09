"""Calibrate starting crews, then build the optimised plan, baselines, frontier and shadow prices.

Run: python -m optimizer.run   -> contracts/plan.json, baselines.json, frontier.json
"""
import json
import re
from pathlib import Path

import pandas as pd

from forecast.model import load_forecast
from optimizer.model import (MONTHS, ROOT, fixed_plan, flat_staffing, level_staffing, load_params, solve)

CONTRACTS = ROOT / "contracts"
MONTHLY = ROOT / "data" / "processed" / "monthly.parquet"


def forecast_demand(col: str = "mean") -> dict[str, list[float]]:
    f = load_forecast().sort_values(["dept", "month"])
    return {d: g[col].tolist() for d, g in f.groupby("dept")}


def actual_demand(year: int) -> dict[str, list[float]]:
    m = pd.read_parquet(MONTHLY)
    m = m[pd.to_datetime(m["month"]).dt.year == year].sort_values(["dept", "month"])
    return {d: g["requests"].astype(float).tolist() for d, g in m.groupby("dept")}


def observed_on_time(year: int) -> dict[str, float]:
    m = pd.read_parquet(MONTHLY)
    m = m[pd.to_datetime(m["month"]).dt.year == year]
    g = m.groupby("dept")[["on_time", "requests"]].sum()
    return (g["on_time"] / g["requests"]).to_dict()


def calibrate(params: dict, year: int = 2024) -> dict[str, int]:
    """Smallest flat crew count whose simulated on-time rate on `year` demand reaches the real one."""
    demand, target = actual_demand(year), observed_on_time(year)
    out = {}
    for d, D in demand.items():
        for n in range(1, 2000):
            p = {**params, "starting_crews": {**params["starting_crews"], d: n}}
            sim = fixed_plan({d: D}, p, {d: [n] * MONTHS})
            if sim["by_dept"][d]["on_time_rate"] >= target[d]:
                out[d] = n
                break
    return out


def write_starting_crews(crews: dict[str, int]) -> None:
    path = ROOT / "params.yaml"
    text = path.read_text()
    for d, n in crews.items():
        text = re.sub(rf"(starting_crews:[\s\S]*?\n  {re.escape(d)}: )\d+", rf"\g<1>{n}", text)
    path.write_text(text)


def history_fit(params: dict) -> dict:
    """Check the model's 'closed within the month = on time' rule against real monthly on-time rates:
    run today's crews flat through 2023-24 actual demand and compare month by month."""
    m = pd.read_parquet(MONTHLY)
    m["month"] = pd.to_datetime(m["month"])
    out = {}
    for d in params["departments"]:
        rows = []
        for year in (2023, 2024):
            g = m[(m["dept"] == d) & (m["month"].dt.year == year)].sort_values("month")
            D = g["requests"].astype(float).tolist()
            sim = fixed_plan({d: D}, params, {d: [params["starting_crews"][d]] * MONTHS})
            for row, (_, real) in zip(sim["rows"], g.iterrows()):
                rows.append({"month": real["month"].strftime("%Y-%m"), "model_on_time": row["on_time_rate"],
                             "real_on_time": round(real["on_time"] / real["requests"], 4),
                             "model_backlog": row["backlog"]})
        df = pd.DataFrame(rows)
        corr = df["model_on_time"].corr(df["real_on_time"])
        out[d] = {"months": rows, "correlation": round(float(corr), 3) if pd.notna(corr) else None,
                  "mae": round(float((df["model_on_time"] - df["real_on_time"]).abs().mean()), 4)}
    return out


def run(target: float | None = None) -> dict:
    params = load_params()
    crews0 = calibrate(params)
    write_starting_crews(crews0)
    params = load_params()
    target = params["default_on_time_target"] if target is None else target
    demand = forecast_demand()

    optimised = solve(demand, params, target=target)
    unconstrained = solve(demand, params, target=None)
    lp = solve(demand, params, target=target, relax=True)
    flat = fixed_plan(demand, params, flat_staffing(demand, params))
    level = fixed_plan(demand, params, level_staffing(demand, params))
    # merge LP shadow values into the integer plan rows
    sv = {(r["dept"], r["t"]): r["shadow_value"] for r in lp["rows"]}
    for row in optimised["rows"]:
        row["shadow_value"] = sv[row["dept"], row["t"]]
        crew_month = params["departments"][row["dept"]]["crew_cost"] / 12
        row["net_value_extra_crew"] = round(row["shadow_value"] - crew_month, 2)

    plan = {"plan_year": 2025, "on_time_target": target, "params": params, "starting_crews": crews0,
            "calibration": {"year": 2024, "observed_on_time": observed_on_time(2024)}, **optimised}
    baselines = {
        name: {"totals": p["totals"], "by_dept": p["by_dept"], "crews": p["crews"]}
        for name, p in [("flat", flat), ("level", level), ("optimised", optimised),
                        ("cost_only", unconstrained)]
    }
    baselines["saving_vs_flat"] = round(flat["totals"]["total_cost"] - optimised["totals"]["total_cost"], 2)
    baselines["saving_vs_level"] = round(level["totals"]["total_cost"] - optimised["totals"]["total_cost"], 2)

    frontier = []
    for tau in [x / 100 for x in range(50, 100, 5)]:
        p = solve(demand, params, target=tau)
        if p.get("feasible", True):
            frontier.append({"target": tau, "total_cost": p["totals"]["total_cost"],
                             "on_time_rate": p["totals"]["on_time_rate"],
                             "crew_cost": p["totals"]["cost_crew"] + p["totals"]["cost_seasonal"],
                             "late_cost": p["totals"]["cost_late"] + p["totals"]["cost_late30"]})

    plan["history_fit"] = history_fit(params)
    CONTRACTS.mkdir(exist_ok=True)
    (CONTRACTS / "plan.json").write_text(json.dumps(plan, indent=1))
    # the original plan, so `make reset` can undo approved re-plans before a demo
    (CONTRACTS / "plan_history").mkdir(exist_ok=True)
    (CONTRACTS / "plan_history" / "plan_original.json").write_text(json.dumps(plan, indent=1))
    (CONTRACTS / "baselines.json").write_text(json.dumps(baselines, indent=1))
    (CONTRACTS / "frontier.json").write_text(json.dumps(frontier, indent=1))
    return {"plan": plan, "baselines": baselines, "frontier": frontier}


if __name__ == "__main__":
    out = run()
    print("starting crews:", out["plan"]["starting_crews"])
    for name in ("flat", "level", "optimised", "cost_only"):
        t = out["baselines"][name]["totals"]
        print(f"{name:10s} cost ${t['total_cost']:>13,.0f}  on-time {t['on_time_rate']:.1%}")
    print("saving vs flat:", f"${out['baselines']['saving_vs_flat']:,.0f}")
    print("history fit:", {d: (v["correlation"], v["mae"]) for d, v in out["plan"]["history_fit"].items()})
    for f in out["frontier"]:
        print(f"  tau {f['target']:.2f}  ${f['total_cost']:,.0f}  on-time {f['on_time_rate']:.1%}")
