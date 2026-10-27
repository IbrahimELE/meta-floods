"""Image pipeline (PLAN 5.1–5.3): ingest → segment (SAM 3.1) → assess (Muse Spark).

Location is independent of processing: an image can be fully assessed and
still wait for a pin; a pin later only publishes it – no new API calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageOps

from . import sam as samlib
from .api import call_with_retry
from .config import Settings
from .db import BudgetExceeded, Database, image_public, now_iso
from .schema import validate

GPS_IFD, EXIF_IFD = 0x8825, 0x8769
DATETIME_ORIGINAL, DATETIME = 0x9003, 0x0132
UNCERTAINTY_M = {"drone_oblique": 300, "satellite": 300, "unknown": 300, "drone_nadir": 50, "ground": 50}


class RejectedImage(ValueError):
    """Upload refused before decoding (size, pixels, format)."""


@dataclass
class ImageMeta:
    gps: tuple[float, float] | None
    captured_at: str | None


# ---------------------------------------------------------------------------- ingest
def read_metadata(image: Image.Image) -> ImageMeta:
    exif = image.getexif()
    gps = None
    try:
        g = exif.get_ifd(GPS_IFD)
        if g and 2 in g and 4 in g:
            def deg(dms, ref):
                d, m, s = (float(x) for x in dms)
                v = d + m / 60 + s / 3600
                return -v if ref in ("S", "W") else v
            gps = (deg(g[2], g.get(1, "N")), deg(g[4], g.get(3, "E")))
            if not (-90 <= gps[0] <= 90 and -180 <= gps[1] <= 180) or gps == (0.0, 0.0):
                gps = None
    except Exception:
        gps = None
    captured = None
    raw = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) or exif.get(DATETIME)
    if isinstance(raw, str):
        try:
            dt = datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S")
            # Camera clocks have no timezone; a time in the future is invalid → unknown (PLAN R3-2)
            if datetime(1990, 1, 1) < dt < datetime.now() + timedelta(days=1):
                captured = dt.isoformat()
        except ValueError:
            pass
    return ImageMeta(gps=gps, captured_at=captured)


def open_checked(data: bytes, s: Settings) -> Image.Image:
    """Size and pixel limits BEFORE full decoding (PLAN 5.5)."""
    if len(data) > s.max_bytes:
        raise RejectedImage(f"file too large ({len(data) / 1e6:.1f} MB > {s.max_bytes / 1e6:.0f} MB)")
    Image.MAX_IMAGE_PIXELS = s.max_pixels
    try:
        image = Image.open(io.BytesIO(data))       # reads the header only
    except Exception as exc:
        raise RejectedImage(f"not an image: {exc}") from exc
    if image.width * image.height > s.max_pixels:
        raise RejectedImage(f"too many pixels ({image.width}x{image.height})")
    if image.format not in ("JPEG", "PNG", "WEBP", "MPO"):
        raise RejectedImage(f"unsupported format {image.format}")
    try:
        image.load()
    except Exception as exc:
        raise RejectedImage(f"cannot decode image: {exc}") from exc
    return image


class Pipeline:
    def __init__(self, db: Database, settings: Settings, api):
        self.db, self.s, self.api = db, settings, api

    def ingest(self, incident_id: str, data: bytes, name: str) -> str | None:
        """Store one upload. Returns the image id, or None for a duplicate."""
        image = open_checked(data, self.s)
        meta = read_metadata(image)
        sha = hashlib.sha256(data).hexdigest()
        if self.db.one("SELECT id FROM images WHERE incident_id = ? AND sha256 = ?", (incident_id, sha)):
            return None
        self.db.reserve("image", self.s.budget_images)

        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((self.s.max_side, self.s.max_side))
        image_id = uuid.uuid4().hex[:16]
        path = self.s.images_dir / f"{image_id}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, "JPEG", quality=90)          # no EXIF in the stored copy

        location_state = "camera" if meta.gps else ("pending" if self.s.ai_locate else "needs_pin")
        with self.db.tx() as c:
            c.execute(
                """INSERT INTO images (id, incident_id, sha256, original_name, path, width, height,
                   captured_at, uploaded_at, camera_lat, camera_lon, location_state, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (image_id, incident_id, sha, name, str(path), image.width, image.height,
                 meta.captured_at, now_iso(), *(meta.gps or (None, None)), location_state, now_iso()),
            )
            if meta.gps:
                c.execute(
                    """INSERT INTO locations (image_id, kind, lat, lon, uncertainty_m, source_detail, created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (image_id, "camera_exif", *meta.gps, UNCERTAINTY_M["unknown"],
                     "EXIF GPS = camera position, not the objects", now_iso()),
                )
            row = c.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
            self.db.emit(c, incident_id, "image_added", image_public(row))
        return image_id

    # ------------------------------------------------------------------- processing
    def recover(self) -> int:
        """After a restart: running → queued (attempts counted); too many → failed."""
        rows = self.db.query("SELECT id, attempts FROM images WHERE processing_state = 'running'")
        for row in rows:
            if row["attempts"] >= self.s.max_attempts:
                self.db.update_image(row["id"], "image_updated", processing_state="failed",
                                     last_error="too many attempts (restarts)")
            else:
                self.db.update_image(row["id"], "image_updated", processing_state="queued")
        return len(rows)

    async def run_queue(self, incident_id: str | None = None, recover: bool = True) -> None:
        """Process everything queued (CLI / tests). The web server uses its own worker
        and calls recover() only once at startup."""
        if recover:
            self.recover()
        sql = "SELECT id FROM images WHERE processing_state = 'queued'"
        args: tuple = ()
        if incident_id:
            sql += " AND incident_id = ?"
            args = (incident_id,)
        ids = [r["id"] for r in self.db.query(sql + " ORDER BY uploaded_at", args)]
        semaphore = asyncio.Semaphore(self.s.image_workers)

        async def one(image_id: str) -> None:
            async with semaphore:
                await self.process_image(image_id)

        await asyncio.gather(*(one(i) for i in ids))

    def _reserve_call(self, image_id: str):
        def reserve() -> None:
            self.db.reserve("api_call", self.s.budget_api_calls)
            with self.db.tx() as c:
                c.execute("UPDATE images SET api_calls_used = api_calls_used + 1 WHERE id = ?", (image_id,))
        return reserve

    async def process_image(self, image_id: str) -> None:
        row = self.db.image(image_id)
        self.db.update_image(image_id, "image_updated", processing_state="running", stage="segment",
                             attempts=row["attempts"] + 1, last_error=None)
        try:
            objects = await self._segment(image_id, Path(row["path"]))
            self.db.update_image(image_id, "image_updated", stage="assess")
            await self._assess(image_id, Path(row["path"]), objects)
        except BudgetExceeded as exc:
            self.db.update_image(image_id, "image_updated", processing_state="failed", last_error=f"budget: {exc}")
            return
        except Exception as exc:  # noqa: BLE001 – every failure must become visible, not crash the batch
            stage = self.db.image(image_id)["stage"]
            self.db.update_image(image_id, "image_updated", processing_state="failed",
                                 last_error=f"{stage}: {type(exc).__name__}: {exc}"[:500])
            return
        self.db.update_image(image_id, "image_updated", processing_state="done", stage=None)
        self.maybe_publish(image_id)

    async def _segment(self, image_id: str, path: Path) -> list[samlib.SamObject]:
        image = Image.open(path)
        reserve = self._reserve_call(image_id)

        async def concept(c: str) -> list[samlib.SamObject]:
            text = await call_with_retry(lambda: self.api.segment(path, c), timeout=self.s.timeout_sam,
                                         delays=self.s.retry_delays, before_attempt=reserve)
            return samlib.to_objects(samlib.parse(text), c)

        found = [o for group in await asyncio.gather(*(concept(c) for c in self.s.concepts)) for o in group]
        found = samlib.merge_buildings(found, self.s.merge_iou)
        samlib.flag_flooded_roads(found, image.size)
        samlib.number(found)
        overlay = samlib.render(image, found, self.s.masks_dir / f"{image_id}_overlay.jpg")

        with self.db.tx() as c:
            c.execute("DELETE FROM objects WHERE image_id = ?", (image_id,))
            for o in found:
                c.execute(
                    """INSERT INTO objects (id, image_id, n, concept, box_json, sam_confidence, area_px, flood_overlap)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (f"{image_id}:{o.n}", image_id, o.n, o.concept, json.dumps(o.box),
                     o.confidence, o.area, o.flood_overlap),
                )
        self.db.update_image(image_id, "image_updated", overlay_path=str(overlay),
                             segmentation_state="objects" if found else "no_objects")
        return found

    @staticmethod
    def listing(objects: list[samlib.SamObject]) -> str:
        lines = []
        for o in objects:
            note = ""
            if o.flood_overlap:
                note = f" – {o.flood_overlap:.0%} of this mask lies under SAM's flood-water mask"
            lines.append(f"#{o.n}: {o.concept}{note}")
        return "\n".join(lines)

    async def _assess(self, image_id: str, path: Path, objects: list[samlib.SamObject]) -> None:
        overlay = Path(self.db.image(image_id)["overlay_path"])
        listing = self.listing(objects)
        ids = {o.n for o in objects}
        reserve = self._reserve_call(image_id)
        feedback = None
        for attempt in range(2):                     # 1 retry with the validation errors
            try:
                result, model = await call_with_retry(
                    lambda: self.api.assess(path, overlay, listing, feedback),
                    timeout=self.s.timeout_assess, delays=self.s.retry_delays, before_attempt=reserve)
                errors = validate(result, ids)
            except ValueError as exc:
                errors = [str(exc)]
            if not errors:
                break
            feedback = "; ".join(errors)[:1500]
        else:
            raise ValueError(f"invalid_output: {feedback}")
        self._store_assessment(image_id, result, model)

    def _store_assessment(self, image_id: str, result: dict, model: str) -> None:
        def nb(v):  # nullable bool → 1 / 0 / NULL
            return None if v is None else int(bool(v))
        with self.db.tx() as c:
            c.execute("DELETE FROM findings WHERE image_id = ?", (image_id,))
            for o in result["objects"]:
                c.execute(
                    """INSERT INTO findings (image_id, object_id, damage, passability, self_confidence,
                       evidence_text, model, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                    (image_id, f"{image_id}:{o['id']}", o["damage"], o["passability"], o["confidence"],
                     o["evidence"], model, now_iso()),
                )
            people = result["people"]
            c.execute(
                """INSERT INTO findings (image_id, object_id, hazards_json, people_visible, people_may_need_help,
                   evidence_text, model, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (image_id, None, json.dumps(result["hazards"]), nb(people["visible"]),
                 nb(people["may_need_help"]), result["scene"]["summary"], model, now_iso()),
            )
            c.execute("INSERT OR REPLACE INTO image_labels (image_id, labels_json, model) VALUES (?,?,?)",
                      (image_id, json.dumps(result["image_labels"]), model))
        self.db.update_image(image_id, None, scene_json=json.dumps(
            {**result["scene"], "location_clues": result["location_clues"]}),
            viewpoint=result["scene"]["viewpoint"])

    # ----------------------------------------------------------------- location / map
    def set_pin(self, image_id: str, lat: float, lon: float) -> None:
        """Human pin: confirms the location and publishes – never calls a model."""
        with self.db.tx() as c:
            c.execute(
                """INSERT INTO locations (image_id, kind, lat, lon, uncertainty_m, source_detail,
                   confirmed_by_human, created_at) VALUES (?,?,?,?,?,?,1,?)""",
                (image_id, "human_pin", lat, lon, 50, "placed by responder", now_iso()),
            )
            c.execute("INSERT INTO reviews (target_type, target_id, action, value_json, created_at) VALUES (?,?,?,?,?)",
                      ("location", image_id, "confirm", json.dumps({"lat": lat, "lon": lon}), now_iso()))
        self.db.update_image(image_id, "image_updated", location_state="confirmed")
        self.maybe_publish(image_id)

    def maybe_publish(self, image_id: str) -> bool:
        row = self.db.image(image_id)
        ok = row["processing_state"] == "done" and row["location_state"] in ("camera", "proposed", "confirmed")
        if ok and not row["published"]:
            self.db.update_image(image_id, "finding_published", published=1)
        return ok
