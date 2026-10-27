"""Command line for the pipeline (before the web UI exists).

    python -m app.cli new "VT flood test" --region "Vermont, USA"
    python -m app.cli ingest <incident_id> samples/ladi/*.jpg
    python -m app.cli process [<incident_id>]
    python -m app.cli pin <image_id> 43.09 -72.45
    python -m app.cli status <incident_id>
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import time
from collections import Counter
from pathlib import Path

from .api import ModelApi
from .config import settings
from .db import Database
from .pipeline import Pipeline, RejectedImage


def build() -> Pipeline:
    db = Database(settings.db_path)
    api = ModelApi(settings, os.environ.get("MODEL_API_KEY"), os.environ.get("BASETEN_API_KEY"))
    return Pipeline(db, settings, api)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("name"); n.add_argument("--region")
    i = sub.add_parser("ingest"); i.add_argument("incident"); i.add_argument("paths", nargs="+")
    p = sub.add_parser("process"); p.add_argument("incident", nargs="?")
    pin = sub.add_parser("pin"); pin.add_argument("image"); pin.add_argument("lat", type=float); pin.add_argument("lon", type=float)
    st = sub.add_parser("status"); st.add_argument("incident")
    args = ap.parse_args()
    pipe = build()

    if args.cmd == "new":
        print(pipe.db.create_incident(args.name, args.region))
    elif args.cmd == "ingest":
        paths = [p for pattern in args.paths for p in (glob.glob(pattern) or [pattern])]
        for path in paths:
            try:
                image_id = pipe.ingest(args.incident, Path(path).read_bytes(), Path(path).name)
                print(f"{Path(path).name}: {image_id or 'duplicate, skipped'}")
            except RejectedImage as exc:
                print(f"{Path(path).name}: REJECTED – {exc}")
    elif args.cmd == "process":
        started = time.perf_counter()
        asyncio.run(pipe.run_queue(args.incident))
        print(f"done in {time.perf_counter() - started:.1f}s")
    elif args.cmd == "pin":
        pipe.set_pin(args.image, args.lat, args.lon)
        print("pinned")
    elif args.cmd == "status":
        rows = pipe.db.query("SELECT * FROM images WHERE incident_id = ? ORDER BY uploaded_at", (args.incident,))
        for r in rows:
            objs = pipe.db.one("SELECT COUNT(*) n FROM objects WHERE image_id = ?", (r["id"],))["n"]
            dmg = Counter(f["damage"] for f in pipe.db.query(
                "SELECT damage FROM findings WHERE image_id = ? AND object_id IS NOT NULL", (r["id"],)))
            print(f"{r['id']} {r['original_name'][:28]:<28} {r['processing_state']:<7} "
                  f"loc={r['location_state']:<9} seg={r['segmentation_state']:<10} pub={r['published']} "
                  f"objs={objs:<3} calls={r['api_calls_used']:<3} {dict(dmg)} {r['last_error'] or ''}")
        print(json.dumps(Counter(r["processing_state"] for r in rows)))


if __name__ == "__main__":
    main()
