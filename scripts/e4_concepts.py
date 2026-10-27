"""E4: which SAM 3.1 text prompt finds roads / buildings best?

Runs several candidate concepts on the same images (in parallel), prints a
count table and saves one overlay per image+concept for visual review:
outputs/e4/<image>__<concept>.png

    python scripts/e4_concepts.py --limit 6
    python scripts/e4_concepts.py samples/ladi/a.jpg --concepts road street
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common import OUTPUTS_DIR, meta_client, pick_images

_spec = importlib.util.spec_from_file_location("sam01", Path(__file__).parent / "01_test_sam.py")
sam = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sam)

CANDIDATES = ["road", "street", "flooded road", "paved road", "building", "house", "damaged building"]


def run_one(client, image_path: Path, concept: str) -> dict:
    started = time.perf_counter()
    text = sam.segment(client, image_path, concept)
    records, _ = sam.parse_sam_output(text)
    objects = sam.objects_from_records(records, concept)
    for n, obj in enumerate(objects, start=1):
        obj["id"] = n
    target = OUTPUTS_DIR / "e4" / f"{image_path.stem}__{concept.replace(' ', '_')}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    sam.render(image_path, objects, target)
    confs = [o["confidence"] for o in objects if o["confidence"] is not None]
    return {
        "image": image_path.name,
        "concept": concept,
        "count": len(objects),
        "mean_conf": round(sum(confs) / len(confs), 2) if confs else None,
        "seconds": round(time.perf_counter() - started, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*")
    ap.add_argument("--concepts", nargs="+", default=CANDIDATES)
    ap.add_argument("--limit", type=int, default=6)
    args = ap.parse_args()

    client = meta_client()
    images = pick_images(args.images, args.limit)
    jobs = [(img, c) for img in images for c in args.concepts]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda job: run_one(client, *job), jobs))

    print(f"{'image':<32}" + "".join(f"{c[:14]:>16}" for c in args.concepts))
    for img in images:
        row = {r["concept"]: r for r in results if r["image"] == img.name}
        cells = "".join(
            f"{row[c]['count']:>9} ({row[c]['mean_conf'] or 0:.2f})" for c in args.concepts
        )
        print(f"{img.name[:31]:<32}{cells}")
    out = OUTPUTS_DIR / "e4" / "results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\n-> {out}  (overlays in {out.parent})")


if __name__ == "__main__":
    main()
