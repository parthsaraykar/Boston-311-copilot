"""SQLite: intake log (scrubbed text only), agent traces, plan proposals, intake sessions."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("APP_DB", ROOT / "data" / "app.sqlite"))
_lock = threading.Lock()

SCHEMA = """
create table if not exists intake_log (
  id text primary key, ts real, text_scrubbed text, status text, category_id text, type text, dept_code text,
  department text, queue text, confidence real, language text, mode text, latency_ms integer,
  tokens integer, neighborhood text, lat real, lon real, filed integer default 0, review text default null,
  plan_month integer, source text
);
create table if not exists agent_runs (
  run_id text primary key, agent text, ts real, input text, answer text, status text, mode text,
  steps integer, tokens integer, latency_ms integer, sources text, grounded integer
);
create table if not exists agent_steps (
  run_id text, step integer, ts real, kind text, name text, input text, output text, tokens integer, latency_ms integer
);
create table if not exists proposals (
  id text primary key, ts real, created_by text, reason text, plan text, summary text, status text, decided_ts real
);
create table if not exists sessions (id text primary key, ts real, state text);
"""


@contextmanager
def conn():
    with _lock:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        c.executescript(SCHEMA)
        try:
            yield c
            c.commit()
        finally:
            c.close()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def log_intake(result: dict, filed: bool = False, plan_month: int | None = None, source: str = "web") -> str:
    """Only the scrubbed text is stored, never the raw message."""
    rid = new_id("req")
    loc = result.get("location") or {}
    with conn() as c:
        c.execute("insert into intake_log values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            rid, time.time(), result.get("text_scrubbed"), result.get("status"), result.get("category_id"),
            result.get("type"), result.get("dept_code"), result.get("department"), result.get("queue"),
            result.get("confidence"), result.get("language"), result.get("mode"), result.get("latency_ms"),
            (result.get("tokens_in") or 0) + (result.get("tokens_out") or 0), loc.get("neighborhood"),
            loc.get("lat"), loc.get("lon"), int(filed), None, plan_month, source))
    return rid


def rows(sql: str, args: tuple = ()) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def execute(sql: str, args: tuple = ()) -> None:
    with conn() as c:
        c.execute(sql, args)


def start_run(agent: str, user_input: str, mode: str) -> str:
    rid = new_id("run")
    with conn() as c:
        c.execute("insert into agent_runs (run_id, agent, ts, input, status, mode, steps, tokens, latency_ms) "
                  "values (?,?,?,?,?,?,0,0,0)", (rid, agent, time.time(), user_input, "running", mode))
    return rid


def log_step(run_id: str, step: int, kind: str, name: str | None, inp, out, tokens: int = 0, latency_ms: int = 0):
    with conn() as c:
        c.execute("insert into agent_steps values (?,?,?,?,?,?,?,?,?)", (
            run_id, step, time.time(), kind, name, json.dumps(inp, default=str)[:20000],
            json.dumps(out, default=str)[:20000], tokens, latency_ms))


def finish_run(run_id: str, answer: str, status: str, steps: int, tokens: int, latency_ms: int,
               sources: list[str], grounded: bool | None, mode: str):
    with conn() as c:
        c.execute("update agent_runs set answer=?, status=?, steps=?, tokens=?, latency_ms=?, sources=?, grounded=?, mode=? "
                  "where run_id=?", (answer, status, steps, tokens, latency_ms, json.dumps(sources),
                                     None if grounded is None else int(grounded), mode, run_id))


def trace(run_id: str) -> dict:
    run = rows("select * from agent_runs where run_id=?", (run_id,))
    steps = rows("select * from agent_steps where run_id=? order by step, ts", (run_id,))
    for s in steps:
        for k in ("input", "output"):
            try:
                s[k] = json.loads(s[k])
            except Exception:
                pass
    return {"run": run[0] if run else None, "steps": steps}


def get_session(sid: str) -> dict | None:
    r = rows("select state from sessions where id=?", (sid,))
    return json.loads(r[0]["state"]) if r else None


def save_session(sid: str, state: dict):
    with conn() as c:
        c.execute("insert or replace into sessions values (?,?,?)", (sid, time.time(), json.dumps(state, default=str)))
