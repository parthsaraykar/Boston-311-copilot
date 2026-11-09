"""Crew-planning integer program and a plan simulator.

solve(demand, params, target=None) picks crews per department per month to minimise crew cost
plus late-request cost. simulate(plan, demand) runs a fixed plan against any demand path.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

import numpy as np
import pulp
import yaml

ROOT = Path(__file__).resolve().parents[1]
MONTHS = 12


def load_params(path: Path | None = None) -> dict:
    return yaml.safe_load((path or ROOT / "params.yaml").read_text())


def with_overrides(params: dict, overrides: dict | None) -> dict:
    """Overrides: late_cost, late30_cost, severance_rate, seasonal_premium, training_months,
    crew_output_mult (scales every k[d]), crew_cost_mult, starting_crews {dept: n}."""
    p = copy.deepcopy(params)
    for key, val in (overrides or {}).items():
        if val is None:
            continue
        if key == "crew_output_mult":
            for d in p["departments"].values():
                d["requests_per_crew_month"] *= val
        elif key == "crew_cost_mult":
            for d in p["departments"].values():
                d["crew_cost"] *= val
        elif key == "starting_crews":
            p["starting_crews"].update(val)
        else:
            p[key] = val
    return p


def _solver(msg=False):
    # CBC ships with PuLP and reports constraint duals for the LP relaxation (HiGHS via PuLP does not)
    return pulp.PULP_CBC_CMD(msg=msg, timeLimit=30)


def solve(demand: dict[str, list[float]], params: dict, target: float | None = None,
          relax: bool = False, fixed: dict | None = None, initial_backlog: dict | None = None,
          paths: list[dict] | None = None, locked: dict | None = None, lock_until: int = 0) -> dict:
    """demand: {dept: [12 monthly values]}. target: min on-time share (0-1) in each department,
    a float or {dept: float}.
    paths: optional list of demand dicts; one plan is chosen for all of them (robust plan).
    locked + lock_until: keep an existing staffing plan for months < lock_until (mid-year re-plan).
    fixed: {dept: [12 crew counts]} forces a staffing level (used for flat / level baselines).
    Returns the plan dict (see contracts/plan.schema.json)."""
    depts = list(demand)
    T = range(MONTHS)
    L = int(params["training_months"])
    cat = pulp.LpContinuous if relax else pulp.LpInteger
    m = pulp.LpProblem("crew_plan", pulp.LpMinimize)

    # robust mode: several demand paths share one staffing plan; late costs are averaged over paths
    paths = paths or [demand]
    P = range(len(paths))
    w = 1.0 / len(paths)

    x = {(d, t): pulp.LpVariable(f"x_{i}_{t}", 0, cat=cat) for i, d in enumerate(depts) for t in T}
    h = {(d, t): pulp.LpVariable(f"h_{i}_{t}", 0, cat=cat) for i, d in enumerate(depts) for t in T}
    r = {(d, t): pulp.LpVariable(f"r_{i}_{t}", 0, cat=cat) for i, d in enumerate(depts) for t in T}
    s = {(d, t): pulp.LpVariable(f"s_{i}_{t}", 0, cat=cat) for i, d in enumerate(depts) for t in T
         if params["departments"][d].get("seasonal_allowed")}
    q = {(p, d, t): pulp.LpVariable(f"q_{p}_{i}_{t}", 0) for p in P for i, d in enumerate(depts) for t in T}
    B = {(p, d, t): pulp.LpVariable(f"B_{p}_{i}_{t}", 0) for p in P for i, d in enumerate(depts) for t in T}
    L30 = {(p, d, t): pulp.LpVariable(f"L30_{p}_{i}_{t}", 0) for p in P for i, d in enumerate(depts) for t in T}

    cost = []
    cap = {}
    for d in depts:
        pd_ = params["departments"][d]
        c, k = pd_["crew_cost"], pd_["requests_per_crew_month"]
        x0 = params["starting_crews"][d]
        b0 = (initial_backlog or {}).get(d, 0.0)
        for t in T:
            trainees = pulp.lpSum(h[d, j] for j in range(max(0, t - L + 1), t + 1)) if L > 0 else 0
            cost += [c / 12 * (x[d, t] + trainees), params["severance_rate"] * c * r[d, t]]
            if (d, t) in s:
                cost.append((1 + params["seasonal_premium"]) * c / 12 * s[d, t])
            # crew balance: hires join after L months of training, releases leave next month
            if t == 0:
                m += x[d, 0] == x0, f"start_{d}"
            if t + 1 < MONTHS:
                joined = h[d, t + 1 - L] if t + 1 - L >= 0 else 0
                m += x[d, t + 1] == x[d, t] + joined - r[d, t], f"balance_{d}_{t}"
            m += r[d, t] <= x[d, t], f"release_le_crew_{d}_{t}"
            capacity = k * (x[d, t] + (s[d, t] if (d, t) in s else 0))
            for p in P:
                D = paths[p][d][t]
                cost += [w * params["late_cost"] * B[p, d, t], w * params["late30_cost"] * L30[p, d, t]]
                cap[p, d, t] = pulp.LpConstraint(q[p, d, t] - capacity, pulp.LpConstraintLE, f"cap_{p}_{d}_{t}", 0)
                m += cap[p, d, t]
                prev = B[p, d, t - 1] if t > 0 else b0
                m += B[p, d, t] == prev + D - q[p, d, t], f"backlog_{p}_{d}_{t}"
                m += L30[p, d, t] >= prev - q[p, d, t], f"old_first_{p}_{d}_{t}"
            if locked is not None and t < lock_until:
                m += h[d, t] == locked["hires"][d][t], f"lock_h_{d}_{t}"
                m += r[d, t] == locked["releases"][d][t], f"lock_r_{d}_{t}"
                if (d, t) in s:
                    m += s[d, t] == locked["seasonal"][d][t], f"lock_s_{d}_{t}"
            if fixed is not None and d in fixed:
                m += x[d, t] == fixed[d][t], f"fixed_{d}_{t}"
            if fixed is not None:
                m += h[d, t] == 0, f"nohire_{d}_{t}"
                m += r[d, t] == 0, f"norelease_{d}_{t}"
                if (d, t) in s:
                    m += s[d, t] == 0, f"noseasonal_{d}_{t}"
        # hires late in the year that never become productive are pointless; forbid them
        for t in range(max(0, MONTHS - L), MONTHS):
            m += h[d, t] == 0, f"no_late_hire_{d}_{t}"
    if target is not None:
        # the on-time target holds in every department (on average over paths in robust mode),
        # so no department is sacrificed for the citywide total
        for d in depts:
            tau = target[d] if isinstance(target, dict) else target
            m += (pulp.lpSum(w * (paths[p][d][t] - B[p, d, t]) for p in P for t in T)
                  >= tau * w * sum(sum(paths[p][d]) for p in P)), f"on_time_target_{d}"
    m += pulp.lpSum(cost)

    status = m.solve(_solver())
    status_name = pulp.LpStatus[status]
    if status_name not in ("Optimal",):
        return {"status": status_name, "feasible": False}

    val = lambda v: float(v.value() or 0.0)  # noqa: E731
    shadow = {}
    if relax:
        for (p, d, t), con in cap.items():
            if p:
                continue
            k = params["departments"][d]["requests_per_crew_month"]
            # dual of q - k*x <= 0 is the late-cost saved per extra unit of capacity; x k = one more crew
            shadow[d, t] = abs(con.pi or 0.0) * k

    crews = {d: [round(val(x[d, t])) if not relax else val(x[d, t]) for t in T] for d in depts}
    hires = {d: [val(h[d, t]) for t in T] for d in depts}
    releases = {d: [val(r[d, t]) for t in T] for d in depts}
    seasonal = {d: [val(s[d, t]) if (d, t) in s else 0.0 for t in T] for d in depts}
    plan = build_plan(demand, params, crews, hires, releases, seasonal, initial_backlog)
    plan["status"] = status_name
    plan["target"] = target
    if relax:
        for row in plan["rows"]:
            row["shadow_value"] = round(shadow[row["dept"], row["t"]], 2)
    return plan


def build_plan(demand, params, crews, hires, releases, seasonal, initial_backlog=None) -> dict:
    """Turn a staffing decision into the full plan table by simulating it on `demand`."""
    sim = simulate({"crews": crews, "hires": hires, "releases": releases, "seasonal": seasonal},
                   demand, params, initial_backlog)
    sim["crews"], sim["hires"], sim["releases"], sim["seasonal"] = crews, hires, releases, seasonal
    return sim


def simulate(staffing: dict, demand: dict[str, list[float]], params: dict,
             initial_backlog: dict | None = None) -> dict:
    """Run a fixed staffing plan through a demand path (no re-optimising). Old backlog is served first."""
    L = int(params["training_months"])
    rows = []
    tot = {"cost_crew": 0.0, "cost_severance": 0.0, "cost_seasonal": 0.0, "cost_late": 0.0, "cost_late30": 0.0,
           "demand": 0.0, "on_time": 0.0, "late30_requests": 0.0}
    by_dept = {}
    for d in demand:
        pd_ = params["departments"][d]
        c, k = pd_["crew_cost"], pd_["requests_per_crew_month"]
        backlog = (initial_backlog or {}).get(d, 0.0)
        dt = {key: 0.0 for key in tot}
        for t in range(MONTHS):
            x = staffing["crews"][d][t]
            hires = staffing["hires"][d]
            trainees = sum(hires[j] for j in range(max(0, t - L + 1), t + 1)) if L > 0 else 0
            s = staffing["seasonal"][d][t]
            rel = staffing["releases"][d][t]
            D = float(demand[d][t])
            capacity = k * (x + s)
            served = min(capacity, backlog + D)
            old_unserved = max(0.0, backlog - served)
            on_time = max(0.0, min(D, served - backlog))
            new_backlog = backlog + D - served
            row = {
                "dept": d, "t": t, "month": t + 1, "demand": round(D, 1),
                "crews": x, "hires": hires[t], "releases": rel, "seasonal": s,
                "capacity": round(capacity, 1), "served": round(served, 1),
                "backlog": round(new_backlog, 1), "late": round(new_backlog, 1),
                "late30": round(old_unserved, 1), "on_time_rate": round(on_time / D, 4) if D else 1.0,
                "cost_crew": round(c / 12 * (x + trainees), 2),
                "cost_severance": round(params["severance_rate"] * c * rel, 2),
                "cost_seasonal": round((1 + params["seasonal_premium"]) * c / 12 * s, 2),
                "cost_late": round(params["late_cost"] * new_backlog, 2),
                "cost_late30": round(params["late30_cost"] * old_unserved, 2),
                "shadow_value": None,
            }
            rows.append(row)
            for key in ("cost_crew", "cost_severance", "cost_seasonal", "cost_late", "cost_late30"):
                dt[key] += row[key]
            dt["demand"] += D
            dt["on_time"] += on_time
            dt["late30_requests"] += old_unserved
            backlog = new_backlog
        dt["total_cost"] = sum(dt[k_] for k_ in ("cost_crew", "cost_severance", "cost_seasonal", "cost_late", "cost_late30"))
        dt["on_time_rate"] = dt["on_time"] / dt["demand"] if dt["demand"] else 1.0
        dt["end_backlog"] = backlog
        dt["peak_crews"] = max(staffing["crews"][d][t] + staffing["seasonal"][d][t] for t in range(MONTHS))
        by_dept[d] = {k_: round(v, 4 if k_ == "on_time_rate" else 2) for k_, v in dt.items()}
        for key in tot:
            tot[key] += dt[key]
    tot["total_cost"] = sum(tot[k_] for k_ in ("cost_crew", "cost_severance", "cost_seasonal", "cost_late", "cost_late30"))
    tot["on_time_rate"] = tot["on_time"] / tot["demand"] if tot["demand"] else 1.0
    tot = {k_: round(v, 4 if k_ == "on_time_rate" else 2) for k_, v in tot.items()}
    return {"rows": rows, "by_dept": by_dept, "totals": tot}


def staffing_of(plan: dict) -> dict:
    return {k: plan[k] for k in ("crews", "hires", "releases", "seasonal")}


def flat_staffing(depts, params) -> dict:
    return {d: [params["starting_crews"][d]] * MONTHS for d in depts}


def level_staffing(demand, params) -> dict:
    return {d: [math.ceil(np.mean(demand[d]) / params["departments"][d]["requests_per_crew_month"])] * MONTHS
            for d in demand}


def fixed_plan(demand, params, crews) -> dict:
    """Hold a crew level all year. If it differs from today's crews, the change happens in January:
    hires train in January (productive from February), releases leave after January with severance."""
    zeros = {d: [0.0] * MONTHS for d in demand}
    hires, releases, path = {}, {}, {}
    for d in demand:
        x0, target = params["starting_crews"][d], crews[d][0]
        hires[d] = [float(max(0, target - x0))] + [0.0] * (MONTHS - 1)
        releases[d] = [float(max(0, x0 - target))] + [0.0] * (MONTHS - 1)
        path[d] = [x0] + [target] * (MONTHS - 1) if params["training_months"] <= 1 or target < x0 else \
            [x0] * int(params["training_months"]) + [target] * (MONTHS - int(params["training_months"]))
    return build_plan(demand, params, path, hires, releases, zeros)
