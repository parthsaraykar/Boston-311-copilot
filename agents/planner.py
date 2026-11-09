"""Planner agent: answers questions about the 2025 plan from tool results only."""
from __future__ import annotations

import re

from agents.runtime import Tracer, run_agent
from agents.tools import DEPTS, MONTH_NAMES, _money

TOOLS = ["get_plan", "get_forecast", "explain_month", "run_scenario", "compare_baselines", "solve_plan", "ask_stress_test"]

SYSTEM = """You are the planning assistant for Boston 311 crew planning (Public Works, Transportation, Parks,
Inspectional Services). The 2025 plan picks crews per department per month to minimise crew cost plus late-request cost.
Use tools to answer: explain_month for "why" questions about a month, run_scenario for what-ifs, compare_baselines for
savings, get_forecast for demand. Months are numbers 1-12."""


def _dept(q: str) -> str | None:
    ql = q.lower()
    for key, d in [("park", "Parks"), ("public works", "Public Works"), ("pwd", "Public Works"), ("transport", "Transportation"),
                   ("parking", "Transportation"), ("btd", "Transportation"), ("inspect", "Inspectional Services"),
                   ("isd", "Inspectional Services"), ("housing", "Inspectional Services"), ("trash", "Public Works"),
                   ("pothole", "Public Works")]:
        if key in ql:
            return d
    return None


def _month(q: str) -> int | None:
    ql = q.lower()
    for i, n in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                           "october", "november", "december"]):
        if re.search(rf"\b({n}|{n[:3]})\b", ql):
            return i + 1
    m = re.search(r"\bmonth (\d{1,2})\b", ql)
    return int(m.group(1)) if m else None


def _pct(q: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
    return float(m.group(1)) / 100 if m else None


def scripted(t: Tracer, q: str) -> str:
    ql = q.lower()
    d, m = _dept(q), _month(q)

    if any(w in ql for w in ["stress", "worst case", "worst-case", "what could go wrong", "biggest risk"]):
        r = t.call("ask_stress_test", focus=q)
        top = r["worst_cases"][0]
        return (f"The worst case found is {top['label']}: the saved plan would cost {_money(top['locked_total_cost'])} "
                f"with {top['locked_on_time']:.1%} on time. The cheapest fix is to re-plan ({top['fix']}), which saves "
                f"{_money(top['cost_of_not_replanning'])}.")

    if any(w in ql for w in ["what if", "what happens", "storm", "snow", "blizzard", "if demand", "late cost", "severance",
                             "training", "slower", "more requests", "fewer requests", "increase", "decrease", "drop"]):
        args = {}
        p = _pct(q)
        if "storm" in ql or "snow" in ql or "blizzard" in ql:
            args["storm"] = True
        if p is not None and any(w in ql for w in ["demand", "request", "volume", "more", "fewer", "increase", "decrease", "drop", "higher", "lower"]):
            down = any(w in ql for w in ["fewer", "decrease", "drop", "lower", "less", "down"])
            args["demand_mult"] = round(1 - p if down else 1 + p, 3)
        if "severance" in ql:
            args["severance_rate"] = p or 0.5
        if "late cost" in ql:
            mm = re.search(r"\$\s?(\d+)", q)
            args["late_cost"] = float(mm.group(1)) if mm else 40.0
        if "training" in ql or "slower hiring" in ql:
            args["training_months"] = 2
        if "seasonal premium" in ql:
            args["seasonal_premium"] = p or 0.5
        if not args:
            args["demand_mult"] = 1.1
        r = t.call("run_scenario", **args)
        worst = min(r["locked_by_dept"].items(), key=lambda kv: kv[1]["on_time_rate"])
        return (f"If we keep the saved plan, total cost goes from {_money(r['base_total_cost'])} to "
                f"{_money(r['locked_total_cost'])} and on-time is {r['locked_on_time']:.1%} "
                f"(lowest: {worst[0]} at {worst[1]['on_time_rate']:.1%}). Re-planning for it would cost "
                f"{_money(r['replanned_total_cost'])} with {r['replanned_on_time']:.1%} on time, so re-planning saves "
                f"{_money(r['cost_of_not_replanning'])}.")

    if any(w in ql for w in ["saving", "save", "flat", "baseline", "compare", "versus", " vs", "worth it"]):
        r = t.call("compare_baselines")
        return (f"The optimised plan costs {_money(r['optimised']['total_cost'])} with {r['optimised']['on_time_rate']:.1%} on time. "
                f"Flat staffing (today's crews all year) costs {_money(r['flat']['total_cost'])} with {r['flat']['on_time_rate']:.1%} "
                f"on time, so the plan saves {_money(r['saving_vs_flat'])}. Level staffing costs {_money(r['level']['total_cost'])} "
                f"({r['level']['on_time_rate']:.1%} on time).")

    if re.search(r"\b(target|reach|hit|get to)\b", ql) and _pct(q):
        tau = _pct(q)
        r = t.call("solve_plan", target=tau)
        b = t.call("get_plan")
        if not r.get("feasible"):
            return f"A {tau:.0%} on-time target isn't reachable with these inputs."
        return (f"Hitting {tau:.0%} on time in every department costs {_money(r['totals']['total_cost'])} "
                f"(on-time {r['totals']['on_time_rate']:.1%}), against {_money(b['totals']['total_cost'])} for the saved plan.")

    if "forecast" in ql or "expect" in ql or "how many requests" in ql or "demand" in ql:
        r = t.call("get_forecast", dept=d, month=m)
        rows = r["forecast"]
        if not rows:
            return "I don't have that."
        if d and m:
            f = rows[0]
            return (f"{d} is forecast to get {f['mean']:,.0f} requests in {MONTH_NAMES[m - 1]} 2025 "
                    f"(likely range {f['p10']:,.0f} to {f['p90']:,.0f}), using the {f['model']} model.")
        if d:
            peak = max(rows, key=lambda x: x["mean"])
            low = min(rows, key=lambda x: x["mean"])
            total = sum(x["mean"] for x in rows)
            return (f"{d} is forecast to get {total:,.0f} requests in 2025, peaking in {MONTH_NAMES[int(peak['month'][-2:]) - 1]} "
                    f"({peak['mean']:,.0f}) and lowest in {MONTH_NAMES[int(low['month'][-2:]) - 1]} ({low['mean']:,.0f}).")
        total = sum(x["mean"] for x in rows)
        return f"Across the four departments the 2025 forecast is {total:,.0f} requests."

    if d and m or (m and any(w in ql for w in ["why", "hire", "seasonal", "crew", "staff"])) or (d and "why" in ql):
        if not d:
            d = "Parks" if "seasonal" in ql else "Public Works"
        if not m:
            r0 = t.call("get_plan", dept=d)
            rows = r0["rows"]
            changes = [r for r in rows if r["hires"] or r["seasonal"] or r["releases"]]
            m = (changes[0] if changes else max(rows, key=lambda x: x["demand"]))["month"]
        e = t.call("explain_month", dept=d, month=m)
        mn = e["month_name"]
        parts = [f"In {mn}, {d} has {e['crews']:.0f} crews" + (f" plus {e['seasonal_crews']:.0f} seasonal" if e["seasonal_crews"] else "")
                 + f" for forecast demand of {e['forecast_demand']:,.0f} requests (capacity {e['capacity']:,.0f}, "
                   f"{e['on_time_rate']:.1%} on time)."]
        if e["hires_this_month"]:
            parts.append(f"It hires {e['hires_this_month']:.0f} crews in {mn} because hires train for one month, so they are ready "
                         f"for {e['demand_next_month']:,.0f} requests next month.")
        elif "hire" in ql:
            parts.append(f"The plan does not hire permanent crews in {mn}.")
        if e["seasonal_crews"]:
            parts.append(f"Parks uses seasonal crews at the peak instead of permanent hires, since they need no training and "
                         f"don't carry severance when the season ends.")
        elif "hire" in ql and d == "Parks":
            nxt = t.call("get_plan", dept="Parks")
            seas = [r for r in nxt["rows"] if r["seasonal"]]
            if seas:
                parts.append(f"Instead it adds seasonal crews from {MONTH_NAMES[seas[0]['month'] - 1]} "
                             f"({seas[0]['seasonal']:.0f} that month), because they start without training and cost less than "
                             f"carrying permanent crews all year.")
        sv = e["shadow_value_one_more_crew"]
        if sv:
            parts.append(f"One more crew in {mn} would save about {_money(sv)} in late costs, against "
                         f"{_money(e['crew_cost_per_month'])} for a crew-month.")
        else:
            parts.append(f"One more crew in {mn} would save nothing: capacity already covers the work.")
        return " ".join(parts)

    if d or "plan" in ql or "crews" in ql or "cost" in ql:
        r = t.call("get_plan", dept=d)
        if d:
            dt = r["dept_totals"]
            crews = [x["crews"] + x["seasonal"] for x in r["rows"]]
            return (f"{d} in the 2025 plan: {min(crews):.0f} to {max(crews):.0f} crews a month, total cost {_money(dt['total_cost'])}, "
                    f"{dt['on_time_rate']:.1%} on time.")
        tot = r["totals"]
        return (f"The 2025 plan costs {_money(tot['total_cost'])} in total with {tot['on_time_rate']:.1%} of requests closed "
                f"within the month, against a {r['on_time_target']:.0%} target in each department.")

    return "I don't have that. I can explain a month of the plan, compare it with flat staffing, show the forecast, or run a what-if."


def ask(question: str, use_llm: bool | None = None) -> dict:
    return run_agent("planner", SYSTEM, TOOLS, question, scripted=scripted, use_llm=use_llm)
