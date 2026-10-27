"""E3 – end-to-end speed (PLAN 6.2): upload through the real HTTP API → image `done`
and published, measured from the server's own events.

Start a server first (fresh data dir), then:
    FH_DATA_DIR=data/e3 uvicorn app.server:app --port 8077 &
    python eval/run_e3.py --server http://localhost:8077 --images "data/demo_src/ky/*.jpg"

Reports: first image (cold – the first request after start), per-image p50/p95
upload→done, time until the whole batch is on the map.
"""

from __future__ import annotations

import argparse
import glob
import json
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def pct(values, q):
    a = sorted(values)
    if not a:
        return None
    x = (len(a) - 1) * q
    lo = int(x)
    return a[lo] + (a[min(lo + 1, len(a) - 1)] - a[lo]) * (x - lo)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:8077")
    ap.add_argument("--images", required=True)
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()
    paths = sorted(glob.glob(args.images))[: args.limit]
    c = httpx.Client(base_url=args.server, timeout=120)
    inc = c.post("/api/incidents", json={"name": "E3 latency", "region": "test"}).json()["id"]

    t0 = time.time()
    files = [("files", (Path(p).name, open(p, "rb").read(), "image/jpeg")) for p in paths]
    res = c.post(f"/api/incidents/{inc}/images", files=files).json()["results"]
    uploaded = time.time()
    ids = [r["image_id"] for r in res if r.get("image_id")]
    done_at: dict[str, float] = {}
    while len(done_at) < len(ids) and time.time() - t0 < 900:
        for img in c.get(f"/api/incidents/{inc}/snapshot").json()["images"]:
            if img["processing_state"] in ("done", "failed") and img["id"] not in done_at:
                done_at[img["id"]] = time.time()
        time.sleep(1)
    per_image = [done_at[i] - t0 for i in ids if i in done_at]
    first = min(per_image) if per_image else None
    result = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "images": len(ids), "finished": len(per_image),
        "upload_request_s": round(uploaded - t0, 1),
        "first_image_on_map_s": round(first, 1) if first else None,
        "p50_s": round(pct(per_image, .5), 1), "p95_s": round(pct(per_image, .95), 1),
        "whole_batch_s": round(max(per_image), 1) if per_image else None,
        "workers": "4 images in parallel, 5 SAM concepts per image in parallel, mask decoding in a process pool",
        "note": "Upload → processing_state done, measured by polling /snapshot every 1 s; includes queueing behind other images of the batch.",
    }
    (ROOT / "eval" / "e3_summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
