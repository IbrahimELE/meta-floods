"""SAM 3.1 output → objects with full-frame masks, merging and overlays."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from meta_sam_parser import (
    CompletedOutcome,
    decode_mask_to_raster,
    image_segmentation_format,
    video_segmentation_format,
)
from PIL import Image, ImageChops, ImageDraw

import meta_sam_parser._segmentation as _segmentation

# The parser decodes every mask once just to validate it and throws the raster away; local_mask
# then decodes it again. Mask decoding is pure Python and dominates CPU time, so the parser's
# validation decode is cached and reused (the mask is frozen, its payload is the key).
_RASTERS: dict = {}


def _decode_cached(mask) -> bytes:
    key = (mask.encoding, mask.width, mask.height, mask.payload)
    raster = _RASTERS.pop(key, None)
    if raster is None:
        raster = decode_mask_to_raster(mask)
    _RASTERS[key] = raster
    while len(_RASTERS) > 64:
        _RASTERS.pop(next(iter(_RASTERS)))
    return raster


_segmentation.decode_mask_to_raster = _decode_cached

COLORS = {
    "building": (255, 99, 71),
    "house": (255, 99, 71),
    "road": (65, 105, 225),
    "bridge": (255, 215, 0),
    "flood water": (0, 191, 255),
}
FALLBACK = (186, 85, 211)


@dataclass
class SamObject:
    concept: str
    box: tuple[int, int, int, int]          # x1, y1, x2, y2 (half-open), source pixels
    confidence: float | None
    mask: Image.Image | None = None         # box-local "L" mask (255 = object), placed at `origin`
    origin: tuple[int, int] = (0, 0)
    n: int = 0                              # number on the overlay (set after merging)
    flood_overlap: float | None = None
    extra: dict = field(default_factory=dict)

    @property
    def area(self) -> int:
        if self.mask is None:
            x1, y1, x2, y2 = self.box
            return max(0, x2 - x1) * max(0, y2 - y1)
        return self.mask.histogram()[255]


def parse(text: str) -> list:
    """Box and mask records from SAM's wire text (`<0f>id<|box…|><|mask…|>,…`)."""
    if not text.strip():
        return []
    result = None
    for make_format in (image_segmentation_format, video_segmentation_format):
        parser = make_format().create_parser()
        parser.push(text if text.endswith("\n") else text + "\n")
        result = parser.finish(CompletedOutcome()).result
        if any(r.kind == "box" for r in result.records):
            break
    return [r for r in (result.records if result else ()) if r.kind in ("box", "mask")]


def to_objects(records: list, concept: str) -> list[SamObject]:
    boxes = {r.object_id: r for r in records if r.kind == "box"}
    masks = {r.object_id: r for r in records if r.kind == "mask"}
    objects = []
    for object_id, box in boxes.items():
        mask_record = masks.get(object_id)
        objects.append(SamObject(
            concept=concept,
            box=(round(box.left), round(box.top), round(box.right), round(box.bottom)),
            confidence=box.confidence,
        ))
        if mask_record is not None:
            objects[-1].mask, objects[-1].origin = local_mask(mask_record)
    return objects


def local_mask(mask_record) -> tuple[Image.Image, tuple[int, int]]:
    """SAM mask → box-local 'L' image (255 inside) and its top-left origin.
    Masks stay box-local to keep memory small (an image can have 80+ objects)."""
    mask = mask_record.mask
    raster = _decode_cached(mask)
    local = Image.frombytes("L", (mask.width, mask.height), bytes(raster)).point(lambda v: 255 if v else 0)
    b = mask_record.bounds
    left, top = round(b.left), round(b.top)
    local_size = (max(1, round(b.right) - left), max(1, round(b.bottom) - top))
    if local.size != local_size:
        local = local.resize(local_size, Image.NEAREST)
    return local, (left, top)


def _crop(obj: SamObject, rect: tuple[int, int, int, int]) -> Image.Image:
    """The object's mask inside `rect` (absolute coordinates)."""
    ox, oy = obj.origin
    x1, y1, x2, y2 = rect
    return obj.mask.crop((x1 - ox, y1 - oy, x2 - ox, y2 - oy))


def _extent(obj: SamObject) -> tuple[int, int, int, int]:
    ox, oy = obj.origin
    return ox, oy, ox + obj.mask.width, oy + obj.mask.height


def iou(a: SamObject, b: SamObject) -> float:
    if a.mask is not None and b.mask is not None:
        ax1, ay1, ax2, ay2 = _extent(a)
        bx1, by1, bx2, by2 = _extent(b)
        rect = (max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2))
        if rect[0] >= rect[2] or rect[1] >= rect[3]:
            return 0.0
        inter = ImageChops.multiply(_crop(a, rect), _crop(b, rect)).histogram()[255]
        union = a.area + b.area - inter
        return inter / union if union else 0.0
    ax1, ay1, ax2, ay2 = a.box
    bx1, by1, bx2, by2 = b.box
    iw, ih = max(0, min(ax2, bx2) - max(ax1, bx1)), max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = a.area + b.area - inter
    return inter / union if union else 0.0


def merge_buildings(objects: list[SamObject], threshold: float) -> list[SamObject]:
    """`building` and `house` find complementary sets (E4). Keep all buildings,
    add houses that don't overlap one (IoU ≤ threshold); everything becomes 'building'."""
    buildings = [o for o in objects if o.concept == "building"]
    houses = [o for o in objects if o.concept == "house"]
    rest = [o for o in objects if o.concept not in ("building", "house")]
    kept = list(buildings)
    for house in houses:
        if all(iou(house, b) <= threshold for b in kept):
            kept.append(house)
    for obj in kept:
        obj.concept = "building"
    return kept + rest


def flag_flooded_roads(objects: list[SamObject], size: tuple[int, int]) -> None:
    """Share of each road/bridge mask that lies under a SAM flood-water mask – a
    deterministic hint for passability that Muse Spark gets as evidence."""
    water = [o for o in objects if o.concept == "flood water" and o.mask is not None]
    if not water:
        return
    union = Image.new("L", size, 0)
    for w in water:
        union.paste(255, w.origin, w.mask)
    for road in (o for o in objects if o.concept in ("road", "bridge") and o.mask is not None):
        area = road.area
        if area:
            under = ImageChops.multiply(road.mask, union.crop(_extent(road)))
            road.flood_overlap = round(under.histogram()[255] / area, 3)


def number(objects: list[SamObject]) -> None:
    """Stable numbering: by concept, then top-to-bottom, left-to-right."""
    order = {"building": 0, "road": 1, "bridge": 2, "flood water": 3}
    objects.sort(key=lambda o: (order.get(o.concept, 9), o.box[1], o.box[0]))
    for n, obj in enumerate(objects, start=1):
        obj.n = n


def render(image: Image.Image, objects: list[SamObject], target: Path) -> Path:
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for obj in objects:
        if obj.mask is not None:
            color = COLORS.get(obj.concept, FALLBACK)
            alpha = 80 if obj.concept == "flood water" else 110
            overlay.paste(Image.new("RGBA", obj.mask.size, (*color, alpha)), obj.origin, obj.mask)
    out = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(out)
    for obj in objects:
        color = COLORS.get(obj.concept, FALLBACK)
        x1, y1, x2, y2 = obj.box
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        label = f"#{obj.n}"
        draw.rectangle([x1, y1, x1 + 12 + 9 * len(label), y1 + 20], fill=color)
        draw.text((x1 + 4, y1 + 4), label, fill=(0, 0, 0))
    target.parent.mkdir(parents=True, exist_ok=True)
    out.convert("RGB").save(target, "JPEG", quality=85)
    return target
