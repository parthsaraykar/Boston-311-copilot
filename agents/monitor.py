"""Monitor agent: catch demand outside the forecast band and draft a re-plan for a person to approve."""
from __future__ import annotations

from agents.runtime import Tracer, run_agent
from agents.tools import MONTH_NAMES, _money

TOOLS = ["get_live_demand", "get_forecast", "solve_plan", "propose_plan"]
SYSTEM = """You monitor live 311 demand against the forecast band. Call get_live_demand. If any department's latest month
is above p90 or below p10, or year-to-date demand is more than 8% off forecast, call propose_plan with a one-line reason.
Otherwise report that there is no drift."""

YTD_TOLERANCE = 0.08


def scripted(t: Tracer, _q: str) -> str:
    live = t.call("get_live_demand")
    M = live["as_of_month"]
    drift = []
    for d, v in live["departments"].items():
        last = v["months"][-1]
        if last["outside_band"]:
            drift.append(f"{d} {MONTH_NAMES[M - 1]} demand {last['actual']:,.0f} is {last['outside_band']} the band "
                         f"({last['p10']:,.0f}-{last['p90']:,.0f})")
        elif v["ytd_ratio"] and abs(v["ytd_ratio"] - 1) > YTD_TOLERANCE:
            drift.append(f"{d} year-to-date demand is {v['ytd_ratio'] - 1:+.1%} vs forecast")
    if not drift:
        return f"No drift through {MONTH_NAMES[M - 1]}: every department is inside its forecast band."
    reason = "; ".join(drift)
    p = t.call("propose_plan", reason=reason, as_of_month=M)
    return (f"Drift found: {reason}. I drafted re-plan {p['proposal_id']} for the rest of the year: it costs "
            f"{_money(p['new_plan_cost'])} ({p['new_plan_on_time']:.1%} on time) vs {_money(p['keep_plan_cost'])} "
            f"({p['keep_plan_on_time']:.1%}) if we keep the current plan. It needs a person to approve it.")


def run_monitor(use_llm: bool | None = False) -> dict:
    res = run_agent("monitor", SYSTEM, TOOLS, "Check live demand against the forecast and propose a re-plan if needed.",
                    scripted=scripted, use_llm=use_llm, max_steps=6)
    proposal = next((o for o in res["tool_outputs"] if isinstance(o, dict) and o.get("proposal_id")), None)
    return {**{k: v for k, v in res.items() if k != "tool_outputs"}, "proposal": proposal}
