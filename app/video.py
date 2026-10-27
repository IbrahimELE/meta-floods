"""Drone clips: SAM 3.1 tracks houses, roads and flood water through the video.

Why tracking matters for triage: a drone pass shows the same house in dozens of
frames. SAM 3.1 gives every object a stable id across frames, so the clip is
counted per object, not per frame, and a handful of keyframes that together
cover every tracked house go through the normal photo pipeline (SAM masks +
Muse Spark assessment) – no house is assessed fifty times.

Limits (Meta Model API): MP4/MOV with H.264/H.265; video tracks at most 16 objects
per frame, so counts are "at least" when a frame hits 16. Billing is per frame
(min 50), so clips are normalised to 5 fps, 1280 px, ≤ 30 s before sending.
"""

from __future__ import annotations

import base64
import io
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import asyncio
import secrets
from typing import Any, Callable

from meta_sam_parser import CompletedOutcome, video_segmentation_format
from PIL import Image, ImageDraw

from .db import now_iso
from .sam import COLORS, FALLBACK, local_mask

VIDEO_CONCEPTS = ("house", "road", "flood water")
FPS, WIDTH, MAX_SECONDS = 5, 1280, 30
MAX_UPLOAD_BYTES = 60_000_000
PER_FRAME_CAP = 16


@dataclass
class Track:
    concept: str
    object_id: int
    frames: dict[int, tuple] = field(default_factory=dict)     # frame -> (box, mask_record | None)

    @property
    def length(self) -> int:
        return len(self.frames)


# ------------------------------------------------------------------ ffmpeg helpers
def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=width,height,nb_read_packets:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    return {"width": int(s["width"]), "height": int(s["height"]), "frames": int(s.get("nb_read_packets") or 0),
            "duration": float(d["format"].get("duration") or 0)}


def normalize(src: Path, dst: Path, start: float = 0.0) -> dict:
    """Any video ffmpeg can read → H.264 MP4, 5 fps, 1280 px wide, ≤ 30 s, no audio."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(MAX_SECONDS), "-i", str(src),
                    "-vf", f"fps={FPS},scale='min({WIDTH},iw)':-2", "-an", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)],
                   check=True, capture_output=True, timeout=300)
    return probe(dst)


def frames(path: Path, size: tuple[int, int]):
    """Decoded RGB frames, in order."""
    w, h = size
    proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)   # stopping early = broken pipe
    try:
        while True:
            buf = proc.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                break
            yield Image.frombytes("RGB", (w, h), buf)
    finally:
        proc.stdout.close()
        proc.wait()


# ------------------------------------------------------------------ SAM 3.1
def track(meta_client, mp4: bytes, concept: str, timeout: float = 240) -> str:
    """One concept through the whole clip (streamed; frames arrive in order)."""
    url = "data:video/mp4;base64," + base64.b64encode(mp4).decode()
    parts = []
    with meta_client.responses.stream(
        model="sam-3.1", timeout=timeout,
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": concept}, {"type": "input_video", "video_url": url}]}],
        metadata={"include_confidence": "true", "mask_encoding": "one_bit"},
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                parts.append(event.delta)
    return "".join(parts)


def parse_tracks(text: str, concept: str, keep_masks: bool = True) -> list[Track]:
    if not text.strip():
        return []
    parser = video_segmentation_format().create_parser()
    parser.push(text if text.endswith("\n") else text + "\n")
    records = parser.finish(CompletedOutcome()).result.records
    tracks: dict[int, Track] = {}
    masks = {(r.frame.frame_index, r.object_id): r for r in records if r.kind == "mask"}
    for r in records:
        if r.kind != "box":
            continue
        f = r.frame.frame_index
        t = tracks.setdefault(r.object_id, Track(concept, r.object_id))
        t.frames[f] = ((round(r.left), round(r.top), round(r.right), round(r.bottom)),
                       masks.get((f, r.object_id)) if keep_masks else None)
    return sorted(tracks.values(), key=lambda t: t.object_id)


def track_index(text: str, concept: str) -> list[Track]:
    """Boxes per frame only (picklable, light) – runs in the decode process pool. The parser
    would decode every mask just to validate it; for counting and keyframes we only need the
    boxes, so validation is skipped here (the overlay renderer decodes and checks the masks)."""
    import meta_sam_parser._segmentation as seg
    original = seg.decode_mask_to_raster
    seg.decode_mask_to_raster = lambda mask: b""
    try:
        return parse_tracks(text, concept, keep_masks=False)
    finally:
        seg.decode_mask_to_raster = original


def summarize(tracks: dict[str, list[Track]]) -> dict:
    out = {}
    for concept, ts in tracks.items():
        per_frame = defaultdict(int)
        for t in ts:
            for f in t.frames:
                per_frame[f] += 1
        peak = max(per_frame.values(), default=0)
        out[concept] = {"tracked": len(ts), "max_in_one_frame": peak, "capped": peak >= PER_FRAME_CAP}
    return out


def pick_keyframes(tracks: dict[str, list[Track]], n_frames: int, k: int | None = None) -> list[int]:
    """Greedy cover: the fewest frames that together show every tracked house (falls back to
    roads / water if no houses were found); remaining slots are spread evenly, because the
    drone reaches ground later in the clip that the tracked objects may not cover."""
    k = k or min(4, max(1, n_frames // (5 * FPS)))          # about one keyframe per 5 s, at most 4
    pool = next((tracks[c] for c in ("house", "road", "flood water") if tracks.get(c)), [])
    if not pool:
        return sorted({0, n_frames // 2, max(0, n_frames - 1)})[:k]
    uncovered = {t.object_id for t in pool}
    chosen: list[int] = []
    while uncovered and len(chosen) < k:
        best = max(range(n_frames), key=lambda f: sum(1 for t in pool if t.object_id in uncovered and f in t.frames))
        gain = {t.object_id for t in pool if t.object_id in uncovered and best in t.frames}
        if not gain:
            break
        chosen.append(best)
        uncovered -= gain
    for f in (round(i * (n_frames - 1) / max(1, k - 1)) for i in range(k)):
        if len(chosen) >= k:
            break
        if all(abs(f - c) > n_frames // (2 * k) for c in chosen):
            chosen.append(f)
    return sorted(chosen)


# ------------------------------------------------------------------ overlay video
def frame_lines(text: str) -> dict[int, str]:
    """SAM's video output has one line per frame, each starting with `<Nf>`."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"<(\d+)f>", line)
        if m:
            out[int(m.group(1))] = line
    return out


def _frame_layer(lines: dict[str, str], size: tuple[int, int]) -> tuple[bytes, list]:
    """Runs in the decode process pool: one frame's masks → RGBA layer + house labels."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    labels = []
    for concept in sorted(lines, key=lambda c: {"flood water": 0, "road": 1, "house": 2}.get(c, 9)):
        for t in parse_tracks(lines[concept], concept):
            for box, mask in t.frames.values():
                if mask is not None:
                    local, origin = local_mask(mask)
                    color = COLORS.get(concept, FALLBACK)
                    layer.paste(Image.new("RGBA", local.size, (*color, 70 if concept == "flood water" else 95)), origin, local)
                if concept == "house":
                    labels.append((t.object_id, box))
    return layer.tobytes(), labels


def render(src: Path, dst: Path, size: tuple[int, int], texts: dict[str, str], pool=None) -> Path:
    """The clip with every tracked object's mask and each house's track id (H.264, plays in
    browsers). Mask decoding is pure Python, so frames are decoded in the process pool."""
    w, h = size
    per_concept = {c: frame_lines(t) for c, t in texts.items()}
    n = max((max(v, default=-1) for v in per_concept.values()), default=-1) + 1
    jobs = [{c: v[i] for c, v in per_concept.items() if i in v} for i in range(n)]
    layers = pool.map(_frame_layer, jobs, [size] * n, chunksize=4) if pool else map(_frame_layer, jobs, [size] * n)
    dst.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
    try:
        for frame, (layer, labels) in zip(frames(src, size), layers):
            out = Image.alpha_composite(frame.convert("RGBA"), Image.frombytes("RGBA", size, layer))
            draw = ImageDraw.Draw(out)
            color = COLORS["house"]
            for oid, (x1, y1, x2, y2) in labels:
                draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
                label = f"H{int(oid) + 1}" if str(oid).isdigit() else f"H{oid}"
                draw.rectangle([x1, y1, x1 + 10 + 8 * len(label), y1 + 18], fill=color)
                draw.text((x1 + 4, y1 + 3), label, fill=(0, 0, 0))
            enc.stdin.write(out.convert("RGB").tobytes())
    finally:
        enc.stdin.close()
        enc.wait(timeout=120)
    if enc.returncode:
        raise RuntimeError("ffmpeg could not encode the overlay video")
    return dst


def frame_jpeg(src: Path, size: tuple[int, int], index: int) -> bytes:
    for i, frame in enumerate(frames(src, size)):
        if i == index:
            buf = io.BytesIO()
            frame.save(buf, "JPEG", quality=92)
            return buf.getvalue()
    raise IndexError(index)


# ------------------------------------------------------------------ job (server + demo builder)
def register(db, settings, incident_id: str, data: bytes, name: str, start: float = 0.0,
             credit: str | None = None) -> tuple[str, dict]:
    """Store an uploaded clip normalised (5 fps, 1280 px, ≤ 30 s). Raises ValueError if unreadable."""
    video_id = secrets.token_hex(8)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    src = settings.videos_dir / f"{video_id}_upload"
    src.write_bytes(data)
    clip = settings.videos_dir / f"{video_id}.mp4"
    try:
        info = normalize(src, clip, start)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyError, IndexError) as exc:
        raise ValueError("could not read this video (MP4, MOV or WebM expected)") from exc
    finally:
        src.unlink(missing_ok=True)
    if info["frames"] < 5:
        raise ValueError("video too short")
    with db.tx() as c:
        c.execute("""INSERT INTO videos (id, incident_id, original_name, path, width, height, frames, seconds, credit,
                     created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (video_id, incident_id, name, str(clip), info["width"], info["height"], info["frames"],
                   info["duration"], credit, now_iso(), now_iso()))
        db.emit(c, incident_id, "video_updated", {"id": video_id, "status": "queued"})
    return video_id, info


def _update(db, video_id: str, **fields: Any) -> None:
    fields["updated_at"] = now_iso()
    with db.tx() as c:
        c.execute(f"UPDATE videos SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", (*fields.values(), video_id))
        inc = c.execute("SELECT incident_id FROM videos WHERE id = ?", (video_id,)).fetchone()[0]
        db.emit(c, inc, "video_updated", {"id": video_id, "status": fields.get("status")})


async def process(pipe, video_id: str, on_keyframes: Callable[[], Any] | None = None) -> None:
    """Track → keyframes into the photo pipeline → overlay video. Failures are shown on the clip."""
    from .pipeline import decode_pool
    db = pipe.db
    row = db.one("SELECT * FROM videos WHERE id = ?", (video_id,))
    clip, size = Path(row["path"]), (row["width"], row["height"])
    loop = asyncio.get_running_loop()
    try:
        _update(db, video_id, status="tracking")
        for _ in VIDEO_CONCEPTS:
            db.reserve("api_call", pipe.s.budget_api_calls)
        data = clip.read_bytes()
        texts = dict(zip(VIDEO_CONCEPTS, await asyncio.gather(
            *(asyncio.to_thread(track, pipe.api.meta, data, c) for c in VIDEO_CONCEPTS))))
        for c, t in texts.items():
            (pipe.s.videos_dir / f"{video_id}_{c.replace(' ', '_')}.txt").write_text(t)
        tracks = dict(zip(texts, await asyncio.gather(
            *(loop.run_in_executor(decode_pool(), track_index, t, c) for c, t in texts.items()))))
        keyframes = []
        for f in pick_keyframes(tracks, row["frames"]):
            jpeg = await asyncio.to_thread(frame_jpeg, clip, size, f)
            image_id = await asyncio.to_thread(pipe.ingest, row["incident_id"], jpeg,
                                               f"{row['original_name']} · {f / FPS:.1f} s")
            if image_id:
                if row["credit"]:
                    db.update_image(image_id, None, credit=row["credit"])
                keyframes.append({"frame": f, "seconds": f / FPS, "image_id": image_id})
        if on_keyframes:
            on_keyframes()
        _update(db, video_id, status="rendering", summary_json=json.dumps(summarize(tracks)),
                keyframes_json=json.dumps(keyframes))
        overlay = pipe.s.videos_dir / f"{video_id}_overlay.mp4"
        await asyncio.to_thread(render, clip, overlay, size, texts, decode_pool())
        _update(db, video_id, status="done", overlay_path=str(overlay))
    except Exception as exc:  # noqa: BLE001
        _update(db, video_id, status="failed", error=f"{type(exc).__name__}: {exc}"[:300])
