"""Run every scripted demo input through the local LLM once, so the demo answers instantly from the cache."""
from fastapi.testclient import TestClient

from api.main import app

DEMO_INPUTS = [
    "big hole near the Jackson Sq T stop, almost blew a tire",
    "Hay un bache enorme en la calle Centre cerca de Hyde Square",
    "downed wire sparking on Washington St",
    "rats running around the alley behind 45 Dudley St",
    "car parked on the sidewalk on Boylston St",
    "Gen yon gwo twou nan lari a sou Blue Hill Ave",
    "我家门口的路灯坏了，晚上很黑",
]

if __name__ == "__main__":
    c = TestClient(app)
    for t in DEMO_INPUTS:
        r = c.post("/intake/classify", json={"text": t, "mode": "cached", "file": False}).json()
        print(f"{r['status']:9s} {r.get('type_name') or r.get('message', '')[:40]:40s} {r.get('mode')} {r['latency_ms']} ms  <- {t}")
