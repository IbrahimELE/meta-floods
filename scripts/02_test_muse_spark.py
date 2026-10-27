"""Step 2: Muse Spark assesses damage, grounded in SAM's numbered objects.

The trick: we send Muse Spark the original photo AND the SAM overlay with
numbered boxes (#1, #2, ...). It then reports damage / passability per SAM
object id, so every claim points at a concrete mask on the photo. That's
what makes the result verifiable (and it's a non-basic use of two Meta models
together).

Run 01_test_sam.py first so outputs/<name>_sam.png exists. Without it the
script still works, but assesses the scene without object ids.

    python scripts/02_test_muse_spark.py
    python scripts/02_test_muse_spark.py samples/a.jpg --effort medium
    python scripts/02_test_muse_spark.py --backend baseten   # Muse Spark Open
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from common import (
    MUSE_SPARK,
    MUSE_SPARK_OPEN_BASETEN,
    baseten_client,
    final_text,
    image_to_data_url,
    meta_client,
    out_path,
    pick_images,
)

# Damage levels follow the xBD / Joint Damage Scale used in disaster research.
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scene", "objects", "hazards", "people", "priority", "location_clues"],
    "properties": {
        "scene": {
            "type": "object",
            "additionalProperties": False,
            "required": ["disaster_type", "summary", "water_depth", "viewpoint"],
            "properties": {
                "disaster_type": {
                    "type": "string",
                    "enum": ["flood", "earthquake", "landslide", "storm", "fire", "other", "none"],
                },
                "summary": {"type": "string"},
                "water_depth": {
                    "type": "string",
                    "enum": ["none", "ankle", "knee", "waist", "above_waist", "roof_level", "unknown"],
                },
                "viewpoint": {
                    "type": "string",
                    "enum": ["ground", "drone_oblique", "drone_nadir", "satellite", "unknown"],
                },
            },
        },
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "type", "damage", "passability", "evidence", "confidence"],
                "properties": {
                    "id": {"type": "integer"},
                    "type": {"type": "string", "enum": ["building", "road", "bridge", "other"]},
                    "damage": {
                        "type": "string",
                        "enum": ["no_damage", "minor", "major", "destroyed", "unknown"],
                    },
                    "passability": {
                        "type": "string",
                        "enum": ["passable", "caution", "impassable", "not_applicable", "unknown"],
                    },
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        },
        "hazards": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "description", "object_ids"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "deep_water", "fast_current", "landslide", "collapse_risk",
                            "downed_power_lines", "debris", "fire", "other",
                        ],
                    },
                    "description": {"type": "string"},
                    "object_ids": {"type": "array", "items": {"type": "integer"}},
                },
            },
        },
        "people": {
            "type": "object",
            "additionalProperties": False,
            "required": ["visible", "may_need_help", "note"],
            "properties": {
                "visible": {"type": "boolean"},
                "may_need_help": {"type": "boolean"},
                "note": {"type": "string"},
            },
        },
        "priority": {
            "type": "object",
            "additionalProperties": False,
            "required": ["score", "reason"],
            "properties": {
                "score": {"type": "integer", "description": "1 = low, 5 = urgent"},
                "reason": {"type": "string"},
            },
        },
        "location_clues": {"type": "array", "items": {"type": "string"}},
    },
}

INSTRUCTIONS = """You are assisting disaster responders. You get a post-disaster photo and,
if available, the same photo with numbered segmentation boxes (#1, #2, ...) from SAM.
For EVERY numbered object, report damage (xBD scale: no_damage, minor, major,
destroyed) and, for roads/bridges, whether a rescue vehicle could pass.
Base every judgement on visible evidence and say what you see in `evidence`.
Use `unknown` rather than guessing; confidence is 0-1.
People: say only whether people are visible and may need help. Never describe
faces or try to identify anyone.
location_clues: visible text, signs, landmarks, terrain, architecture that could
help place the photo on a map.
This is decision support for trained responders, not a final verdict."""


def build_content(image_path: Path) -> tuple[list[dict], bool]:
    overlay = out_path(f"{image_path.stem}_sam.png")
    sam_json = out_path(f"{image_path.stem}_sam.json")
    content = [{"type": "input_text", "text": "Original photo:"},
               {"type": "input_image", "image_url": image_to_data_url(image_path)}]
    grounded = overlay.exists() and sam_json.exists()
    if grounded:
        objects = json.loads(sam_json.read_text())["objects"]
        listing = "\n".join(f"#{o['id']}: SAM label '{o['concept']}'" for o in objects)
        content += [
            {"type": "input_text", "text": f"Same photo with SAM objects:\n{listing}"},
            {"type": "input_image", "image_url": image_to_data_url(overlay)},
        ]
    else:
        content.append({"type": "input_text", "text": "No SAM overlay: return objects as []."})
    return content, grounded


def assess_meta(client, content: list[dict], effort: str) -> tuple[dict, object]:
    response = client.responses.create(
        model=MUSE_SPARK,
        instructions=INSTRUCTIONS,
        input=[{"type": "message", "role": "user", "content": content}],
        reasoning={"effort": effort},
        text={"format": {"type": "json_schema", "name": "damage_assessment",
                         "schema": SCHEMA}},
    )
    return json.loads(final_text(response)), response.usage


def assess_baseten(client, content: list[dict]) -> tuple[dict, object]:
    """Muse Spark Open via Baseten (Chat Completions format)."""
    messages_content = []
    for part in content:
        if part["type"] == "input_text":
            messages_content.append({"type": "text", "text": part["text"]})
        else:
            messages_content.append({"type": "image_url", "image_url": {"url": part["image_url"]}})
    response = client.chat.completions.create(
        model=MUSE_SPARK_OPEN_BASETEN,
        messages=[{"role": "system", "content": INSTRUCTIONS},
                  {"role": "user", "content": messages_content}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "damage_assessment", "schema": SCHEMA}},
    )
    return json.loads(response.choices[0].message.content), response.usage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--backend", choices=["meta", "baseten"], default="meta")
    ap.add_argument("--effort", default="low",
                    choices=["minimal", "low", "medium", "high", "xhigh", "max"])
    args = ap.parse_args()

    client = meta_client() if args.backend == "meta" else baseten_client()
    for image_path in pick_images(args.images, args.limit):
        content, grounded = build_content(image_path)
        started = time.perf_counter()
        if args.backend == "meta":
            result, usage = assess_meta(client, content, args.effort)
        else:
            result, usage = assess_baseten(client, content)
        elapsed = time.perf_counter() - started

        print(f"\n=== {image_path.name}  ({'grounded in SAM' if grounded else 'no SAM'}, "
              f"{elapsed:.1f}s)")
        scene = result["scene"]
        print(f"  {scene['disaster_type']} | water: {scene['water_depth']} | "
              f"priority {result['priority']['score']}/5: {result['priority']['reason']}")
        for obj in result["objects"]:
            print(f"  #{obj['id']:<3} {obj['type']:<9} damage={obj['damage']:<10} "
                  f"pass={obj['passability']:<14} ({obj['confidence']:.2f}) {obj['evidence'][:70]}")
        for hazard in result["hazards"]:
            print(f"  ! {hazard['type']}: {hazard['description'][:90]}")
        if result["people"]["visible"]:
            print(f"  people: may need help={result['people']['may_need_help']}")
        print("  usage:", usage)

        target = out_path(f"{image_path.stem}_assessment_{args.backend}.json")
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"  -> {target.name}")


if __name__ == "__main__":
    main()
