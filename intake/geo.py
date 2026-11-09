"""Location: pull a place from the message, geocode it (Nominatim, cached), find neighborhood and nearby open reports."""
from __future__ import annotations

import json
import math
import re
import threading
import time
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
CACHE_FILE = ROOT / "data" / "geocode_cache.json"
_lock = threading.Lock()
_last_call = [0.0]

STREET_SUFFIX = r"(?:st|street|ave|avenue|rd|road|blvd|boulevard|pl|place|sq|square|ct|court|ter|terrace|way|pkwy|parkway|dr|drive|ln|lane|hwy|park|playground|station|stop)\b\.?"
LOC_PATTERNS = [
    r"\b(corner of [\w .'-]+? and [\w .'-]+? " + STREET_SUFFIX + ")",
    r"\b(\d{1,5}\s+[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,3}\s+" + STREET_SUFFIX + ")",
    r"\b(?:near|at|on|by|outside|in front of|across from|next to|behind|cerca de|en la|en el|perto de|na rua|bò|nan|gần)\s+(?:the\s+)?([A-Z0-9][\w'.-]*(?:\s+(?:[A-Z0-9][\w'.-]*|of|and|&))*(?:\s+" + STREET_SUFFIX + r")?(?:\s+T\s+stop|\s+T\s+station)?)",
]


@lru_cache(maxsize=1)
def neighborhoods() -> list[str]:
    g = pd.read_parquet(PROCESSED / "geo_points.parquet")
    return sorted(g["neighborhood"].dropna().unique().tolist(), key=len, reverse=True)


@lru_cache(maxsize=1)
def _points():
    g = pd.read_parquet(PROCESSED / "geo_points.parquet").dropna(subset=["lat", "lon"])
    return g, np.radians(g[["lat", "lon"]].to_numpy())


@lru_cache(maxsize=1)
def neighborhood_centroids() -> dict[str, tuple[float, float]]:
    g, _ = _points()
    c = g.groupby("neighborhood")[["lat", "lon"]].median()
    return {n: (float(r.lat), float(r.lon)) for n, r in c.iterrows()}


def extract_location(text: str) -> str | None:
    for p in LOC_PATTERNS:
        m = re.search(p, text, flags=0 if "[A-Z" in p else re.IGNORECASE)
        if m:
            loc = m.group(1).strip(" .,")
            if len(loc) >= 4:
                return loc
    for n in neighborhoods():
        for part in n.split(" / "):
            if re.search(rf"\b{re.escape(part)}\b", text, flags=re.IGNORECASE):
                return part
    return None


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}


def geocode(place: str, timeout: float = 4.0) -> dict | None:
    """Returns {lat, lon, display} or None. Bounded to Boston; obeys Nominatim's 1 request/second rule."""
    key = place.strip().lower()
    with _lock:
        cache = _load_cache()
        if key in cache:
            return cache[key]
    # a bare neighborhood name: use its centroid, no network needed
    for n, (lat, lon) in neighborhood_centroids().items():
        if key in [p.lower() for p in n.split(" / ")] or key == n.lower():
            return {"lat": lat, "lon": lon, "display": n, "source": "neighborhood"}
    out = None
    for q in _query_variants(place):
        out = _nominatim(q, timeout)
        if out:
            break
    if not out:  # fall back to a neighborhood named in the text
        for n in neighborhoods():
            for part in n.split(" / "):
                if re.search(rf"\b{re.escape(part)}\b", place, flags=re.IGNORECASE):
                    lat, lon = neighborhood_centroids()[n]
                    out = {"lat": lat, "lon": lon, "display": n, "source": "neighborhood"}
                    break
            if out:
                break
    with _lock:
        cache = _load_cache()
        cache[key] = out
        CACHE_FILE.write_text(json.dumps(cache, indent=1))
    return out


def _query_variants(place: str) -> list[str]:
    q = re.sub(r"\bT (stop|station)\b", "station", place, flags=re.IGNORECASE)
    q = re.sub(r"^(the )?(corner|intersection) of\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+in\s+(" + "|".join(re.escape(p) for n in neighborhoods() for p in n.split(" / ")) + r")\s*$", "", q,
               flags=re.IGNORECASE)
    variants = [q]
    if re.search(r"\s(and|&)\s", q):
        a, b = re.split(r"\s(?:and|&)\s", q, maxsplit=1)
        variants += [f"{a.strip()} & {b.strip()}", a.strip()]
    if q != place:
        variants.append(place)
    return list(dict.fromkeys(v for v in variants if v))


def _nominatim(q: str, timeout: float) -> dict | None:
    try:
        with _lock:
            wait = 1.05 - (time.time() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.time()
        r = httpx.get("https://nominatim.openstreetmap.org/search",
                      params={"q": f"{q}, Boston, MA", "format": "json", "limit": 1,
                              "viewbox": "-71.20,42.42,-70.98,42.22", "bounded": 1},
                      headers={"User-Agent": "boston-311-copilot/0.1 (hackathon demo)"}, timeout=timeout)
        hits = r.json()
        return {"lat": float(hits[0]["lat"]), "lon": float(hits[0]["lon"]),
                "display": hits[0]["display_name"], "source": "nominatim"} if hits else None
    except Exception:
        return None


def locate(lat: float, lon: float) -> dict:
    """Nearest historical case point -> neighborhood and PWD district."""
    g, rad = _points()
    p = np.radians([lat, lon])
    d = np.sin((rad[:, 0] - p[0]) / 2) ** 2 + np.cos(p[0]) * np.cos(rad[:, 0]) * np.sin((rad[:, 1] - p[1]) / 2) ** 2
    i = int(np.argmin(d))
    dist_m = 2 * 6371000 * math.asin(math.sqrt(d[i]))
    row = g.iloc[i]
    return {"neighborhood": row["neighborhood"], "pwd_district": row["pwd_district"], "nearest_m": round(dist_m)}


@lru_cache(maxsize=1)
def _open_cases() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "open_cases.parquet")


def find_duplicates(type_: str, lat: float, lon: float, radius_m: float = 200, limit: int = 3) -> list[dict]:
    oc = _open_cases()
    g = oc[oc["type"] == type_]
    if g.empty:
        return []
    dlat = np.radians(g["lat"].to_numpy() - lat)
    dlon = np.radians(g["lon"].to_numpy() - lon)
    a = np.sin(dlat / 2) ** 2 + np.cos(math.radians(lat)) * np.cos(np.radians(g["lat"].to_numpy())) * np.sin(dlon / 2) ** 2
    dist = 2 * 6371000 * np.arcsin(np.sqrt(a))
    g = g.assign(dist=dist)
    g = g[g["dist"] <= radius_m].sort_values("dist").head(limit)
    return [{"case_id": r.case_id, "type": r.type, "opened": str(r.open_dt)[:10], "distance_m": round(r.dist),
             "location": (r.location or "").replace("&amp;", "&"), "lat": r.lat, "lon": r.lon} for r in g.itertuples()]
