"""Acceptance tests for the pipeline (PLAN 12.2: T1, T2/T9, T8, budget, ingest limits).
No network: the model API is a fake."""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational as R

from app.api import TransientError
from app.config import Settings
from app.db import Database
from app.pipeline import Pipeline, RejectedImage

# One real SAM 3.1 output line (from the meta-sam-parser README), two objects in a 320x334 frame.
SAM_TWO = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334;c=0.9|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
    ",1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334;c=0.8|>"
    "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>\n"
)


def valid_assessment(listing: str) -> dict:
    ids = [int(m) for m in re.findall(r"#(\d+):", listing)]
    return {
        "scene": {"disaster_type": "flood", "summary": "test", "water_depth": "knee", "viewpoint": "drone_oblique"},
        "objects": [{"id": i, "type": "building", "damage": "minor", "passability": "not_applicable",
                     "evidence": "roof damage", "confidence": 0.7} for i in ids],
        "hazards": [],
        "people": {"visible": None, "may_need_help": None, "note": "too far"},
        "image_labels": {"flooding_any": True, "flooding_structures": False,
                         "buildings_affected_or_greater": bool(ids), "buildings_major_or_greater": False,
                         "roads_damage": False, "debris_any": False},
        "location_clues": [],
    }


class FakeApi:
    """behaviour[path] ∈ ok | empty | rate_once | invalid | invalid_once"""

    def __init__(self):
        self.behaviour: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        self._rate_done: set[str] = set()
        self._invalid_done: set[str] = set()

    def _b(self, path: Path) -> str:
        return self.behaviour.get(str(path), "ok")

    def segment(self, path: Path, concept: str) -> str:
        self.calls.append(("segment", str(path)))
        b = self._b(path)
        if b == "rate_once" and str(path) not in self._rate_done:
            self._rate_done.add(str(path))
            raise TransientError("429")
        if b == "empty":
            return ""
        return SAM_TWO if concept == "building" else ""

    def assess(self, path: Path, overlay: Path, listing: str, feedback):
        self.calls.append(("assess", str(path)))
        b = self._b(path)
        if b == "invalid" or (b == "invalid_once" and str(path) not in self._invalid_done):
            self._invalid_done.add(str(path))
            return {"scene": "nonsense"}, "fake"
        return valid_assessment(listing), "fake"

    def count(self, kind: str, path: str) -> int:
        return sum(1 for k, p in self.calls if k == kind and p == path)


def jpeg(size=(400, 400), gps=None, color=(120, 120, 120)) -> bytes:
    image = Image.new("RGB", size, color)
    exif = image.getexif()
    if gps:
        exif.get_ifd(0x8825).update({1: "N", 2: (R(int(gps[0])), R(0), R(0)), 3: "E", 4: (R(int(gps[1])), R(0), R(0))})
    buf = io.BytesIO()
    image.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


@pytest.fixture
def env(tmp_path):
    s = replace(Settings(), data_dir=tmp_path, retry_delays=(0.0, 0.0, 0.0), budget_images=100,
                budget_api_calls=1000, ai_locate=False)
    db = Database(s.db_path)
    api = FakeApi()
    pipe = Pipeline(db, s, api)
    incident = db.create_incident("test", "Testland")
    return pipe, api, incident


def add(pipe, api, incident, behaviour="ok", gps=(43, 17), color=(1, 2, 3)):
    image_id = pipe.ingest(incident, jpeg(gps=gps, color=color), f"{behaviour}.jpg")
    api.behaviour[pipe.db.image(image_id)["path"]] = behaviour
    return image_id


def state(pipe, image_id):
    r = pipe.db.image(image_id)
    return r["processing_state"], r["segmentation_state"], r["location_state"], r["published"]


def test_t1_mixed_batch(env):
    pipe, api, inc = env
    ok = add(pipe, api, inc, "ok", color=(1, 1, 1))
    empty = add(pipe, api, inc, "empty", color=(2, 2, 2))
    rate = add(pipe, api, inc, "rate_once", color=(3, 3, 3))
    invalid = add(pipe, api, inc, "invalid", color=(4, 4, 4))
    nogps = add(pipe, api, inc, "ok", gps=None, color=(5, 5, 5))
    asyncio.run(pipe.run_queue(inc))

    assert state(pipe, ok) == ("done", "objects", "camera", 1)
    assert state(pipe, empty) == ("done", "no_objects", "camera", 1)
    assert state(pipe, rate) == ("done", "objects", "camera", 1)
    assert state(pipe, invalid)[0] == "failed"
    assert "invalid_output" in pipe.db.image(invalid)["last_error"]
    assert api.count("assess", pipe.db.image(invalid)["path"]) == 2      # exactly one retry
    assert state(pipe, nogps) == ("done", "objects", "needs_pin", 0)     # assessed, not on the map


def test_t8_pin_after_done_makes_no_api_calls(env):
    pipe, api, inc = env
    image_id = add(pipe, api, inc, "empty", gps=None)
    asyncio.run(pipe.run_queue(inc))
    assert state(pipe, image_id) == ("done", "no_objects", "needs_pin", 0)
    calls_before = len(api.calls)
    pipe.set_pin(image_id, 43.65, 17.96)
    assert state(pipe, image_id) == ("done", "no_objects", "confirmed", 1)
    assert len(api.calls) == calls_before


def test_t9_restart_while_waiting_for_pin(env):
    pipe, api, inc = env
    image_id = add(pipe, api, inc, "ok", gps=None)
    pipe.db.update_image(image_id, processing_state="running", stage="assess", attempts=1)  # crash mid-assess
    pipe.set_pin(image_id, 43.6, 17.9)                       # human pin before the restart
    asyncio.run(pipe.run_queue(inc))                         # "restart"
    assert state(pipe, image_id) == ("done", "objects", "confirmed", 1)
    assert pipe.db.image(image_id)["attempts"] == 2


def test_restart_gives_up_after_max_attempts(env):
    pipe, api, inc = env
    image_id = add(pipe, api, inc)
    pipe.db.update_image(image_id, processing_state="running", attempts=3)
    pipe.recover()
    assert pipe.db.image(image_id)["processing_state"] == "failed"


def test_budget_exhausted_means_no_api_call(env):
    pipe, api, inc = env
    pipe.s = replace(pipe.s, budget_api_calls=0)
    image_id = add(pipe, api, inc)
    asyncio.run(pipe.run_queue(inc))
    assert pipe.db.image(image_id)["processing_state"] == "failed"
    assert "budget" in pipe.db.image(image_id)["last_error"]
    assert api.calls == []


def test_ingest_rejects_and_dedupes(env):
    pipe, api, inc = env
    with pytest.raises(RejectedImage):
        pipe.ingest(inc, b"not an image", "x.txt")
    pipe.s = replace(pipe.s, max_pixels=100 * 100)
    with pytest.raises(RejectedImage):
        pipe.ingest(inc, jpeg(size=(200, 200)), "big.jpg")
    pipe.s = replace(pipe.s, max_pixels=40_000_000)
    data = jpeg()
    assert pipe.ingest(inc, data, "a.jpg") is not None
    assert pipe.ingest(inc, data, "a-again.jpg") is None


def test_events_are_emitted_in_order(env):
    pipe, api, inc = env
    add(pipe, api, inc)
    asyncio.run(pipe.run_queue(inc))
    types = [r["type"] for r in pipe.db.query("SELECT type FROM events WHERE incident_id = ? ORDER BY seq", (inc,))]
    assert types[0] == "image_added" and types[-1] == "finding_published"
