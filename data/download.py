"""Download the yearly Boston 311 CSVs from Analyze Boston (data.boston.gov). Run: python -m data.download"""
from pathlib import Path

import httpx

RAW = Path(__file__).resolve().parent / "raw"
BASE = "https://data.boston.gov/dataset/8048697b-ad64-4bfc-b090-ee00169f2323/resource"
FILES = {
    2022: "81a7b022-f8fc-4da5-80e4-b160058ca207/download/lagan_311_open_data_2022_rvsd3.csv",
    2023: "e6013a93-1321-4f2a-bf91-8d8a02f1e62f/download/lagan_311_open_data_2023_rvsd3.csv",
    2024: "dff4d804-5031-443a-8409-8344efd0e5c8/download/lagan_311_open_data_2024_rvsd3.csv",
    2025: "9d7c2214-4709-478a-a2e8-fb2020a5bb94/download/lagan_311_open_data_2025_rvsd3.csv",
}

if __name__ == "__main__":
    RAW.mkdir(exist_ok=True)
    for year, path in FILES.items():
        out = RAW / f"311_{year}.csv"
        if out.exists() and out.stat().st_size > 1e7:
            print(f"{out.name} already here")
            continue
        print(f"downloading {year} ...")
        with httpx.stream("GET", f"{BASE}/{path}", follow_redirects=True, timeout=600) as r, out.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
        print(f"  {out.stat().st_size / 1e6:.0f} MB")
