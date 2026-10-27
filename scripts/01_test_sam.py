"""Step 1: segment buildings, roads, bridges and flood water with SAM 3.1.

SAM 3.1 takes ONE concept per request (commas/"and" do not split), so we send
one request per concept. Cost: $2.50 per 1,000 images per request, so 4
concepts x 10 photos is about $0.10.

For every image this writes to outputs/:
  <name>_sam.png    colored masks + numbered boxes (also the input for step 2)
  <name>_sam.json   one entry per object: id, concept, box, confidence, area

    python scripts/01_test_sam.py                      # everything in samples/
    python scripts/01_test_sam.py samples/a.jpg --concepts building "flood water"
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from meta_sam_parser import (
    CompletedOutcome,
    decode_mask_to_raster,
    image_segmentation_format,
    video_segmentation_format,
)
from PIL import Image, ImageDraw, ImageOps

from common import SAM, image_to_data_url, meta_client, out_path, pick_images

DEFAULT_CONCEPTS = ["building", "road", "bridge", "flood water"]
COLORS = {  # RGBA overlay colors per concept
    "building": (255, 99, 71, 110),
    "road": (65, 105, 225, 110),
    "bridge": (255, 215, 0, 130),
    "flood water": (0, 191, 255, 90),
}
FALLBACK_COLOR = (186, 85, 211, 110)


def segment(client, image_path: Path, concept: str) -> str:
    """One SAM request; returns the raw special-token output text."""
    response = client.responses.create(
        model=SAM,
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": image_to_data_url(image_path)},
                ],
            }
        ],
        metadata={"include_confidence": "true"},  # metadata values are strings
    )
    return response.output_text or ""


def parse_sam_output(text: str):
    """Parse SAM's wire format into box/mask records.

    Lines look like `<0f>0<|box;...|><|mask;...|>,1<|box;...|>...`. Anything
    the parser can't read comes back as a "text" record, which we drop here.
    Image format first; video format as a fallback.
    """
    if not text.strip():
        return [], []
    result = None
    for make_format in (image_segmentation_format, video_segmentation_format):
        parser = make_format().create_parser()
        parser.push(text if text.endswith("\n") else text + "\n")
        result = parser.finish(CompletedOutcome()).result
        if any(r.kind == "box" for r in result.records):
            break
    diagnostics = list(result.diagnostics) if result else []
    records = [r for r in (result.records if result else ()) if r.kind in ("box", "mask")]
    return records, diagnostics


def objects_from_records(records, concept: str) -> list[dict]:
    boxes = {r.object_id: r for r in records if r.kind == "box"}
    masks = {r.object_id: r for r in records if r.kind == "mask"}
    objects = []
    for object_id, box in boxes.items():
        mask_record = masks.get(object_id)
        objects.append(
            {
                "sam_object_id": object_id,
                "concept": concept,
                "box": [round(box.left), round(box.top), round(box.right), round(box.bottom)],
                "confidence": box.confidence,
                "_mask": mask_record,
            }
        )
    return objects


def paste_mask(canvas: Image.Image, mask_record, color) -> int:
    """Draw one box-local mask onto the overlay; returns its pixel area."""
    mask = mask_record.mask
    raster = decode_mask_to_raster(mask)  # row-major bytes of 0/1, width*height
    local = Image.frombytes("L", (mask.width, mask.height), bytes(raster)).point(
        lambda v: 255 if v else 0
    )
    b = mask_record.bounds
    left, top = round(b.left), round(b.top)
    size = (max(1, round(b.right) - left), max(1, round(b.bottom) - top))
    if local.size != size:
        local = local.resize(size, Image.NEAREST)
    fill = Image.new("RGBA", size, color)
    canvas.paste(fill, (left, top), local)
    return local.histogram()[255]


def render(image_path: Path, objects: list[dict], target: Path | None = None) -> Path:
    base = ImageOps.exif_transpose(Image.open(image_path)).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for obj in objects:
        color = COLORS.get(obj["concept"], FALLBACK_COLOR)
        if obj["_mask"] is not None:
            obj["mask_area_px"] = paste_mask(overlay, obj["_mask"], color)
    image = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(image)
    for obj in objects:
        color = COLORS.get(obj["concept"], FALLBACK_COLOR)[:3]
        x1, y1, x2, y2 = obj["box"]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        label = f"#{obj['id']}"
        draw.rectangle([x1, y1, x1 + 12 + 9 * len(label), y1 + 20], fill=color)
        draw.text((x1 + 4, y1 + 4), label, fill=(0, 0, 0))
    target = target or out_path(f"{image_path.stem}_sam.png")
    image.convert("RGB").save(target)
    return target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*")
    ap.add_argument("--concepts", nargs="+", default=DEFAULT_CONCEPTS)
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    client = meta_client()
    for image_path in pick_images(args.images, args.limit):
        print(f"\n=== {image_path.name}")
        objects: list[dict] = []
        for concept in args.concepts:
            started = time.perf_counter()
            text = segment(client, image_path, concept)
            records, diagnostics = parse_sam_output(text)
            found = objects_from_records(records, concept)
            print(
                f"  {concept:<12} {len(found):>3} objects  "
                f"{time.perf_counter() - started:5.1f}s"
                + (f"  ({len(diagnostics)} parser warnings)" if diagnostics else "")
            )
            for d in diagnostics[:3]:
                print(f"     ! {d.code}: {d.message}")
            if text and not records:
                print("     raw output start:", text[:200])
            objects.extend(found)

        for number, obj in enumerate(objects, start=1):
            obj["id"] = number  # one id per image, shared with the overlay labels
        overlay_path = render(image_path, objects)
        for obj in objects:
            obj.pop("_mask")
        json_path = out_path(f"{image_path.stem}_sam.json")
        json_path.write_text(
            json.dumps({"image": str(image_path), "objects": objects}, indent=2)
        )
        print(f"  -> {overlay_path.name}, {json_path.name}")


if __name__ == "__main__":
    main()
