"""Intake agent: multi-turn. Files the request in the right queue with a location, shows 911, or stops after
3 follow-ups (then the request goes to the human review queue)."""
from __future__ import annotations

from agents.runtime import Tracer, run_agent
from agents.tools import current_month
from core import db, llm

TOOLS = ["classify", "geocode", "find_duplicates", "get_expected_fix", "file_request", "search_categories"]
SYSTEM = "You file Boston 311 requests: classify, get a location, check duplicates, then file."
MAX_FOLLOWUPS = 3


def _file(t: Tracer, state: dict, cls: dict, review: bool = False) -> str:
    if cls.get("location"):
        dups = t.call("find_duplicates", type=cls["type"], lat=cls["location"]["lat"], lon=cls["location"]["lon"])
        cls["similar_open"] = dups["similar_open"]
    fix = t.call("get_expected_fix", type=cls["type"], neighborhood=(cls.get("location") or {}).get("neighborhood"))
    filed = t.call("file_request", classification=cls, as_of_month=current_month())
    if review and filed.get("request_id"):
        db.execute("update intake_log set review='pending' where id=?", (filed["request_id"],))
    state.update(done=True, filed=filed, classification=cls)
    where = f" near {cls['location_text']}" if cls.get("location_text") else ""
    days = fix.get("median_days_to_close")
    if days is None:
        eta = ""
    elif days < 1.5:
        eta = " Requests like this are usually handled within a day."
    else:
        eta = f" Requests like this usually close in about {days:.0f} days."
    n = len(cls.get("similar_open") or [])
    dup = "" if not n else (" There is 1 similar open report nearby." if n == 1 else f" There are {n} similar open reports nearby.")
    rev = " A 311 staff member will double-check the category." if review else ""
    return f"Filed: {cls['type_name']}{where}, sent to {cls['department']} ({cls['queue']}).{eta}{dup}{rev}"


def step(session_id: str | None, message: str, use_llm: bool | None = None) -> dict:
    sid = session_id or db.new_id("sess")
    state = db.get_session(sid) or {"text": None, "clarification": None, "awaiting": None, "followups": 0, "done": False}
    if state.get("done"):
        state = {"text": None, "clarification": None, "awaiting": None, "followups": 0, "done": False}
    out = {}

    def policy(t: Tracer, msg: str) -> str:
        if state["awaiting"] == "clarify":
            state["clarification"] = msg
        elif state["awaiting"] == "location":
            # the location answer often says more about the problem too ("the streetlight on the pole outside 20 Adams St")
            state["location_reply"] = msg
            state["clarification"] = f"{state.get('clarification') or ''} {msg}".strip()
        else:
            state["text"] = msg
        cls = t.call("classify", text=state["text"], clarification=state.get("clarification"))
        if state.get("location_reply"):
            g = t.call("geocode", place=state["location_reply"])
            if g.get("found"):
                from intake.classify import classify
                cls = classify(state["text"], clarification=state.get("clarification"),
                               location={"lat": g["lat"], "lon": g["lon"]}, clarify=False)
                cls["location_text"] = state["location_reply"]
                cls["location"] = {**(cls.get("location") or {}), "display": g.get("display")}
        out["classification"] = cls
        if cls["status"] in ("emergency", "refused"):
            state["done"] = True
            return cls["message"]
        if cls["status"] == "clarify" and state["followups"] < MAX_FOLLOWUPS and not state.get("clarification"):
            state.update(awaiting="clarify", followups=state["followups"] + 1)
            return cls["question"]
        if not cls.get("location") and state["followups"] < MAX_FOLLOWUPS and not state.get("location_reply"):
            state.update(awaiting="location", followups=state["followups"] + 1)
            return f"Got it: {cls['type_name']}. Where is it? A street address or the nearest intersection works."
        low = (cls.get("confidence") or 0) < llm.settings()["clarify_threshold"]
        return _file(t, state, cls, review=low)

    res = run_agent("intake", SYSTEM, TOOLS, message, scripted=policy, use_llm=False)
    db.save_session(sid, state)
    return {"session_id": sid, "reply": res["answer"], "done": state.get("done", False), "run_id": res["run_id"],
            "classification": out.get("classification"), "filed": state.get("filed"), "followups": state["followups"]}
