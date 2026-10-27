"""The coordinating agent (PLAN 7): Muse Spark 1.3 with function tools.

The agent never computes priorities itself – the server does (PLAN 7.2). It can
group photos into zones, suggest a ±1 correction with evidence, ask a human to
check something, and write the briefing. Every call is validated and logged."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from .db import Database, now_iso
from .state import incident_images, state_hash, zones_view
from .zones import ToolRejected, adjust_priority, cluster, request_review

MAX_STEPS = 15
MAX_SECONDS = 120

TOOLS = [
    {"type": "function", "name": "get_situation",
     "description": "Current zones (server-computed priority, revision, members), every published photo's findings summary, "
                    "photos waiting for a location, and open review requests. Call this first and after changes.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "cluster_zones",
     "description": "Group published photos into zones by location (deterministic). Zones locked by a responder are kept. "
                    "Replaces all unlocked zones, so earlier priority corrections on them are dropped.",
     "parameters": {"type": "object", "properties": {"radius_m": {"type": "number", "description": "100–2000"}},
                    "required": ["radius_m"], "additionalProperties": False}},
    {"type": "function", "name": "adjust_zone_priority",
     "description": "Suggest a correction of -1, 0 or +1 to a zone's server-computed priority. Only when the findings show "
                    "something the fixed rule misses (e.g. many separate collapsed buildings, a whole area cut off). "
                    "Must cite finding ids from that zone. Rejected for responder-locked or unassessed zones.",
     "parameters": {"type": "object", "properties": {
         "zone_id": {"type": "integer"}, "zone_revision": {"type": "integer"},
         "delta": {"type": "integer", "enum": [-1, 0, 1]}, "reason": {"type": "string"},
         "evidence_ids": {"type": "array", "items": {"type": "integer"}}},
         "required": ["zone_id", "zone_revision", "delta", "reason", "evidence_ids"], "additionalProperties": False}},
    {"type": "function", "name": "flag_possible_duplicate",
     "description": "Ask a responder whether several photos show the same place/object. Does not merge anything.",
     "parameters": {"type": "object", "properties": {
         "image_ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
         "required": ["image_ids", "reason"], "additionalProperties": False}},
    {"type": "function", "name": "request_human_review",
     "description": "Ask a responder to check something: a low-confidence or conflicting finding, people who may need help, "
                    "a photo of unknown age, an unassessed zone.",
     "parameters": {"type": "object", "properties": {
         "target_type": {"type": "string", "enum": ["image", "finding", "zone"]},
         "target_ids": {"type": "array", "items": {"type": ["string", "integer"]}},
         "question": {"type": "string"}},
         "required": ["target_type", "target_ids", "question"], "additionalProperties": False}},
    {"type": "function", "name": "write_briefing",
     "description": "Write the situation briefing for the incident commander. The server adds the ranked zone table, "
                    "confirmed blockages and the 'not verified' list from the database; you write the headline and a short "
                    "plain-language summary (what to do first and why, what is uncertain). Refer to zones by their label "
                    "(e.g. 'Zone 3') and to places by what is visible – never include internal ids or hashes. "
                    "Call once per language at the end.",
     "parameters": {"type": "object", "properties": {
         "language": {"type": "string", "enum": ["en", "bs"]},
         "headline": {"type": "string"}, "summary": {"type": "string"}},
         "required": ["language", "headline", "summary"], "additionalProperties": False}},
]

INSTRUCTIONS = """You coordinate the first hours after a flood, landslide or earthquake for a rescue team.
Your inputs are AI findings from photos (SAM 3.1 masks + Muse Spark assessments). They can be wrong.

Work in this order:
1. get_situation.
2. If photos are not grouped yet, or new photos arrived outside zones, cluster_zones (start with ~500 m).
3. For each zone, compare its findings with the server priority. Only if the rule clearly misses something,
   adjust_zone_priority by ±1 with finding ids as evidence. Most zones need no change.
4. request_human_review for: people who may need help, unassessed zones, findings with low self-confidence that
   drive a high priority, photos of unknown age that drive priority. flag_possible_duplicate for photos that look
   like the same place.
5. write_briefing in English ("en") and in Bosnian ("bs").

Rules: never invent findings, locations or numbers; cite ids. "Unknown" is not "safe". Do not describe or identify people.
You support trained responders – they decide. Be brief."""


class Agent:
    def __init__(self, db: Database, call_model: Callable[..., Any], model: str = "muse-spark-1.3"):
        self.db, self.call_model, self.model = db, call_model, model

    # ------------------------------------------------------------------ tools
    def situation(self, incident_id: str) -> dict:
        inc, images = incident_images(self.db, incident_id)
        zones = zones_view(self.db, incident_id, images)
        in_zone = {i for z in zones for i in z["image_ids"]}
        published = [i for i in images if i["published"]]

        def brief(i: dict) -> dict:
            return {"image_id": i["id"], "name": i["original_name"], "priority": i["priority"], "points": i["points"],
                    "points_parts": i["points_parts"], "age": i["age"], "location": i["location"]["kind"] if i["location"] else None,
                    "scene": (i["scene"] or {}).get("summary"), "water_depth": (i["scene"] or {}).get("water_depth"),
                    "summary": i["summary"], "finding_ids": i["finding_ids"][:60]}

        findings = {}
        for i in published:
            for f in self.db.query("""SELECT f.id, o.n, o.concept, f.damage, f.passability, f.self_confidence, f.evidence_text
                                      FROM findings f JOIN objects o ON o.id = f.object_id WHERE f.image_id = ?
                                      AND (f.damage IN ('major','destroyed') OR f.passability IN ('impassable','caution'))
                                      LIMIT 25""", (i["id"],)):
                findings.setdefault(i["id"], []).append(dict(f))
        return {
            "incident": {"name": inc["name"], "region": inc["region_text"], "as_of": inc["as_of"]},
            "zones": zones,
            "photos": [brief(i) for i in published],
            "notable_findings_by_photo": findings,
            "photos_not_in_a_zone": [i["id"] for i in published if i["id"] not in in_zone],
            "photos_waiting_for_location": [i["id"] for i in images if i["location_state"] == "needs_pin"],
            "open_review_requests": [dict(r) for r in self.db.query(
                "SELECT id, kind, target_type, target_ids_json, question FROM review_requests WHERE incident_id = ? AND status = 'open'",
                (incident_id,))],
        }

    def write_briefing(self, incident_id: str, run_id: int | None, language: str, headline: str, summary: str) -> dict:
        if language not in ("en", "bs"):
            raise ToolRejected("language must be en or bs")
        if not headline or not summary:
            raise ToolRejected("headline and summary are required")
        _, images = incident_images(self.db, incident_id)
        zones = zones_view(self.db, incident_id, images)
        by_id = {i["id"]: i for i in images}
        en = language == "en"
        lines = [summary.strip(), "", "## " + ("Zones by priority" if en else "Zone po prioritetu")]
        label = (lambda z: z["label"]) if en else (lambda z: z["label"].replace("Zone", "Zona"))
        for z in [z for z in zones if z["status"] == "assessed"][:5]:
            imgs = [by_id[i] for i in z["image_ids"]]
            dmg = sum(i["summary"]["damage"]["destroyed"] + i["summary"]["damage"]["major"] for i in imgs)
            note = f" (agent {z['agent_delta']:+d}: {z['agent_reason']})" if z["agent_delta"] else ""
            note += " – " + ("set by responder" if en else "postavio spasilac") if z["human_priority"] else ""
            lines.append(f"- {label(z)}: {'priority' if en else 'prioritet'} {z['priority']} – {len(imgs)} "
                         f"{'photos' if en else 'fotografija'}, {dmg} {'buildings major/destroyed' if en else 'zgrada teško oštećeno/uništeno'}{note}")
        blocked = [i for i in images if i["summary"]["roads_blocked_confirmed"]]
        lines += ["", "## " + ("Confirmed road blockages" if en else "Potvrđene blokade cesta")]
        lines += [f"- {i['original_name']}" for i in blocked] or ["- " + ("none confirmed yet" if en else "još nijedna potvrđena")]
        unassessed = [z for z in zones if z["status"] == "unassessed"]
        no_loc = [i for i in images if i["location_state"] == "needs_pin"]
        unknown_age = [i for i in images if i["published"] and i["age"] == "unknown"]
        lines += ["", "## " + ("Not verified" if en else "Nije provjereno")]
        lines += [f"- {label(z)}: " + ("could not be assessed from the photos" if en else "nije se moglo procijeniti s fotografija") for z in unassessed]
        if no_loc:
            lines.append(f"- {len(no_loc)} " + ("photos without a location (not on the map)" if en else "fotografija bez lokacije (nisu na mapi)"))
        if unknown_age:
            lines.append(f"- {len(unknown_age)} " + ("photos of unknown age" if en else "fotografija nepoznate starosti"))
        stale = [i for i in images if i["published"] and i["age"] == "stale"]
        if stale:
            lines.append(f"- {len(stale)} " + ("photos older than 12 h – conditions may have changed" if en else "fotografija starijih od 12 h – stanje se možda promijenilo"))
        lines.append("- " + ("All findings are AI estimates (Meta SAM 3.1 + Muse Spark) – verify on site."
                             if en else "Svi nalazi su AI procjene (Meta SAM 3.1 + Muse Spark) – provjeriti na terenu."))
        body = "\n".join(lines)
        with self.db.tx() as c:
            cur = c.execute("""INSERT INTO briefings (incident_id, language, headline, body, state_hash, run_id, created_at)
                               VALUES (?,?,?,?,?,?,?)""",
                            (incident_id, language, headline[:200], body, state_hash(zones), run_id, now_iso()))
            self.db.emit(c, incident_id, "briefing_written", {"id": cur.lastrowid, "language": language})
        return {"briefing_id": cur.lastrowid}

    def dispatch(self, incident_id: str, run_id: int, name: str, args: dict) -> Any:
        if name == "get_situation":
            return self.situation(incident_id)
        if name == "cluster_zones":
            return cluster(self.db, incident_id, float(args.get("radius_m", 500)))
        if name == "adjust_zone_priority":
            return adjust_priority(self.db, incident_id, args.get("zone_id"), args.get("zone_revision"), args.get("delta"),
                                   args.get("reason", ""), args.get("evidence_ids", []))
        if name == "flag_possible_duplicate":
            ids = args.get("image_ids") or []
            if len(ids) < 2:
                raise ToolRejected("need at least two image ids")
            return request_review(self.db, incident_id, "duplicate", "image", ids, args.get("reason", ""), run_id)
        if name == "request_human_review":
            return request_review(self.db, incident_id, "check", args.get("target_type", ""), args.get("target_ids") or [],
                                  args.get("question", ""), run_id)
        if name == "write_briefing":
            return self.write_briefing(incident_id, run_id, args.get("language", ""), args.get("headline", ""), args.get("summary", ""))
        raise ToolRejected(f"unknown tool {name}")

    def _log(self, run_id: int, tool: str, args: dict, result: str) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO agent_actions (run_id, tool, args_json, result, created_at) VALUES (?,?,?,?,?)",
                      (run_id, tool, json.dumps(args)[:4000], result[:500], now_iso()))
            inc = c.execute("SELECT incident_id FROM agent_runs WHERE id = ?", (run_id,)).fetchone()[0]
            self.db.emit(c, inc, "agent_action", {"run_id": run_id, "tool": tool, "result": result[:200]})

    # ------------------------------------------------------------------ loop
    def run(self, incident_id: str) -> int:
        """Synchronous; the server runs it in a thread. Returns the run id."""
        if self.db.one("SELECT id FROM agent_runs WHERE incident_id = ? AND status = 'running'", (incident_id,)):
            raise ToolRejected("an agent run is already in progress for this incident")
        with self.db.tx() as c:
            run_id = c.execute("INSERT INTO agent_runs (incident_id, status, started_at) VALUES (?,?,?)",
                               (incident_id, "running", now_iso())).lastrowid
            self.db.emit(c, incident_id, "agent_started", {"run_id": run_id})
        started = time.monotonic()
        status, error, steps = "done", None, 0
        try:
            # The full conversation is sent every turn instead of previous_response_id:
            # the API sometimes answered "referenced response not found or expired".
            history: list[dict] = [{"type": "message", "role": "user",
                                    "content": [{"type": "input_text", "text": "Assess the current situation and prepare the briefing."}]}]
            response = self.call_model(instructions=INSTRUCTIONS, tools=TOOLS, input=history)
            while True:
                calls = [i for i in response.output if getattr(i, "type", "") == "function_call"]
                if not calls:
                    break
                if steps >= MAX_STEPS or time.monotonic() - started > MAX_SECONDS:
                    status = "incomplete"
                    break
                outputs = []
                for call in calls:
                    steps += 1
                    try:
                        args = json.loads(call.arguments or "{}")
                        result = self.dispatch(incident_id, run_id, call.name, args)
                        self._log(run_id, call.name, args, "read" if call.name == "get_situation" else "applied")
                        payload = {"ok": True, "result": result}
                    except ToolRejected as exc:
                        self._log(run_id, call.name, locals().get("args", {}), f"rejected: {exc}")
                        payload = {"ok": False, "rejected": str(exc)}
                    except json.JSONDecodeError:
                        self._log(run_id, call.name, {}, "rejected: arguments were not valid JSON")
                        payload = {"ok": False, "rejected": "arguments were not valid JSON"}
                    outputs.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": json.dumps(payload, default=str)[:60000]})
                history += [{"type": "function_call", "call_id": c.call_id, "name": c.name, "arguments": c.arguments or "{}"}
                            for c in calls]
                history += outputs
                response = self.call_model(instructions=INSTRUCTIONS, tools=TOOLS, input=history)
        except Exception as exc:  # noqa: BLE001 – a failed run must be visible, not crash the server
            status, error = "failed", f"{type(exc).__name__}: {exc}"[:500]
        with self.db.tx() as c:
            c.execute("UPDATE agent_runs SET status = ?, steps = ?, error = ?, finished_at = ? WHERE id = ?",
                      (status, steps, error, now_iso(), run_id))
            self.db.emit(c, incident_id, "agent_finished", {"run_id": run_id, "status": status})
        return run_id


def meta_caller(client, model: str = "muse-spark-1.3", effort: str = "medium") -> Callable[..., Any]:
    def call(**kwargs: Any) -> Any:
        return client.responses.create(model=model, reasoning={"effort": effort}, timeout=60, **kwargs)
    return call
