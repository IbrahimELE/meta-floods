"""Deterministic priority points (PLAN 7.2). The server computes these; the agent
may later only suggest a ±1 adjustment per zone."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

STALE_AFTER = timedelta(hours=12)
HAZARD_POINTS = {"collapse_risk", "landslide", "fast_current", "downed_power_lines", "deep_water"}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_status(captured_at: str | None, as_of: str | None) -> str:
    """fresh | stale | unknown (PLAN 5.4). Upload time is never used."""
    captured = parse_time(captured_at)
    if captured is None:
        return "unknown"
    ref = parse_time(as_of) or datetime.now(timezone.utc)
    return "stale" if ref - captured > STALE_AFTER else "fresh"


def image_points(findings: list[dict], scene: dict | None, age: str) -> dict:
    """Points for one image from its non-rejected findings.

    Returns {"points": int | None, "assessable": bool, "parts": [...]} – points is None
    when nothing could be assessed (→ the zone becomes `unassessed`, not low priority).
    """
    objects = [f for f in findings if f["object_id"] is not None and not f.get("rejected")]
    scene_rows = [f for f in findings if f["object_id"] is None and not f.get("rejected")]
    parts: list[str] = []
    points = 0
    assessable = False

    for row in scene_rows:
        if row["people_may_need_help"] is not None:
            assessable = True
        if row["people_may_need_help"] == 1:
            points += 3
            parts.append("people may need help +3")
        hazards = {h["type"] for h in json.loads(row["hazards_json"] or "[]")} & HAZARD_POINTS
        if hazards:
            assessable = True
            add = min(2, len(hazards))
            points += add
            parts.append(f"hazards {sorted(hazards)} +{add}")

    damages = {f["damage"] for f in objects if f["damage"]}
    if damages - {"unknown", "not_applicable"}:
        assessable = True
    if "destroyed" in damages:
        points += 2
        parts.append("destroyed building +2")
    elif "major" in damages:
        points += 1
        parts.append("major damage +1")

    depth = (scene or {}).get("water_depth")
    if depth and depth != "unknown":
        assessable = True
    if depth in ("waist", "above_waist"):
        points += 1
        parts.append(f"water {depth} +1")
    elif depth == "roof_level":
        points += 2
        parts.append("water roof level +2")

    if not assessable:
        return {"points": None, "assessable": False, "parts": ["nothing assessable"]}
    if age in ("stale", "unknown"):
        halved = points // 2
        parts.append(f"age {age}: {points} → {halved}")
        points = halved
    return {"points": points, "assessable": True, "parts": parts}


def to_priority(zone_points: int | None) -> int | None:
    """Z → 1..5 (PLAN 7.2). None stays None (unassessed)."""
    if zone_points is None:
        return None
    if zone_points <= 0:
        return 1
    if zone_points <= 2:
        return 2
    if zone_points <= 4:
        return 3
    if zone_points <= 6:
        return 4
    return 5
