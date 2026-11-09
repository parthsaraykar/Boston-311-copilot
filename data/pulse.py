"""City Pulse layers: on-time rate and open backlog per neighborhood (spatial join of every case onto the
official neighborhood boundaries), and a grid of currently open requests.

Run: python -m data.pulse  -> data/processed/pulse_neighborhoods.geojson, pulse_grid.json
"""
import json
from pathlib import Path

import duckdb
import numpy as np
import shapely
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "processed"
DEPT = {"PWDx": "Public Works", "BTDT": "Transportation", "PARK": "Parks", "ISD": "Inspectional Services"}
CELL = 0.004  # degrees, about 330 m north-south


def build() -> None:
    gj = json.loads((ROOT / "neighborhoods.geojson").read_text())
    feats = [f for f in gj["features"] if f["properties"]["name"] != "Harbor Islands"]
    polys = [shape(f["geometry"]) for f in feats]
    names = [f["properties"]["name"] for f in feats]
    con = duckdb.connect(str(OUT / "311.duckdb"), read_only=True)
    cases = con.execute("""
        select lon, lat, on_time::int as on_time, dept_code, is_closed::int as closed,
               open_dt >= (select max(open_dt) from cases) - interval 180 day as recent
        from cases
        where lat between 42.2 and 42.45 and lon between -71.2 and -70.95 and open_dt >= timestamp '2023-01-01'
    """).df()
    con.close()

    # point-in-polygon for ~900k cases, vectorised
    idx = np.full(len(cases), -1)
    xs, ys = cases["lon"].to_numpy(), cases["lat"].to_numpy()
    for i, p in enumerate(polys):
        shapely.prepare(p)
        inside = shapely.contains_xy(p, xs, ys)
        idx[(idx == -1) & inside] = i
    cases["nb"] = idx
    cases = cases[cases["nb"] >= 0]

    out_feats = []
    for i, (f, p) in enumerate(zip(feats, polys)):
        g = cases[cases["nb"] == i]
        if g.empty:
            continue
        by_dept = {}
        for code, d in DEPT.items():
            gd = g[g["dept_code"] == code]
            if len(gd):
                by_dept[d] = {"requests": int(len(gd)), "on_time": round(float(gd["on_time"].mean()), 4)}
        open_recent = g[(g["closed"] == 0) & g["recent"]]
        out_feats.append({
            "type": "Feature",
            "geometry": mapping(p.simplify(0.0002, preserve_topology=True)),
            "properties": {
                "name": names[i], "requests": int(len(g)), "on_time": round(float(g["on_time"].mean()), 4),
                "open_now": int(len(open_recent)), "by_dept": by_dept,
                "per_sq_mile": round(len(g) / max(f["properties"].get("sqmiles") or 1, 0.05)),
            },
        })
    (OUT / "pulse_neighborhoods.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": out_feats}))

    # grid of requests that are open right now (opened in the last 180 days of the data, not closed)
    op = cases[(cases["closed"] == 0) & cases["recent"]].copy()
    op["gx"] = np.floor(op["lon"] / CELL).astype(int)
    op["gy"] = np.floor(op["lat"] / CELL).astype(int)
    grid = []
    for (gx, gy), g in op.groupby(["gx", "gy"]):
        counts = g["dept_code"].value_counts()
        top = counts.index[0]
        grid.append({"lat": round((gy + 0.5) * CELL, 5), "lon": round((gx + 0.5) * CELL, 5), "n": int(len(g)),
                     "top_dept": DEPT.get(top, "Other"),
                     "by_dept": {DEPT.get(k, "Other"): int(v) for k, v in counts.items()}})
    (OUT / "pulse_grid.json").write_text(json.dumps(grid))
    print(f"{len(out_feats)} neighborhoods, {len(grid)} grid cells, {len(op):,} open requests")


if __name__ == "__main__":
    build()
