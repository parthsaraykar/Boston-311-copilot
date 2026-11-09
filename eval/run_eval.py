"""Score the intake assistant on the labelled test set.

python -m eval.run_eval --mode retrieval   (no LLM, fast)
python -m eval.run_eval --mode llm         (Ollama; slow on CPU)
Writes eval/results_<mode>.jsonl and merges metrics into eval/eval.json (what the app shows).
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from intake import retrieve
from intake.catalog import cards_by_type, resolve_route
from intake.classify import classify

HERE = Path(__file__).parent
ROOT = HERE.parent


def load_testset() -> list[dict]:
    return [json.loads(line) for line in (HERE / "testset.jsonl").read_text().splitlines() if line.strip()]


def ok_type(row, pred_type) -> bool:
    return pred_type is not None and (pred_type == row["type"] or pred_type in row.get("also_ok", []))


def run_one(row: dict, use_llm: bool) -> dict:
    t0 = time.time()
    first = classify(row["text"], use_llm=use_llm)
    final = first
    if first["status"] == "clarify" and row.get("reply"):
        final = classify(row["text"], clarification=row["reply"], use_llm=use_llm)
    hits = retrieve.search(row["text"], k=10)
    base = retrieve.tfidf_baseline(row["text"])
    return {
        "id": row["id"], "slice": row["slice"], "language": row["language"], "expect": row["expect"],
        "label_type": row.get("type"), "label_dept": row.get("dept"),
        "first_status": first["status"], "status": final["status"],
        "pred_type": final.get("type"), "pred_dept": final.get("dept_code"), "queue": final.get("queue"),
        "first_type": first.get("type"),
        "confidence": final.get("confidence"), "first_confidence": first.get("confidence"),
        "top10_types": [h["card"]["type"] for h in hits],
        "baseline_type": base["type"], "mode": final.get("mode"),
        "tokens_in": first.get("tokens_in", 0) + (final.get("tokens_in", 0) if final is not first else 0),
        "tokens_out": first.get("tokens_out", 0) + (final.get("tokens_out", 0) if final is not first else 0),
        "latency_ms": round((time.time() - t0) * 1000), "clf_latency_ms": first.get("latency_ms"),
        "located": bool(final.get("location")), "reason": final.get("reason"),
    }


def queue_accuracy_on_history(n: int = 400, seed: int = 3) -> dict:
    """The queue comes from location. Test that stage on real 2025 cases: given the true type and the case's
    lat/lon, do we pick the queue the city actually used?"""
    from intake import geo
    import duckdb

    con = duckdb.connect(str(ROOT / "data" / "processed" / "311.duckdb"), read_only=True)
    types = list(cards_by_type())
    df = con.execute(f"""
        select type, dept_code, queue, lat, lon from cases
        where year(open_dt) = 2025 and lat is not null and lat between 42.2 and 42.45
          and type in ({",".join("?" * len(types))})
        using sample {n * 3} rows (reservoir, {seed})
    """, types).df().head(n)
    con.close()
    right_q = right_d = 0
    multi = multi_right = 0
    for r in df.itertuples():
        card = cards_by_type()[r.type]
        place = geo.locate(r.lat, r.lon)
        route, _ = resolve_route(card, place["neighborhood"])
        right_q += route["queue"] == r.queue
        right_d += route["dept_code"] == r.dept_code
        if len(card["routes"]) > 1:
            multi += 1
            multi_right += route["queue"] == r.queue
    return {"cases": len(df), "queue_accuracy": round(right_q / len(df), 4), "dept_accuracy": round(right_d / len(df), 4),
            "multi_queue_types_cases": multi, "multi_queue_accuracy": round(multi_right / multi, 4) if multi else None,
            "note": "Real 2025 cases (some queues are outside the 170 catalog combos, which caps this score)."}


def leakage(rows: list[dict]) -> dict[str, float]:
    """Max similarity between each test message and any card example phrasing (same author wrote both)."""
    from intake.catalog import cards
    examples = [e for c in cards() for e in c["examples"]]
    enc = retrieve._encoder()
    if enc is None:
        return {}
    E = enc.encode(examples, normalize_embeddings=True)
    T = enc.encode([r["text"] for r in rows], normalize_embeddings=True)
    sims = (T @ E.T).max(axis=1)
    return {r["id"]: float(s) for r, s in zip(rows, sims)}


def metrics(res: list[dict], leak: dict | None = None) -> dict:
    df = pd.DataFrame(res)
    routed = df[df["expect"] == "routed"].copy()
    routed["type_ok"] = [ok_type({"type": r.label_type, "also_ok": r.also_ok}, r.pred_type) for r in routed.itertuples()]
    routed["type_strict"] = routed["pred_type"] == routed["label_type"]
    routed["dept_ok"] = routed["pred_dept"] == routed["label_dept"]
    routed["top10_hit"] = [r.label_type in r.top10_types or any(a in r.top10_types for a in r.also_ok)
                           for r in routed.itertuples()]
    routed["baseline_ok"] = [ok_type({"type": r.label_type, "also_ok": r.also_ok}, r.baseline_type)
                             for r in routed.itertuples()]
    routed["first_ok"] = [ok_type({"type": r.label_type, "also_ok": r.also_ok}, r.first_type) for r in routed.itertuples()]

    def acc(g):
        return {"n": int(len(g)), "type_accuracy": round(float(g["type_ok"].mean()), 4),
                "dept_accuracy": round(float(g["dept_ok"].mean()), 4),
                "type_strict": round(float(g["type_strict"].mean()), 4),
                "top10_hit_rate": round(float(g["top10_hit"].mean()), 4),
                "baseline_tfidf_type_accuracy": round(float(g["baseline_ok"].mean()), 4)}

    by_slice = {s: acc(g) for s, g in routed.groupby("slice")}
    by_lang = {l: acc(g) for l, g in routed.groupby("language")}
    by_dept = {d: acc(g) for d, g in routed.groupby("label_dept")}
    emerg = df[df["expect"] == "emergency"]
    guard = df[df["expect"] == "refused"]
    non_emerg = df[df["expect"] != "emergency"]
    amb = routed[routed["slice"] == "ambiguous"]
    confusion = defaultdict(Counter)
    for r in routed.itertuples():
        confusion[r.label_dept][r.pred_dept or "none"] += 1

    # human review queue: accuracy vs share auto-routed at each confidence cut-off (first pass, before follow-up)
    cut = []
    conf = routed["first_confidence"].fillna(0).to_numpy()
    for c in np.round(np.arange(0.0, 0.96, 0.05), 2):
        auto = conf >= c
        cut.append({"cutoff": float(c), "share_auto": round(float(auto.mean()), 4),
                    "accuracy_auto": round(float(routed["first_ok"][auto].mean()), 4) if auto.any() else None})

    leak_info = None
    if leak:
        routed["leak"] = routed["id"].map(leak)
        clean = routed[routed["leak"] < 0.85]
        leak_info = {"threshold": 0.85, "n_near_copies": int((routed["leak"] >= 0.85).sum()),
                     "type_accuracy_excluding_near_copies": round(float(clean["type_ok"].mean()), 4),
                     "n_clean": int(len(clean)),
                     "note": "Cards and test set were written by the same person; messages within 0.85 cosine of a card example are excluded here."}

    lat = df["latency_ms"].to_numpy()
    tok = (df["tokens_in"] + df["tokens_out"]).to_numpy()
    return {
        "n_messages": int(len(df)),
        "overall": acc(routed),
        "by_slice": by_slice, "by_language": by_lang, "by_department": by_dept,
        "emergency_recall": round(float((emerg["status"] == "emergency").mean()), 4),
        "emergency_n": int(len(emerg)),
        "false_emergency_rate": round(float((non_emerg["status"] == "emergency").mean()), 4),
        "guardrail_refusal_rate": round(float((guard["status"] == "refused").mean()), 4),
        "guardrail_n": int(len(guard)),
        "wrongly_refused_rate": round(float((routed["status"] == "refused").mean()), 4),
        "clarify_share": round(float((df["first_status"] == "clarify").mean()), 4),
        "ambiguous_first_pass_accuracy": round(float(amb["first_ok"].mean()), 4) if len(amb) else None,
        "ambiguous_after_followup_accuracy": round(float(amb["type_ok"].mean()), 4) if len(amb) else None,
        "located_share": round(float(routed["located"].mean()), 4),
        "latency_ms_p50": float(np.percentile(lat, 50)), "latency_ms_p95": float(np.percentile(lat, 95)),
        "tokens_per_request": round(float(tok.mean()), 1),
        "cost_per_request_usd": 0.0,
        "cost_note": "Runs on a local Ollama model, so there is no per-request API cost; the cost is the laptop/server CPU time shown as latency.",
        "leakage_check": leak_info,
        "confusion_by_department": {k: dict(v) for k, v in confusion.items()},
        "review_queue_curve": cut,
        "failures": [
            {"id": r.id, "slice": r.slice, "language": r.language, "label": r.label_type, "pred": r.pred_type,
             "status": r.status, "confidence": r.confidence}
            for r in routed.itertuples() if not r.type_ok
        ] + [{"id": r.id, "slice": r.slice, "language": r.language, "label": r.expect, "pred": r.pred_type,
              "status": r.status} for r in df[df["expect"] != "routed"].itertuples() if r.status != r.expect],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["retrieval", "llm"], default="retrieval")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    rows = load_testset()[: args.limit]
    use_llm = args.mode == "llm"
    labels = {r["id"]: r for r in rows}
    out_path = HERE / f"results_{args.mode}.jsonl"
    done = {}
    if out_path.exists():  # resume: the LLM run is slow, keep finished rows
        for line in out_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["id"]] = r
    with out_path.open("a") as f:
        for i, row in enumerate(rows):
            if row["id"] in done:
                continue
            r = run_one(row, use_llm)
            done[row["id"]] = r
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i + 1}/{len(rows)}] {row['id']} {row['slice']:12s} {r['status']:9s} {str(r['pred_type'])[:35]:35s} "
                  f"(label {row.get('type') or row['expect']}) {r['latency_ms']}ms", flush=True)
    res = [{**done[r["id"]], "also_ok": labels[r["id"]].get("also_ok", [])} for r in rows]
    m = metrics(res, leakage(rows))
    m["mode"] = args.mode
    eval_path = HERE / "eval.json"
    allm = json.loads(eval_path.read_text()) if eval_path.exists() else {}
    allm[args.mode] = m
    if "queue_from_location" not in allm:
        allm["queue_from_location"] = queue_accuracy_on_history()
    # the app shows whichever mode routes more accurately (on this laptop: retrieval beat the 3B LLM)
    allm["primary"] = max((k for k in ("retrieval", "llm") if k in allm), key=lambda k: allm[k]["overall"]["type_accuracy"])
    allm = json.loads(json.dumps(allm).replace("NaN", "null"))
    eval_path.write_text(json.dumps(allm, indent=1, ensure_ascii=False))
    (ROOT / "contracts" / "eval.json").write_text(json.dumps(allm, indent=1, ensure_ascii=False))
    o = m["overall"]
    print(f"\n{args.mode}: type {o['type_accuracy']:.1%}  dept {o['dept_accuracy']:.1%}  top10 {o['top10_hit_rate']:.1%}  "
          f"tfidf baseline {o['baseline_tfidf_type_accuracy']:.1%}  emergency recall {m['emergency_recall']:.0%}  "
          f"guardrails {m['guardrail_refusal_rate']:.0%}  clarify {m['clarify_share']:.0%}  p50 {m['latency_ms_p50']:.0f}ms")
    print("by language:", {k: v["type_accuracy"] for k, v in m["by_language"].items()})
    print("by slice:", {k: v["type_accuracy"] for k, v in m["by_slice"].items()})
    print("queue from location:", allm["queue_from_location"])


if __name__ == "__main__":
    main()
