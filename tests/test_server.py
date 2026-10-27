"""Backend tests (PLAN 12.2: T6 isolation, read-only demo, upload → map → pin → review)."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace

os.environ["FH_NO_APP"] = "1"

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.pipeline import Pipeline
from app.server import create_app
from tests.test_pipeline import FakeApi, jpeg


@pytest.fixture
def server(tmp_path):
    s = replace(Settings(), data_dir=tmp_path, retry_delays=(0.0,), budget_images=100, budget_api_calls=1000)
    pipe = Pipeline(Database(s.db_path), s, FakeApi())
    app = create_app(pipe, start_worker=False, allow_dev=True)
    return TestClient(app), pipe


def process(pipe):
    asyncio.run(pipe.run_queue())


def test_upload_snapshot_pin_review(server):
    client, pipe = server
    inc = client.post("/api/incidents", json={"name": "t", "region": "X"}).json()["id"]
    files = [("files", ("a.jpg", jpeg(gps=(43, 17), color=(1, 1, 1)), "image/jpeg")),
             ("files", ("b.jpg", jpeg(gps=None, color=(2, 2, 2)), "image/jpeg")),
             ("files", ("c.txt", b"nope", "text/plain"))]
    res = client.post(f"/api/incidents/{inc}/images", files=files).json()["results"]
    assert [r["status"] for r in res] == ["queued", "queued", "rejected"]
    process(pipe)

    snap = client.get(f"/api/incidents/{inc}/snapshot").json()
    by_name = {i["original_name"]: i for i in snap["images"]}
    assert by_name["a.jpg"]["published"] == 1 and by_name["a.jpg"]["location"]["kind"] == "camera_exif"
    assert by_name["b.jpg"]["published"] == 0 and by_name["b.jpg"]["location_state"] == "needs_pin"
    assert snap["last_seq"] > 0

    b = by_name["b.jpg"]["id"]
    assert client.post(f"/api/images/{b}/pin", json={"lat": 43.65, "lon": 17.96}).json()["ok"]
    detail = client.get(f"/api/images/{b}").json()
    assert detail["published"] == 1 and detail["location"]["kind"] == "human_pin"
    assert client.get(f"/api/images/{b}/overlay").status_code == 200

    finding = next(f for f in detail["findings"] if f["object_id"])
    client.post(f"/api/findings/{finding['id']}/review", json={"action": "reject"})
    after = client.get(f"/api/images/{b}").json()
    assert next(f for f in after["findings"] if f["id"] == finding["id"])["rejected"]
    assert after["summary"]["objects"] == detail["summary"]["objects"] - 1


def test_sandbox_is_private_to_its_token(server):
    client, pipe = server
    inc = client.post("/api/sandbox", json={"name": "mine"}).json()["id"]
    assert client.get(f"/api/incidents/{inc}/snapshot").status_code == 200      # cookie set
    other = TestClient(client.app)                                                # new session, no cookie
    assert other.get(f"/api/incidents/{inc}/snapshot").status_code == 403
    assert other.get(f"/api/incidents/{inc}/events").status_code == 403
    files = [("files", ("a.jpg", jpeg(), "image/jpeg"))]
    assert other.post(f"/api/incidents/{inc}/images", files=files).status_code == 403
    image_id = client.post(f"/api/incidents/{inc}/images", files=files).json()["results"][0]["image_id"]
    assert other.get(f"/api/images/{image_id}/photo").status_code == 403
    assert client.get(f"/api/images/{image_id}/photo").status_code == 200


def test_demo_is_read_only_and_dev_can_be_disabled(server):
    client, pipe = server
    demo = pipe.db.create_incident("demo", mode="demo_readonly", as_of="2024-10-04T12:00:00")
    files = [("files", ("a.jpg", jpeg(), "image/jpeg"))]
    assert client.get(f"/api/incidents/{demo}/snapshot").status_code == 200
    assert client.post(f"/api/incidents/{demo}/images", files=files).status_code == 403

    public = TestClient(create_app(pipe, start_worker=False, allow_dev=False))
    assert public.post("/api/incidents", json={"name": "x"}).status_code == 403
    dev = pipe.db.create_incident("dev")
    assert public.get(f"/api/incidents/{dev}/snapshot").status_code == 403


def test_sandbox_upload_limit(server):
    client, pipe = server
    inc = client.post("/api/sandbox", json={"name": "s"}).json()["id"]
    files = [("files", (f"{i}.jpg", jpeg(color=(i, i, i)), "image/jpeg")) for i in range(6)]
    assert client.post(f"/api/incidents/{inc}/images", files=files).status_code == 413


def test_t10_durable_after_restart(tmp_path):
    """Snapshot after every commit: a confirmation and a budget reservation survive a
    restart that starts from the snapshot only (local working DB lost)."""
    snap = tmp_path / "vol" / "db.sqlite"
    commits = []
    s = replace(Settings(), data_dir=tmp_path / "work", retry_delays=(0.0,), budget_images=100, budget_api_calls=1000)
    db = Database(tmp_path / "local1.sqlite", snap, lambda: commits.append(1))
    pipe = Pipeline(db, s, FakeApi())
    inc = db.create_incident("t")
    image_id = pipe.ingest(inc, jpeg(gps=None), "a.jpg")
    pipe.set_pin(image_id, 43.6, 17.9)
    db.reserve("api_call", 1000)
    assert commits, "volume commit must be called after transactions"

    restarted = Database(tmp_path / "local2.sqlite", snap)          # fresh container, restore from snapshot
    assert restarted.image(image_id)["location_state"] == "confirmed"
    assert restarted.one("SELECT api_calls_reserved n FROM budget")["n"] == 1
    assert restarted.one("SELECT COUNT(*) n FROM reviews WHERE target_type = 'location'")["n"] == 1


def test_failed_snapshot_is_an_error(tmp_path):
    def broken():
        raise OSError("volume unavailable")
    db = Database(tmp_path / "l.sqlite", tmp_path / "v" / "db.sqlite", broken)
    with pytest.raises(OSError):
        db.create_incident("x")


def test_t4_blockages_are_human_only_and_raise_zone(server):
    """PLAN T4: an AI 'impassable' finding alone changes nothing; a responder-confirmed blockage
    inside a zone adds +1 to the zone and is listed in the snapshot."""
    from app.zones import cluster
    client, pipe = server
    inc = client.post("/api/incidents", json={"name": "t"}).json()["id"]
    image_id = client.post(f"/api/incidents/{inc}/images", files=[("files", ("a.jpg", jpeg(gps=None), "image/jpeg"))]).json()["results"][0]["image_id"]
    process(pipe)
    client.post(f"/api/images/{image_id}/pin", json={"lat": 43.65, "lon": 17.96})
    cluster(pipe.db, inc, 500)
    before = client.get(f"/api/incidents/{inc}/snapshot").json()["zones"][0]
    assert before["confirmed_blockage"] is False
    r = client.post(f"/api/incidents/{inc}/blockages", json={"a": [43.6501, 17.9601], "b": [43.6505, 17.9603], "direction": "both",
                                                               "way_id": 1, "a_node": 10, "b_node": 11})
    assert r.status_code == 200
    snap = client.get(f"/api/incidents/{inc}/snapshot").json()
    after = snap["zones"][0]
    assert after["confirmed_blockage"] is True and len(snap["blockages"]) == 1
    if before["base_priority"] is not None:
        assert after["base_points"] == before["base_points"] + 1
    assert client.delete(f"/api/blockages/{r.json()['id']}").json()["ok"]
    assert client.get(f"/api/incidents/{inc}/snapshot").json()["blockages"] == []
    other = client.post("/api/incidents", json={"name": "other"}).json()["id"]
    f = pipe.db.one("SELECT id FROM findings WHERE image_id = ?", (image_id,))["id"]
    assert client.post(f"/api/incidents/{other}/blockages", json={"a": [1, 1], "b": [1, 2], "finding_id": f}).status_code == 400
