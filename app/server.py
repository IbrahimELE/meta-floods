"""FastAPI backend (PLAN 5, 5.5): upload, snapshot, live events (SSE), pin, review.

Run locally:  uvicorn app.server:app --reload
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .api import ModelApi
from .config import Settings, settings
from .db import BudgetExceeded, Database, image_public, now_iso
from .pipeline import Pipeline, RejectedImage
from .priority import age_status, image_points, to_priority

STATIC = Path(__file__).parent / "static"
MAX_FILES = {"dev": 50, "sandbox": 5}


class Worker:
    """Picks up queued images continuously; at most `image_workers` in parallel."""

    def __init__(self, pipe: Pipeline):
        self.pipe = pipe
        self.wake = asyncio.Event()
        self.in_flight: set[str] = set()
        self.sem = asyncio.Semaphore(pipe.s.image_workers)
        self.task: asyncio.Task | None = None

    async def _one(self, image_id: str) -> None:
        try:
            async with self.sem:
                await self.pipe.process_image(image_id)
        finally:
            self.in_flight.discard(image_id)

    async def loop(self) -> None:
        self.pipe.recover()                       # only here: restart recovery (PLAN 5.2)
        while True:
            rows = self.pipe.db.query("SELECT id FROM images WHERE processing_state = 'queued' ORDER BY uploaded_at")
            for row in rows:
                if row["id"] not in self.in_flight:
                    self.in_flight.add(row["id"])
                    asyncio.create_task(self._one(row["id"]))
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass


# ----------------------------------------------------------------------------- models
class IncidentIn(BaseModel):
    name: str = Field(max_length=120)
    region: str | None = Field(default=None, max_length=200)
    as_of: str | None = None


class PinIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ReviewIn(BaseModel):
    action: str = Field(pattern="^(confirm|reject)$")


# ----------------------------------------------------------------------------- app
def create_app(pipe: Pipeline | None = None, *, start_worker: bool = True, allow_dev: bool | None = None) -> FastAPI:
    if pipe is None:
        db = Database(settings.db_path)
        api = ModelApi(settings, os.environ.get("MODEL_API_KEY"), os.environ.get("BASETEN_API_KEY"))
        pipe = Pipeline(db, settings, api)
    if allow_dev is None:
        allow_dev = os.environ.get("FH_ALLOW_DEV", "1") == "1"   # set 0 on the public deploy
    worker = Worker(pipe)
    db: Database = pipe.db

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if start_worker:
            worker.task = asyncio.create_task(worker.loop())
        yield
        if worker.task:
            worker.task.cancel()

    app = FastAPI(title="FirstHour", lifespan=lifespan)
    app.state.pipe, app.state.worker = pipe, worker

    # ------------------------------------------------------------------ access control
    def incident_for(incident_id: str, request: Request, write: bool) -> Any:
        inc = db.one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
        if inc is None:
            raise HTTPException(404, "incident not found")
        if inc["mode"] == "sandbox":
            token = request.cookies.get(f"fh_{incident_id}", "")
            if not token or hashlib.sha256(token.encode()).hexdigest() != inc["access_token_hash"]:
                raise HTTPException(403, "this sandbox belongs to another session")
        if inc["mode"] == "dev" and not allow_dev:
            raise HTTPException(403, "dev incidents are disabled on this server")
        if write and inc["mode"] == "demo_readonly":
            raise HTTPException(403, "the demo scenario is read-only – start your own sandbox to upload")
        return inc

    def image_for(image_id: str, request: Request, write: bool) -> Any:
        row = db.one("SELECT * FROM images WHERE id = ?", (image_id,))
        if row is None:
            raise HTTPException(404, "image not found")
        incident_for(row["incident_id"], request, write)
        return row

    # ------------------------------------------------------------------ incidents
    @app.post("/api/incidents")
    def create_incident(body: IncidentIn) -> dict:
        if not allow_dev:
            raise HTTPException(403, "use /api/sandbox")
        return {"id": db.create_incident(body.name, body.region, "dev", body.as_of)}

    @app.post("/api/sandbox")
    def create_sandbox(body: IncidentIn) -> JSONResponse:
        token = secrets.token_urlsafe(32)
        incident_id = db.create_incident(body.name, body.region, "sandbox", None,
                                         hashlib.sha256(token.encode()).hexdigest())
        response = JSONResponse({"id": incident_id})
        response.set_cookie(f"fh_{incident_id}", token, max_age=24 * 3600, httponly=True, samesite="lax")
        return response

    @app.get("/api/incidents")
    def list_incidents() -> list[dict]:
        rows = db.query("SELECT id, name, region_text, mode, as_of, created_at FROM incidents "
                        "WHERE mode IN ('demo_readonly'" + (", 'dev'" if allow_dev else "") + ") ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ images
    @app.post("/api/incidents/{incident_id}/images")
    async def upload(incident_id: str, request: Request, files: list[UploadFile] = File(...)) -> dict:
        inc = incident_for(incident_id, request, write=True)
        if len(files) > MAX_FILES.get(inc["mode"], 5):
            raise HTTPException(413, f"max {MAX_FILES.get(inc['mode'], 5)} images per request")
        results = []
        for f in files:
            data = await f.read(pipe.s.max_bytes + 1)
            try:
                image_id = await asyncio.to_thread(pipe.ingest, incident_id, data, f.filename or "upload.jpg")
                results.append({"name": f.filename, "image_id": image_id, "status": "queued" if image_id else "duplicate"})
            except RejectedImage as exc:
                results.append({"name": f.filename, "status": "rejected", "error": str(exc)})
            except BudgetExceeded as exc:
                results.append({"name": f.filename, "status": "rejected", "error": str(exc)})
        worker.wake.set()
        return {"results": results}

    @app.get("/api/images/{image_id}/photo")
    def photo(image_id: str, request: Request) -> FileResponse:
        return FileResponse(image_for(image_id, request, write=False)["path"], media_type="image/jpeg")

    @app.get("/api/images/{image_id}/overlay")
    def overlay(image_id: str, request: Request) -> FileResponse:
        row = image_for(image_id, request, write=False)
        if not row["overlay_path"]:
            raise HTTPException(404, "no overlay yet")
        return FileResponse(row["overlay_path"], media_type="image/jpeg")

    @app.get("/api/images/{image_id}")
    def image_detail(image_id: str, request: Request) -> dict:
        row = image_for(image_id, request, write=False)
        inc = db.one("SELECT * FROM incidents WHERE id = ?", (row["incident_id"],))
        return describe_image(row, inc, detail=True)

    @app.post("/api/images/{image_id}/pin")
    def pin(image_id: str, body: PinIn, request: Request) -> dict:
        image_for(image_id, request, write=True)
        pipe.set_pin(image_id, body.lat, body.lon)
        return {"ok": True}

    @app.post("/api/findings/{finding_id}/review")
    def review(finding_id: int, body: ReviewIn, request: Request) -> dict:
        row = db.one("SELECT * FROM findings WHERE id = ?", (finding_id,))
        if row is None:
            raise HTTPException(404, "finding not found")
        image = image_for(row["image_id"], request, write=True)
        with db.tx() as c:
            c.execute("INSERT INTO reviews (target_type, target_id, action, created_at) VALUES (?,?,?,?)",
                      ("finding", str(finding_id), body.action, now_iso()))
            db.emit(c, image["incident_id"], "finding_reviewed", {"finding_id": finding_id, "action": body.action,
                                                                  "image_id": image["id"]})
        return {"ok": True}

    # ------------------------------------------------------------------ map state
    def location_of(image_id: str) -> dict | None:
        rows = db.query("SELECT * FROM locations WHERE image_id = ? ORDER BY id DESC", (image_id,))
        for kind in ("human_pin", "camera_exif", "ai_scene_estimate"):
            for r in rows:
                if r["kind"] == kind:
                    return {"lat": r["lat"], "lon": r["lon"], "kind": kind, "uncertainty_m": r["uncertainty_m"],
                            "confirmed": bool(r["confirmed_by_human"]), "note": r["source_detail"]}
        return None

    def findings_of(image_id: str) -> list[dict]:
        rejected = {r["target_id"] for r in db.query(
            """SELECT target_id FROM reviews r1 WHERE target_type = 'finding' AND action = 'reject'
               AND id = (SELECT MAX(id) FROM reviews r2 WHERE r2.target_type = 'finding' AND r2.target_id = r1.target_id)""")}
        confirmed = {r["target_id"] for r in db.query(
            """SELECT target_id FROM reviews r1 WHERE target_type = 'finding' AND action = 'confirm'
               AND id = (SELECT MAX(id) FROM reviews r2 WHERE r2.target_type = 'finding' AND r2.target_id = r1.target_id)""")}
        out = []
        for f in db.query("""SELECT f.*, o.n, o.concept, o.box_json, o.flood_overlap FROM findings f
                             LEFT JOIN objects o ON o.id = f.object_id WHERE f.image_id = ? ORDER BY o.n""", (image_id,)):
            d = dict(f)
            d["rejected"] = str(f["id"]) in rejected
            d["confirmed"] = str(f["id"]) in confirmed
            out.append(d)
        return out

    def describe_image(row: Any, inc: Any, detail: bool = False) -> dict:
        d = image_public(row)
        d["location"] = location_of(row["id"])
        d["age"] = age_status(row["captured_at"], inc["as_of"])
        scene = json.loads(row["scene_json"]) if row["scene_json"] else None
        d["scene"] = scene
        findings = findings_of(row["id"]) if row["processing_state"] == "done" else []
        score = image_points(findings, scene, d["age"]) if findings else {"points": None, "assessable": False, "parts": []}
        d["points"], d["assessable"], d["points_parts"] = score["points"], score["assessable"], score["parts"]
        d["priority"] = to_priority(score["points"])
        objs = [f for f in findings if f["object_id"] and not f["rejected"]]
        d["summary"] = {
            "objects": len(objs),
            "damage": {k: sum(1 for f in objs if f["damage"] == k) for k in ("destroyed", "major", "minor", "no_damage", "unknown")},
            "roads_blocked": sum(1 for f in objs if f["passability"] == "impassable"),
            "roads_caution": sum(1 for f in objs if f["passability"] == "caution"),
        }
        if detail:
            d["findings"] = findings
            labels = db.one("SELECT labels_json FROM image_labels WHERE image_id = ?", (row["id"],))
            d["image_labels"] = json.loads(labels["labels_json"]) if labels else None
        return d

    @app.get("/api/incidents/{incident_id}/snapshot")
    def snapshot(incident_id: str, request: Request) -> dict:
        inc = incident_for(incident_id, request, write=False)
        last = db.one("SELECT COALESCE(MAX(seq), 0) s FROM events WHERE incident_id = ?", (incident_id,))["s"]
        rows = db.query("SELECT * FROM images WHERE incident_id = ? ORDER BY uploaded_at", (incident_id,))
        return {
            "incident": {k: inc[k] for k in ("id", "name", "region_text", "mode", "as_of")},
            "last_seq": last,
            "images": [describe_image(r, inc) for r in rows],
        }

    @app.get("/api/incidents/{incident_id}/events")
    async def events(incident_id: str, request: Request, after: int = 0) -> StreamingResponse:
        incident_for(incident_id, request, write=False)
        last = int(request.headers.get("last-event-id") or after)

        async def stream():
            nonlocal last
            idle = 0.0
            while not await request.is_disconnected():
                rows = db.query("SELECT * FROM events WHERE incident_id = ? AND seq > ? ORDER BY seq LIMIT 200",
                                (incident_id, last))
                for r in rows:
                    last = r["seq"]
                    yield f"id: {r['seq']}\nevent: {r['type']}\ndata: {r['payload_json']}\n\n"
                if rows:
                    idle = 0.0
                else:
                    idle += 0.5
                    if idle >= 15:
                        yield ": keep-alive\n\n"
                        idle = 0.0
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------------ frontend
    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> Any:
        page = STATIC / "index.html"
        return FileResponse(page) if page.exists() else HTMLResponse("<h1>FirstHour API</h1><p>See /docs</p>")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "queued": db.one("SELECT COUNT(*) n FROM images WHERE processing_state='queued'")["n"],
                "in_flight": len(worker.in_flight)}

    return app


app = create_app() if os.environ.get("FH_NO_APP") != "1" else None
