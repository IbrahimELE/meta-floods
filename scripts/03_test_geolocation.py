"""Step 3: where was this photo taken?

Biggest technical risk of the project: citizen photos often have no GPS.
Strategy, cheapest first:
  1. EXIF GPS (phones usually write it; social-media re-uploads strip it)
  2. Muse Spark + server-side web_search tool: reads signs, landmarks, terrain
     and estimates a location inside the disaster region the responder gives
  3. (in the app) a manual pin by the responder

    python scripts/03_test_geolocation.py
    python scripts/03_test_geolocation.py samples/a.jpg --region "Jablanica, Bosnia and Herzegovina"
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from PIL import Image

from common import MUSE_SPARK, final_text, image_to_data_url, meta_client, out_path, pick_images

GPS_IFD = 0x8825

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["latitude", "longitude", "place_name", "precision", "clues_used", "confidence"],
    "properties": {
        "latitude": {"type": ["number", "null"]},
        "longitude": {"type": ["number", "null"]},
        "place_name": {"type": "string"},
        "precision": {
            "type": "string",
            "enum": ["building", "street", "neighborhood", "town", "region", "unknown"],
        },
        "clues_used": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
}


def exif_gps(path: Path) -> tuple[float, float] | None:
    try:
        gps = Image.open(path).getexif().get_ifd(GPS_IFD)
    except Exception:
        return None
    if not gps or 2 not in gps or 4 not in gps:
        return None

    def to_degrees(dms, ref) -> float:
        d, m, s = (float(x) for x in dms)
        value = d + m / 60 + s / 3600
        return -value if ref in ("S", "W") else value

    return to_degrees(gps[2], gps.get(1, "N")), to_degrees(gps[4], gps.get(3, "E"))


def estimate_location(client, path: Path, region: str | None) -> tuple[dict, object]:
    region_text = (
        f"The disaster area is: {region}. The photo was almost certainly taken there; "
        "narrow it down as far as the evidence allows."
        if region else "No region is known."
    )
    response = client.responses.create(
        model=MUSE_SPARK,
        instructions=(
            "Estimate where this post-disaster photo was taken, for placing it on a "
            "rescue map. Use visible text, signs, landmarks, bridges, rivers, terrain "
            "and architecture. Use web search to confirm landmark locations. Never use "
            "people's faces. If unsure, return a coarser precision and null coordinates "
            "rather than inventing a point."
        ),
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": region_text},
            {"type": "input_image", "image_url": image_to_data_url(path)},
        ]}],
        tools=[{"type": "web_search"}],
        reasoning={"effort": "medium"},
        text={"format": {"type": "json_schema", "name": "photo_location",
                         "schema": SCHEMA}},
    )
    return json.loads(final_text(response)), response.usage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*")
    ap.add_argument("--region", help='e.g. "Jablanica, Bosnia and Herzegovina"')
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--force-model", action="store_true",
                    help="ask Muse Spark even when EXIF GPS exists (to compare)")
    args = ap.parse_args()

    client = None
    results = {}
    for path in pick_images(args.images, args.limit):
        print(f"\n=== {path.name}")
        gps = exif_gps(path)
        print(f"  EXIF GPS: {gps if gps else 'none'}")
        entry = {"exif_gps": gps}
        if gps is None or args.force_model:
            client = client or meta_client()
            started = time.perf_counter()
            estimate, usage = estimate_location(client, path, args.region)
            print(f"  Muse Spark ({time.perf_counter() - started:.1f}s): {estimate['place_name']} "
                  f"[{estimate['precision']}, {estimate['confidence']:.2f}] "
                  f"-> {estimate['latitude']}, {estimate['longitude']}")
            for clue in estimate["clues_used"][:5]:
                print(f"    - {clue}")
            entry["estimate"] = estimate
        results[path.name] = entry

    target = out_path("geolocation.json")
    target.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n-> {target}")


if __name__ == "__main__":
    main()
