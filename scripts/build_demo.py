"""Build a read-only demo scenario (PLAN 5.4, 9): historical incident with a fixed
`as_of`, photos processed by the real pipeline, optional pins, then one agent run.

    python scripts/build_demo.py --name "Vermont floods, July 2023 (replay)" \
        --region "Vermont, USA" --images "data/eval/images/*.jpg" --event VT_Flooding --limit 30

    # Jablanica (when licensed photos are in samples/jablanica/ with pins.csv: file,lat,lon,author,license,source)
    python scripts/build_demo.py --name "Jablanica, 4 Oct 2024 (replay)" --region "Jablanica, Bosnia and Herzegovina" \
        --images "samples/jablanica/*.jpg" --pins samples/jablanica/pins.csv --as-of 2024-10-04T12:00:00

`--as-of auto` = one hour after the newest EXIF capture time, so the photos are
"fresh" relative to the scenario, as they were for responders that day.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import glob
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app.agent import Agent, meta_caller  # noqa: E402
from app.api import ModelApi  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.pipeline import Pipeline, read_metadata  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def pick(pattern: str, event: str | None, limit: int) -> list[Path]:
    paths = sorted(Path(p) for p in glob.glob(pattern))
    if event:
        # eval images are named by hash – match the event via the LADI manifests
        wanted = set()
        for manifest in (ROOT / "eval/test_set.csv", ROOT / "eval/tuning_set.csv", ROOT / "samples/ladi_dev_set.csv"):
            if manifest.exists():
                import hashlib
                for row in csv.DictReader(manifest.open(encoding="utf-8-sig")):
                    if event in row["url"]:
                        wanted.add(hashlib.sha256(row["url"].encode()).hexdigest()[:24])
        paths = [p for p in paths if p.stem in wanted or event.lower().split("_")[0] in p.stem.lower()]
    return paths[:limit] if limit else paths


def auto_as_of(paths: list[Path]) -> str | None:
    times = [read_metadata(Image.open(p)).captured_at for p in paths]
    times = [datetime.fromisoformat(t) for t in times if t]
    return (max(times) + timedelta(hours=1)).isoformat(timespec="seconds") if times else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--region")
    ap.add_argument("--images", required=True)
    ap.add_argument("--event", help="substring of the LADI event, e.g. VT_Flooding")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--pins", help="CSV with file,lat,lon[,uncertainty_m,note,author,license,source] – "
                    "pins photos without GPS and records each photo's credit")
    ap.add_argument("--credit", help="credit line for every photo (e.g. the LADI dataset), if the CSV has none")
    ap.add_argument("--as-of", default="auto")
    ap.add_argument("--mode", default="demo_readonly", choices=["demo_readonly", "dev"])
    ap.add_argument("--no-agent", action="store_true")
    args = ap.parse_args()

    paths = pick(args.images, args.event, args.limit)
    if not paths:
        sys.exit("no images matched")
    as_of = auto_as_of(paths) if args.as_of == "auto" else args.as_of
    db = Database(settings.db_path)
    api = ModelApi(settings, os.environ.get("MODEL_API_KEY"), os.environ.get("BASETEN_API_KEY"))
    pipe = Pipeline(db, settings, api)
    incident = db.create_incident(args.name, args.region, args.mode, as_of)
    print(f"incident {incident} as_of={as_of} images={len(paths)}")

    ids = {}
    for p in paths:
        image_id = pipe.ingest(incident, p.read_bytes(), p.name)
        if image_id:
            ids[p.name] = image_id
    asyncio.run(pipe.run_queue(incident))

    rows = list(csv.DictReader(open(args.pins, encoding="utf-8-sig"))) if args.pins else []
    by_file = {r["file"]: r for r in rows}
    for name, image_id in ids.items():
        row = by_file.get(name, {})
        credit = (f"{row['author']} · {row['license']} · {row['source']}" if row.get("author") else args.credit)
        if credit:
            db.update_image(image_id, None, credit=credit)
        if row.get("lat"):
            pipe.set_pin(image_id, float(row["lat"]), float(row["lon"]),
                         float(row.get("uncertainty_m") or 50), row.get("note") or "placed by responder")

    states = db.query("SELECT processing_state, location_state, published FROM images WHERE incident_id = ?", (incident,))
    print("done:", sum(r["processing_state"] == "done" for r in states), "published:", sum(r["published"] for r in states),
          "needs pin:", sum(r["location_state"] == "needs_pin" for r in states))
    if not args.no_agent:
        run_id = Agent(db, meta_caller(api.meta, settings.meta_assess_model)).run(incident)
        print("agent run", run_id, dict(db.one("SELECT status, steps, error FROM agent_runs WHERE id = ?", (run_id,))))
    print(f"open: http://localhost:8000/?incident={incident}")


if __name__ == "__main__":
    main()
