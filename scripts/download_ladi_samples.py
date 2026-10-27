"""Download the LADI v2 dev set listed in samples/ladi_dev_set.csv.

LADI v2 = Civil Air Patrol aerial photos from US disasters (MIT Lincoln Lab),
CC BY 4.0. The CSV has 25 hand-picked test images with their human labels:
  16 x Vermont flooding Jul 2023 (river valley floods, closest to BiH terrain)
   6 x Arkansas storms Apr 2023 (destroyed / major building damage)
   3 x California storms Jan 2023 (flooding)
The labels (flooding_any, buildings_major, roads_damage, ...) are what we
compare our pipeline against in the eval.

Originals are 5-15 MB; we save a copy resized to max 1600 px (EXIF incl. GPS
kept), which is plenty for SAM / Muse Spark and much cheaper and faster.

    python scripts/download_ladi_samples.py
    python scripts/download_ladi_samples.py --limit 5

Attribution: "LADI v2, MIT Lincoln Laboratory / Civil Air Patrol, CC BY 4.0"
"""

from __future__ import annotations

import argparse
import csv
import io
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "samples" / "ladi_dev_set.csv"
TARGET = ROOT / "samples" / "ladi"
MAX_SIDE = 1600

SHORT = {
    "CAP_-_VT_Flooding_Jul_2023": "vt-flood",
    "CAP_-_AR_Storms_APR_2023": "ar-storm",
    "CAP_-_CA_Storms_Jan_2023": "ca-storm",
}


def local_name(row: dict) -> str:
    event = SHORT.get(row["event"], row["event"])
    return f"{event}_{Path(row['url']).stem}.jpg"


def save_resized(data: bytes, target: Path) -> tuple[int, int]:
    image = Image.open(io.BytesIO(data))
    exif = image.info.get("exif")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    kwargs = {"quality": 90}
    if exif:
        kwargs["exif"] = exif
    image.convert("RGB").save(target, "JPEG", **kwargs)
    return image.size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = list(csv.DictReader(LIST.open(encoding="utf-8")))
    if args.limit:
        rows = rows[: args.limit]
    TARGET.mkdir(parents=True, exist_ok=True)

    labels_out = TARGET / "labels.csv"
    with labels_out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["file", *rows[0].keys()])
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            name = local_name(row)
            target = TARGET / name
            writer.writerow({"file": name, **row})
            if target.exists():
                print(f"[{i}/{len(rows)}] {name} (already there)")
                continue
            print(f"[{i}/{len(rows)}] {name} ...", end=" ", flush=True)
            try:
                with urllib.request.urlopen(row["url"], timeout=120) as response:
                    data = response.read()
                size = save_resized(data, target)
                print(f"{len(data) / 1e6:.1f} MB -> {size[0]}x{size[1]}")
            except Exception as exc:  # keep going if one image fails
                print(f"FAILED: {exc}")
    print(f"\nImages + labels.csv in {TARGET}")


if __name__ == "__main__":
    main()
