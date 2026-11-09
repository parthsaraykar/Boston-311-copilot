"""Category cards and routing tables, loaded once."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

DEPT_NAMES = {"PWDx": "Public Works", "BTDT": "Transportation", "PARK": "Parks", "ISD": "Inspectional Services",
              "INFO": "311 / Other agencies", "GEN": "General Services", "BWSC": "Boston Water and Sewer",
              "PROP": "Property Management"}


@lru_cache(maxsize=1)
def combos() -> pd.DataFrame:
    """The 170 type / department / queue combinations."""
    return pd.read_parquet(PROCESSED / "catalog.parquet")


@lru_cache(maxsize=1)
def cards() -> list[dict]:
    """One card per request type, with its possible (department, queue) routes."""
    src = yaml.safe_load((ROOT / "intake" / "cards_source.yaml").read_text())
    c = combos()
    out = []
    for type_, g in c.groupby("type", sort=False):
        info = src.get(type_, {})
        routes = [{"dept_code": r.dept_code, "department": DEPT_NAMES.get(r.dept_code, r.dept), "queue": r.queue,
                   "combo_id": int(r.id), "monthly_volume": float(r.monthly_volume),
                   "median_days_to_close": float(r.median_days_to_close) if pd.notna(r.median_days_to_close) else None,
                   "on_time_rate": float(r.on_time_rate)}
                  for r in g.sort_values("volume_3y", ascending=False).itertuples()]
        out.append({
            "id": f"C{len(out) + 1:02d}", "type": type_, "name": info.get("name", type_),
            "description": info.get("desc", type_), "examples": info.get("ex", []),
            "monthly_volume": round(float(g["monthly_volume"].sum()), 1), "routes": routes,
            "main_department": routes[0]["department"],
        })
    out.sort(key=lambda x: -x["monthly_volume"])
    for i, card in enumerate(out):
        card["id"] = f"C{i + 1:02d}"
    return out


@lru_cache(maxsize=1)
def cards_by_id() -> dict[str, dict]:
    return {c["id"]: c for c in cards()}


@lru_cache(maxsize=1)
def cards_by_type() -> dict[str, dict]:
    return {c["type"]: c for c in cards()}


@lru_cache(maxsize=1)
def type_area() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "type_area.parquet")


def card_text(card: dict) -> str:
    return f"{card['name']}. {card['description']} " + " ".join(card["examples"])


def resolve_route(card: dict, neighborhood: str | None) -> tuple[dict, float]:
    """Pick the department/queue for a type from where it is. Returns (route, share of history it covers)."""
    routes = card["routes"]
    if len(routes) == 1:
        return routes[0], 1.0
    if neighborhood:
        ta = type_area()
        g = ta[(ta["type"] == card["type"]) & (ta["neighborhood"] == neighborhood)]
        if len(g):
            best = g.sort_values("n", ascending=False).iloc[0]
            share = float(best["n"] / g["n"].sum())
            for r in routes:
                if r["queue"] == best["queue"] and r["dept_code"] == best["dept_code"]:
                    return r, share
    total = sum(r["monthly_volume"] for r in routes)
    return routes[0], routes[0]["monthly_volume"] / total
