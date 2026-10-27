"""Muse Spark assessment: JSON schema, prompt and semantic validation (PLAN 5.2, 6.2)."""

from __future__ import annotations

from typing import Any

import jsonschema

DAMAGE = ["no_damage", "minor", "major", "destroyed", "unknown", "not_applicable"]
PASSABILITY = ["passable", "caution", "impassable", "not_applicable", "unknown"]
HAZARDS = ["deep_water", "fast_current", "landslide", "collapse_risk",
           "downed_power_lines", "debris", "fire", "other"]
OBJECT_TYPES = ["building", "road", "bridge", "water", "other"]

# Image-level labels compared 1:1 with LADI v2 in E1 (PLAN 6.2). Kept separate
# from per-object damage / passability on purpose.
IMAGE_LABELS = {
    "flooding_any": "flood water visible anywhere in the image",
    "flooding_structures": "flood water touching or surrounding buildings",
    "buildings_affected_or_greater": "at least one building at FEMA level 'affected' or worse: any visible damage, OR flood water reaching or surrounding the building",
    "buildings_major_or_greater": "at least one building with major damage or destroyed",
    "roads_damage": "visible damage to a road surface or structure (collapsed, washed out, cracked, covered in debris) – NOT whether it is flooded or passable",
    "debris_any": "debris visible anywhere",
}

NULLABLE_BOOL = {"type": ["boolean", "null"]}


def _obj(props: dict, **extra: Any) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": list(props), "properties": props, **extra}


SCHEMA = _obj({
    "scene": _obj({
        "disaster_type": {"type": "string",
                          "enum": ["flood", "earthquake", "landslide", "storm", "fire", "other", "none", "unknown"]},
        "summary": {"type": "string"},
        "water_depth": {"type": "string",
                        "enum": ["none", "ankle", "knee", "waist", "above_waist", "roof_level", "unknown"]},
        "viewpoint": {"type": "string",
                      "enum": ["ground", "drone_oblique", "drone_nadir", "satellite", "unknown"]},
    }),
    "objects": {"type": "array", "items": _obj({
        "id": {"type": "integer"},
        "type": {"type": "string", "enum": OBJECT_TYPES},
        "damage": {"type": "string", "enum": DAMAGE},
        "passability": {"type": "string", "enum": PASSABILITY},
        "evidence": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    })},
    "hazards": {"type": "array", "items": _obj({
        "type": {"type": "string", "enum": HAZARDS},
        "description": {"type": "string"},
        "object_ids": {"type": "array", "items": {"type": "integer"}},
    })},
    "people": _obj({
        "visible": NULLABLE_BOOL,
        "may_need_help": NULLABLE_BOOL,
        "note": {"type": "string"},
    }),
    "image_labels": _obj({k: {"type": "boolean", "description": v} for k, v in IMAGE_LABELS.items()}),
    "location_clues": {"type": "array", "items": {"type": "string"}},
})

INSTRUCTIONS = f"""You assist disaster responders. You get a post-disaster photo and the same photo
with numbered segmentation masks (#1, #2, ...) from SAM 3.1, plus a list of those objects.

For EVERY numbered object return one entry with the same id:
- damage (xBD scale): no_damage, minor, major, destroyed; unknown if you can't see enough;
  not_applicable for water.
- passability (roads, bridges): passable, caution, impassable, unknown – could a rescue
  vehicle use the VISIBLE part? A road partly under flood water is at least caution.
  Buildings and water: not_applicable.
- evidence: what you actually see. confidence: 0-1, your own estimate.
SAM can be wrong: if a numbered object is not what its label says, set type accordingly
(e.g. "other") and explain in evidence.

people: visible = true/false, or null if the resolution makes it impossible to tell.
may_need_help likewise (null = cannot tell). Never describe faces or identify anyone.

image_labels: answer each yes/no for the WHOLE image using exactly these definitions:
""" + "\n".join(f"- {k}: {v}" for k, v in IMAGE_LABELS.items()) + """

location_clues: visible text, signs, landmarks, terrain, architecture.
Use unknown / null instead of guessing. This is decision support for trained responders."""


def validate(result: Any, object_ids: set[int]) -> list[str]:
    """Shape (JSON schema) + semantics. Empty list = valid."""
    errors = [e.message for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(result)]
    if errors:
        return errors[:10]
    seen: set[int] = set()
    for obj in result["objects"]:
        oid = obj["id"]
        if oid not in object_ids:
            errors.append(f"object id {oid} does not exist (valid ids: {sorted(object_ids)[:20]}...)")
        if oid in seen:
            errors.append(f"object id {oid} appears twice")
        seen.add(oid)
        if obj["type"] == "building" and obj["passability"] != "not_applicable":
            errors.append(f"object {oid}: buildings must have passability not_applicable")
    missing = object_ids - seen
    if missing:
        errors.append(f"missing assessments for object ids {sorted(missing)[:20]}")
    for hazard in result["hazards"]:
        bad = [i for i in hazard["object_ids"] if i not in object_ids]
        if bad:
            errors.append(f"hazard {hazard['type']} references unknown ids {bad}")
    return errors
