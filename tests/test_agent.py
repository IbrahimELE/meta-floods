"""Agent + zones (PLAN 12.2: T3 validation, T11 zone lifecycle)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from app.agent import Agent
from app.config import Settings
from app.db import Database
from app.pipeline import Pipeline
from app.state import zones_view
from app.zones import ToolRejected, adjust_priority, cluster, set_human_priority
from tests.test_pipeline import FakeApi, jpeg


@pytest.fixture
def world(tmp_path):
    s = replace(Settings(), data_dir=tmp_path, retry_delays=(0.0,), budget_images=100, budget_api_calls=1000)
    db = Database(s.db_path)
    pipe = Pipeline(db, s, FakeApi())
    inc = db.create_incident("t", as_of="2024-10-04T12:00:00")
    ids = []
    # two photos ~100 m apart, one ~20 km away (EXIF GPS in whole degrees → use pins instead)
    for n, (lat, lon) in enumerate([(43.6500, 17.9600), (43.6509, 17.9600), (43.8000, 18.2000)]):
        image_id = pipe.ingest(inc, jpeg(gps=None, color=(n, n, n)), f"p{n}.jpg")
        ids.append(image_id)
    asyncio.run(pipe.run_queue(inc))
    for image_id, (lat, lon) in zip(ids, [(43.6500, 17.9600), (43.6509, 17.9600), (43.8000, 18.2000)]):
        pipe.set_pin(image_id, lat, lon)
    return db, pipe, inc, ids


def findings(db, image_id):
    return [r["id"] for r in db.query("SELECT id FROM findings WHERE image_id = ? AND object_id IS NOT NULL", (image_id,))]


def test_cluster_groups_by_distance(world):
    db, pipe, inc, ids = world
    assert cluster(db, inc, 500)["zones_created"] == 2
    zones = zones_view(db, inc)
    sizes = sorted(len(z["image_ids"]) for z in zones)
    assert sizes == [1, 2]


def test_t3_adjust_validation(world):
    db, pipe, inc, ids = world
    cluster(db, inc, 500)
    z = next(z for z in zones_view(db, inc) if len(z["image_ids"]) == 2)
    good = findings(db, z["image_ids"][0])[:1]
    other_zone_finding = findings(db, ids[2])[:1]
    with pytest.raises(ToolRejected, match="delta"):
        adjust_priority(db, inc, z["id"], z["revision"], 3, "because reasons", good)
    with pytest.raises(ToolRejected, match="revision"):
        adjust_priority(db, inc, z["id"], z["revision"] + 1, 1, "because reasons", good)
    with pytest.raises(ToolRejected, match="not findings of this zone"):
        adjust_priority(db, inc, z["id"], z["revision"], 1, "because reasons", other_zone_finding + [999999])
    with pytest.raises(ToolRejected, match="does not exist"):
        adjust_priority(db, inc, 424242, 1, 1, "because reasons", good)
    result = adjust_priority(db, inc, z["id"], z["revision"], 1, "many separate damaged houses", good)
    assert result["new_priority"] == result["base_priority"] + 1
    set_human_priority(db, inc, z["id"], 2)
    with pytest.raises(ToolRejected, match="responder"):
        adjust_priority(db, inc, z["id"], z["revision"], -1, "lower it please now", good)
    assert next(v for v in zones_view(db, inc) if v["id"] == z["id"])["priority"] == 2


def test_t11_lock_and_evidence_expiry(world):
    db, pipe, inc, ids = world
    cluster(db, inc, 500)
    z = next(z for z in zones_view(db, inc) if len(z["image_ids"]) == 2)
    ev = findings(db, z["image_ids"][0])[:1]
    adjust_priority(db, inc, z["id"], z["revision"], 1, "many separate damaged houses", ev)
    assert next(v for v in zones_view(db, inc) if v["id"] == z["id"])["agent_delta"] == 1
    # rejecting the cited evidence expires the agent's correction
    with db.tx() as c:
        c.execute("INSERT INTO reviews (target_type, target_id, action, created_at) VALUES ('finding', ?, 'reject', 'now')", (str(ev[0]),))
    after = next(v for v in zones_view(db, inc) if v["id"] == z["id"])
    assert after["agent_delta"] == 0 and after["agent_delta_status"].startswith("expired")
    # a responder lock freezes membership through re-clustering, even with a huge radius
    set_human_priority(db, inc, z["id"], 4)
    cluster(db, inc, 2000)
    zones = zones_view(db, inc)
    locked = next(v for v in zones if v["id"] == z["id"])
    assert locked["locked"] and sorted(locked["image_ids"]) == sorted(z["image_ids"])
    assert all(ids[2] not in v["image_ids"] for v in zones if v["id"] == z["id"])


class ScriptedModel:
    """Plays back tool calls like the Responses API would."""

    def __init__(self, script):
        self.script, self.seen = list(script), []

    def __call__(self, **kwargs):
        self.seen.append(kwargs)
        step = self.script.pop(0) if self.script else []
        output = [NS(type="function_call", name=n, arguments=json.dumps(a), call_id=f"c{i}") for i, (n, a) in enumerate(step)]
        return NS(id=f"r{len(self.seen)}", output=output)


def test_agent_run_logs_and_rejects(world):
    db, pipe, inc, ids = world
    model = ScriptedModel([
        [("get_situation", {})],
        [("cluster_zones", {"radius_m": 500}), ("adjust_zone_priority", {"zone_id": 1, "zone_revision": 1, "delta": 5,
                                                                          "reason": "x", "evidence_ids": []})],
        [("request_human_review", {"target_type": "image", "target_ids": [ids[0]], "question": "Are people trapped here?"}),
         ("write_briefing", {"language": "en", "headline": "Two areas hit", "summary": "Go to zone 1 first."})],
        [],
    ])
    run_id = Agent(db, model).run(inc)
    run = db.one("SELECT * FROM agent_runs WHERE id = ?", (run_id,))
    assert run["status"] == "done"
    results = [r["result"] for r in db.query("SELECT result FROM agent_actions WHERE run_id = ? ORDER BY id", (run_id,))]
    assert results[0] == "read" and results[1] == "applied" and results[2].startswith("rejected")
    briefing = db.one("SELECT * FROM briefings WHERE incident_id = ?", (inc,))
    assert "Not verified" in briefing["body"] and "AI estimates" in briefing["body"]
    assert db.one("SELECT COUNT(*) n FROM review_requests WHERE incident_id = ?", (inc,))["n"] == 1
    # the rejection reason reached the model
    outputs = [json.loads(i["output"]) for i in model.seen[-1]["input"] if i.get("type") == "function_call_output"]
    sent = next(o for o in outputs if not o["ok"])
    assert sent["ok"] is False and "delta" in sent["rejected"]


def test_agent_step_limit(world):
    db, pipe, inc, ids = world
    model = ScriptedModel([[("get_situation", {})]] * 30)
    run_id = Agent(db, model).run(inc)
    assert db.one("SELECT status FROM agent_runs WHERE id = ?", (run_id,))["status"] == "incomplete"
