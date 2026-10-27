"""Read model: what the map, the agent and the briefing see. Everything here is
computed from the database at read time, so a review, a pin or a recluster is
reflected immediately and stale agent corrections can never linger (PLAN 7.3)."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .db import Database, image_public
from .priority import age_status, image_points, to_priority


def latest_reviews(db: Database, target_type: str) -> dict[str, str]:
    rows = db.query(
        """SELECT target_id, action FROM reviews r1 WHERE target_type = ?
           AND id = (SELECT MAX(id) FROM reviews r2 WHERE r2.target_type = r1.target_type AND r2.target_id = r1.target_id)""",
        (target_type,))
    return {r["target_id"]: r["action"] for r in rows}


def location_of(db: Database, image_id: str) -> dict | None:
    rows = db.query("SELECT * FROM locations WHERE image_id = ? ORDER BY id DESC", (image_id,))
    for kind in ("human_pin", "camera_exif", "ai_scene_estimate"):
        for r in rows:
            if r["kind"] == kind:
                return {"lat": r["lat"], "lon": r["lon"], "kind": kind, "uncertainty_m": r["uncertainty_m"],
                        "confirmed": bool(r["confirmed_by_human"]), "note": r["source_detail"]}
    return None


def findings_of(db: Database, image_id: str, reviews: dict[str, str] | None = None) -> list[dict]:
    reviews = reviews if reviews is not None else latest_reviews(db, "finding")
    out = []
    for f in db.query("""SELECT f.*, o.n, o.concept, o.box_json, o.flood_overlap FROM findings f
                         LEFT JOIN objects o ON o.id = f.object_id WHERE f.image_id = ? ORDER BY o.n""", (image_id,)):
        d = dict(f)
        d["rejected"] = reviews.get(str(f["id"])) == "reject"
        d["confirmed"] = reviews.get(str(f["id"])) == "confirm"
        out.append(d)
    return out


def describe_image(db: Database, row: Any, inc: Any, detail: bool = False,
                   reviews: dict[str, str] | None = None) -> dict:
    d = image_public(row)
    d["location"] = location_of(db, row["id"])
    d["age"] = age_status(row["captured_at"], inc["as_of"])
    scene = json.loads(row["scene_json"]) if row["scene_json"] else None
    d["scene"] = scene
    findings = findings_of(db, row["id"], reviews) if row["processing_state"] == "done" else []
    score = image_points(findings, scene, d["age"]) if findings else {"points": None, "assessable": False, "parts": []}
    d["points"], d["assessable"], d["points_parts"] = score["points"], score["assessable"], score["parts"]
    d["priority"] = to_priority(score["points"])
    objs = [f for f in findings if f["object_id"] and not f["rejected"]]
    scene_row = next((f for f in findings if not f["object_id"]), None)
    d["summary"] = {
        "objects": len(objs),
        "damage": {k: sum(1 for f in objs if f["damage"] == k) for k in ("destroyed", "major", "minor", "no_damage", "unknown")},
        "roads_blocked": sum(1 for f in objs if f["passability"] == "impassable"),
        "roads_caution": sum(1 for f in objs if f["passability"] == "caution"),
        "roads_blocked_confirmed": sum(1 for f in objs if f["passability"] == "impassable" and f["confirmed"]),
        "hazards": [h["type"] for h in json.loads(scene_row["hazards_json"] or "[]")] if scene_row and not scene_row["rejected"] else [],
        "people_may_need_help": None if not scene_row else scene_row["people_may_need_help"],
    }
    d["finding_ids"] = [f["id"] for f in findings]
    if detail:
        d["findings"] = findings
        labels = db.one("SELECT labels_json FROM image_labels WHERE image_id = ?", (row["id"],))
        d["image_labels"] = json.loads(labels["labels_json"]) if labels else None
    return d


def incident_images(db: Database, incident_id: str) -> tuple[Any, list[dict]]:
    inc = db.one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    reviews = latest_reviews(db, "finding")
    rows = db.query("SELECT * FROM images WHERE incident_id = ? ORDER BY uploaded_at", (incident_id,))
    return inc, [describe_image(db, r, inc, reviews=reviews) for r in rows]


# ------------------------------------------------------------------------------ zones
def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def zones_view(db: Database, incident_id: str, images: list[dict] | None = None) -> list[dict]:
    """Zones with their CURRENT priority. An agent correction counts only while every
    piece of evidence it cited is still valid (exists, not rejected, still a member)."""
    if images is None:
        _, images = incident_images(db, incident_id)
    by_id = {i["id"]: i for i in images}
    reviews = latest_reviews(db, "finding")
    out = []
    for z in db.query("SELECT * FROM zones WHERE incident_id = ? AND active = 1 ORDER BY id", (incident_id,)):
        members = [r["image_id"] for r in db.query("SELECT image_id FROM zone_members WHERE zone_id = ?", (z["id"],))]
        imgs = [by_id[m] for m in members if m in by_id and by_id[m]["published"]]
        points = [i["points"] for i in imgs if i["points"] is not None]
        base_points = max(points) if points else None
        blocked = any(i["summary"]["roads_blocked_confirmed"] for i in imgs)
        if base_points is not None and blocked:
            base_points += 1
        base = to_priority(base_points)

        delta, delta_status = z["agent_delta"] or 0, None
        if delta:
            evidence = json.loads(z["agent_evidence_json"] or "[]")
            member_findings = {fid for i in imgs for fid in i["finding_ids"]}
            invalid = [e for e in evidence if e not in member_findings or reviews.get(str(e)) == "reject"]
            if z["agent_revision"] != z["revision"] or invalid or base is None:
                delta, delta_status = 0, "expired – evidence changed"
        priority = z["human_priority"] or (None if base is None else max(1, min(5, base + delta)))
        lats = [i["location"]["lat"] for i in imgs if i["location"]]
        lons = [i["location"]["lon"] for i in imgs if i["location"]]
        out.append({
            "id": z["id"], "revision": z["revision"], "locked": bool(z["locked"]),
            "status": "unassessed" if base is None and not z["human_priority"] else "assessed",
            "base_priority": base, "base_points": base_points, "confirmed_blockage": blocked,
            "agent_delta": delta, "agent_delta_status": delta_status, "agent_reason": z["agent_reason"] if delta else None,
            "human_priority": z["human_priority"], "priority": priority,
            "image_ids": [i["id"] for i in imgs],
            "center": [sum(lats) / len(lats), sum(lons) / len(lons)] if lats else None,
            "radius_m": max((haversine_m((sum(lats) / len(lats), sum(lons) / len(lons)), (a, b))
                             for a, b in zip(lats, lons)), default=0) + 150 if lats else None,
            "label": z["label"],
        })
    out.sort(key=lambda z: (z["status"] != "unassessed", -(z["priority"] or 0)))
    return out


def state_hash(zones: list[dict]) -> str:
    key = json.dumps([(z["id"], z["revision"], z["priority"], z["status"], sorted(z["image_ids"])) for z in zones])
    return hashlib.sha256(key.encode()).hexdigest()[:16]
