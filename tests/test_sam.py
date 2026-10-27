from PIL import Image

from app import sam


def obj(concept, box, fill=True):
    x1, y1, x2, y2 = box
    o = sam.SamObject(concept=concept, box=box, confidence=0.9)
    o.mask = Image.new("L", (x2 - x1, y2 - y1), 255 if fill else 0)
    o.origin = (x1, y1)
    return o


def test_merge_keeps_buildings_and_adds_non_overlapping_houses():
    b = obj("building", (0, 0, 10, 10))
    same_house = obj("house", (1, 1, 10, 10))      # IoU 0.81 with b → dropped
    other_house = obj("house", (50, 50, 60, 60))   # no overlap → kept
    merged = sam.merge_buildings([b, same_house, other_house], 0.5)
    assert len(merged) == 2 and all(o.concept == "building" for o in merged)


def test_road_flood_overlap():
    road = obj("road", (0, 0, 100, 10))
    water = obj("flood water", (50, 0, 200, 50))
    sam.flag_flooded_roads([road, water], (200, 50))
    assert road.flood_overlap == 0.5


def test_parse_real_sam_line():
    from tests.test_pipeline import SAM_TWO
    objs = sam.to_objects(sam.parse(SAM_TWO), "building")
    assert len(objs) == 2 and objs[0].mask is not None and objs[0].area > 0
