"""PLAN 7.2 examples + T12 (time)."""

import json

from app.priority import age_status, image_points, to_priority


def scene_row(help_=None, hazards=()):
    return {"object_id": None, "people_may_need_help": help_, "rejected": False,
            "hazards_json": json.dumps([{"type": h} for h in hazards])}


def obj(damage):
    return {"object_id": "x:1", "damage": damage, "rejected": False}


def test_plan_examples():
    r = image_points([scene_row(), obj("major")], {"water_depth": "waist"}, "fresh")
    assert (r["points"], to_priority(r["points"])) == (2, 2)
    r = image_points([scene_row(True, ["landslide"]), obj("destroyed")], {"water_depth": "none"}, "fresh")
    assert (r["points"], to_priority(r["points"])) == (6, 4)
    assert to_priority(7) == 5


def test_only_unknown_is_unassessed_not_low():
    r = image_points([scene_row(None), obj("unknown")], {"water_depth": "unknown"}, "fresh")
    assert r["points"] is None and to_priority(r["points"]) is None


def test_unknown_age_is_halved_and_upload_time_never_used():
    assert age_status(None, None) == "unknown"
    r = image_points([scene_row(True), obj("destroyed")], {"water_depth": "none"}, "unknown")
    assert r["points"] == 2  # 5 // 2


def test_historical_scenario_uses_as_of():
    assert age_status("2024-10-04T08:00:00", "2024-10-04T12:00:00") == "fresh"
    assert age_status("2024-10-03T08:00:00", "2024-10-04T12:00:00") == "stale"


def test_rejected_finding_stops_counting():
    row = obj("destroyed")
    row["rejected"] = True
    r = image_points([scene_row(False), row], {"water_depth": "none"}, "fresh")
    assert r["points"] == 0
