"""Zone operations with server-side validation (PLAN 7.1–7.3). Used by the agent's
tools and by the human endpoints. Every function returns ("applied", info) or
raises ToolRejected with a reason the agent sees."""

from __future__ import annotations

import json
from typing import Any

from .db import Database, now_iso
from .state import haversine_m, incident_images, zones_view


class ToolRejected(Exception):
    pass


def cluster(db: Database, incident_id: str, radius_m: float) -> dict:
    """Deterministic greedy clustering of published images by scene location.
    Locked zones keep their members and are never touched; every other zone is
    replaced (new zone = revision 1, so old agent corrections cannot carry over)."""
    if not 100 <= radius_m <= 2000:
        raise ToolRejected("radius_m must be between 100 and 2000")
    _, images = incident_images(db, incident_id)
    locked_members = {r["image_id"] for r in db.query(
        """SELECT m.image_id FROM zone_members m JOIN zones z ON z.id = m.zone_id
           WHERE z.incident_id = ? AND z.active = 1 AND z.locked = 1""", (incident_id,))}
    free = [i for i in images if i["published"] and i["location"] and i["id"] not in locked_members]
    # seeds: highest priority first, confirmed locations first, then stable by id
    free.sort(key=lambda i: (-(i["priority"] or 0), not i["location"]["confirmed"], i["id"]))
    groups: list[list[dict]] = []
    for img in free:
        here = (img["location"]["lat"], img["location"]["lon"])
        for g in groups:
            seed = (g[0]["location"]["lat"], g[0]["location"]["lon"])
            if haversine_m(seed, here) <= radius_m:
                g.append(img)
                break
        else:
            groups.append([img])
    with db.tx() as c:
        c.execute("UPDATE zones SET active = 0 WHERE incident_id = ? AND locked = 0 AND active = 1", (incident_id,))
        for n, g in enumerate(groups, start=1):
            cur = c.execute("INSERT INTO zones (incident_id, label, created_at) VALUES (?,?,?)",
                            (incident_id, f"Zone {n}", now_iso()))
            for img in g:
                c.execute("INSERT INTO zone_members (zone_id, image_id) VALUES (?,?)", (cur.lastrowid, img["id"]))
        db.emit(c, incident_id, "zones_updated", {"zones": len(groups), "locked_kept": len(locked_members)})
    return {"zones_created": len(groups), "images_in_locked_zones": len(locked_members)}


def _zone(db: Database, incident_id: str, zone_id: Any) -> Any:
    try:
        zid = int(zone_id)
    except (TypeError, ValueError):
        raise ToolRejected(f"zone_id {zone_id!r} is not a number")
    z = db.one("SELECT * FROM zones WHERE id = ? AND active = 1", (zid,))
    if z is None or z["incident_id"] != incident_id:
        raise ToolRejected(f"zone {zone_id} does not exist in this incident")
    return z


def adjust_priority(db: Database, incident_id: str, zone_id: Any, zone_revision: Any, delta: Any,
                    reason: str, evidence_ids: list) -> dict:
    z = _zone(db, incident_id, zone_id)
    if delta not in (-1, 0, 1):
        raise ToolRejected("delta must be -1, 0 or +1")
    if zone_revision != z["revision"]:
        raise ToolRejected(f"zone revision is {z['revision']}, you used {zone_revision} – read the situation again")
    if z["human_priority"]:
        raise ToolRejected("a responder set this zone's priority; agents cannot change it")
    if delta and (not reason or len(reason.strip()) < 10):
        raise ToolRejected("a non-zero delta needs a written reason")
    view = next(v for v in zones_view(db, incident_id) if v["id"] == z["id"])
    if view["base_priority"] is None:
        raise ToolRejected("zone is unassessed; request a human review instead of changing its priority")
    if not isinstance(evidence_ids, list) or (delta and not evidence_ids):
        raise ToolRejected("evidence_ids must list the finding ids that justify the change")
    _, images = incident_images(db, incident_id)
    member_findings = {fid for i in images if i["id"] in view["image_ids"] for fid in i["finding_ids"]}
    bad = [e for e in evidence_ids if e not in member_findings]
    if bad:
        raise ToolRejected(f"evidence ids {bad} are not findings of this zone")
    with db.tx() as c:
        c.execute("UPDATE zones SET agent_delta = ?, agent_revision = ?, agent_reason = ?, agent_evidence_json = ? WHERE id = ?",
                  (delta, z["revision"], reason, json.dumps(evidence_ids), z["id"]))
        db.emit(c, incident_id, "zones_updated", {"zone_id": z["id"], "agent_delta": delta})
    return {"zone_id": z["id"], "base_priority": view["base_priority"], "new_priority": max(1, min(5, view["base_priority"] + delta))}


def request_review(db: Database, incident_id: str, kind: str, target_type: str, target_ids: list,
                   question: str, run_id: int | None = None) -> dict:
    if target_type not in ("image", "finding", "zone"):
        raise ToolRejected("target_type must be image, finding or zone")
    if not target_ids or not question:
        raise ToolRejected("target_ids and question are required")
    table, col = {"image": ("images", "id"), "finding": ("findings", "id"), "zone": ("zones", "id")}[target_type]
    for tid in target_ids:
        row = db.one(f"SELECT * FROM {table} WHERE {col} = ?", (tid,))
        if row is None:
            raise ToolRejected(f"{target_type} {tid} does not exist")
        owner = row["incident_id"] if target_type != "finding" else db.image(row["image_id"])["incident_id"]
        if owner != incident_id:
            raise ToolRejected(f"{target_type} {tid} belongs to another incident")
    with db.tx() as c:
        cur = c.execute("""INSERT INTO review_requests (incident_id, kind, target_type, target_ids_json, question, run_id, created_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (incident_id, kind, target_type, json.dumps(target_ids), question[:500], run_id, now_iso()))
        db.emit(c, incident_id, "review_requested", {"id": cur.lastrowid})
    return {"review_request_id": cur.lastrowid}


# ------------------------------------------------------------------------- human side
def set_human_priority(db: Database, incident_id: str, zone_id: Any, priority: int | None) -> None:
    z = _zone(db, incident_id, zone_id)
    if priority is not None and priority not in (1, 2, 3, 4, 5):
        raise ToolRejected("priority must be 1–5")
    with db.tx() as c:
        c.execute("UPDATE zones SET human_priority = ?, locked = ? WHERE id = ?",
                  (priority, 1 if priority else 0, z["id"]))
        db.emit(c, incident_id, "zones_updated", {"zone_id": z["id"], "human_priority": priority})


def resolve_review(db: Database, incident_id: str, request_id: int) -> None:
    with db.tx() as c:
        c.execute("UPDATE review_requests SET status = 'resolved' WHERE id = ? AND incident_id = ?", (request_id, incident_id))
        db.emit(c, incident_id, "review_resolved", {"id": request_id})
