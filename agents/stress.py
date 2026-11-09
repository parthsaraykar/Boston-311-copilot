"""Stress-test agent: find the 3 demand scenarios that hurt the saved plan most, and the cheapest fix for each.

The agent searches the scenario space step by step (at most 8 probes); we check it against a brute-force grid.
"""
from __future__ import annotations

import itertools

from agents.runtime import Tracer, run_agent
from optimizer.model import load_params, simulate, staffing_of, with_overrides
from scenarios.scenario import base_demand, base_plan, restaff, scale_demand, storm_demand

TOOLS = ["get_forecast", "run_scenario", "solve_plan", "get_plan"]
SYSTEM = """You stress-test the saved 2025 crew plan. Use run_scenario to probe demand changes (demand_mult between 0.8
and 1.3), storms, slower crews (crew_output_mult) and slower hiring (training_months). Find the three scenarios with the
highest locked cost and report the cheapest fix (re-plan) for each."""

MAX_PROBES = 14  # greedy one-step moves need up to 4+4+3+2+1 probes to reach the harshest corner; the grid has 24 cells
DIMS = {"demand_mult": [1.0, 1.1, 1.2], "storm": [False, True], "crew_output_mult": [1.0, 0.9], "training_months": [1, 2]}


def _label(c: dict) -> str:
    parts = []
    if c["demand_mult"] != 1.0:
        parts.append(f"demand {c['demand_mult'] - 1:+.0%}")
    if c["storm"]:
        parts.append("a real-data snowstorm in Jan-Feb")
    if c["crew_output_mult"] != 1.0:
        parts.append(f"crews {1 - c['crew_output_mult']:.0%} slower")
    if c["training_months"] != 1:
        parts.append(f"{c['training_months']}-month training")
    return ", ".join(parts) or "the forecast"


def locked_cost(c: dict) -> dict:
    params = with_overrides(load_params(), {"crew_output_mult": c["crew_output_mult"], "training_months": c["training_months"]})
    D = scale_demand(base_demand(), c["demand_mult"])
    if c["storm"]:
        D = storm_demand(D)
    sim = simulate(restaff(staffing_of(base_plan()), params), D, params)
    return {"total_cost": sim["totals"]["total_cost"], "on_time": sim["totals"]["on_time_rate"]}


def brute_force_grid() -> list[dict]:
    keys = list(DIMS)
    out = []
    for vals in itertools.product(*DIMS.values()):
        c = dict(zip(keys, vals))
        out.append({**c, **locked_cost(c)})
    return sorted(out, key=lambda x: -x["total_cost"])


def scripted(t: Tracer, focus: str) -> str:
    # greedy coordinate search from the forecast: each probe moves one dimension to its harsher value
    current = {k: v[0] for k, v in DIMS.items()}
    probes = []
    for step in range(sum(len(v) - 1 for v in DIMS.values())):
        best = None
        for k, vals in DIMS.items():
            if current[k] == vals[-1]:
                continue
            cand = {**current, k: vals[vals.index(current[k]) + 1]}
            r = t.call("run_scenario", **cand)
            probes.append({**cand, "locked_total_cost": r["locked_total_cost"], "locked_on_time": r["locked_on_time"],
                           "replanned_total_cost": r["replanned_total_cost"], "cost_of_not_replanning": r["cost_of_not_replanning"],
                           "replanned_hires": r["replanned_hires"], "replanned_peak_crews": r["replanned_peak_crews"]})
            if best is None or r["locked_total_cost"] > best[1]:
                best = (cand, r["locked_total_cost"])
            if len(t.sources) >= MAX_PROBES:
                break
        if best is None or len(t.sources) >= MAX_PROBES:
            break
        current = best[0]
    seen, ranked = set(), []
    for p in sorted(probes, key=lambda x: -x["locked_total_cost"]):
        key = tuple(p[k] for k in DIMS)
        if key not in seen:
            seen.add(key)
            ranked.append(p)
    t._ranked = ranked[:3]  # noqa: SLF001 - read back by run_stress_test
    lines = []
    for i, p in enumerate(ranked[:3], 1):
        hires = {d: h for d, h in p["replanned_hires"].items() if h}
        fix = ", ".join(f"hire {h:.0f} {d}" for d, h in hires.items()) or "re-time seasonal crews"
        p["label"], p["fix"] = _label(p), fix
        lines.append(f"{i}. {p['label']}: the saved plan costs ${p['locked_total_cost']:,.0f} with {p['locked_on_time']:.1%} on time; "
                     f"the cheapest fix is to re-plan ({fix}), saving ${p['cost_of_not_replanning']:,.0f}.")
    return "Worst cases for the saved plan:\n" + "\n".join(lines)


def run_stress_test(focus: str = "", use_llm: bool | None = False) -> dict:
    holder = {}

    def policy(t, q):
        out = scripted(t, q)
        holder["ranked"] = t._ranked  # noqa: SLF001
        holder["probes"] = len(t.sources)
        return out

    res = run_agent("stress_test", SYSTEM, TOOLS, focus or "Find the worst cases for the saved plan.", scripted=policy,
                    use_llm=use_llm, max_steps=MAX_PROBES)
    grid = brute_force_grid()
    ranked = holder.get("ranked", [])
    found = bool(ranked) and all(ranked[0][k] == grid[0][k] for k in DIMS)
    return {**{k: res[k] for k in ("run_id", "answer", "sources", "grounded", "mode", "steps", "latency_ms")},
            "worst_cases": ranked,
            "grid_check": {"grid_size": len(grid), "grid_worst": {**{k: grid[0][k] for k in DIMS}, "label": _label(grid[0]),
                                                                  "locked_total_cost": grid[0]["total_cost"]},
                           "agent_found_grid_worst": found, "agent_probes": holder.get("probes")}}
