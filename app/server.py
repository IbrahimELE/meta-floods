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
from .db import BudgetExceeded, Database, now_iso
from .pipeline import Pipeline, RejectedImage
from .agent import Agent, meta_caller
from .state import describe_image, incident_images, state_hash, zones_view
from .zones import ToolRejected, resolve_review, set_human_priority

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


class ZonePriorityIn(BaseModel):
    priority: int | None = Field(default=None, ge=1, le=5)


# ----------------------------------------------------------------------------- app
def create_app(pipe: Pipeline | None = None, *, start_worker: bool = True, allow_dev: bool | None = None,
               agent_factory=None) -> FastAPI:
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
    app.state.agent_tasks = set()

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
        return describe_image(db, row, inc, detail=True)

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
    @app.get("/api/incidents/{incident_id}/snapshot")
    def snapshot(incident_id: str, request: Request) -> dict:
        inc = incident_for(incident_id, request, write=False)
        last = db.one("SELECT COALESCE(MAX(seq), 0) s FROM events WHERE incident_id = ?", (incident_id,))["s"]
        _, images = incident_images(db, incident_id)
        return {
            "incident": {k: inc[k] for k in ("id", "name", "region_text", "mode", "as_of")},
            "last_seq": last,
            "images": images,
            "zones": zones_view(db, incident_id, images),
        }

    # ------------------------------------------------------------------ agent + zones
    def make_agent() -> Agent:
        if agent_factory:
            return agent_factory(db)
        if pipe.api.meta is None:
            raise HTTPException(503, "MODEL_API_KEY is not configured")
        return Agent(db, meta_caller(pipe.api.meta, pipe.s.meta_assess_model))

    @app.post("/api/incidents/{incident_id}/agent/run")
    async def run_agent(incident_id: str, request: Request) -> dict:
        incident_for(incident_id, request, write=True)
        if db.one("SELECT id FROM agent_runs WHERE incident_id = ? AND status = 'running'", (incident_id,)):
            raise HTTPException(409, "the agent is already working on this incident")
        try:
            db.reserve("agent_run", pipe.s.budget_agent_runs)
        except BudgetExceeded as exc:
            raise HTTPException(429, str(exc))
        agent = make_agent()
        app.state.agent_tasks.add(asyncio.create_task(asyncio.to_thread(agent.run, incident_id)))
        return {"started": True}

    @app.get("/api/incidents/{incident_id}/agent")
    def agent_state(incident_id: str, request: Request) -> dict:
        incident_for(incident_id, request, write=False)
        run = db.one("SELECT * FROM agent_runs WHERE incident_id = ? ORDER BY id DESC LIMIT 1", (incident_id,))
        actions = [dict(a) for a in db.query("SELECT * FROM agent_actions WHERE run_id = ? ORDER BY id", (run["id"],))] if run else []
        current = state_hash(zones_view(db, incident_id))
        briefings = []
        for lang in ("en", "bs"):
            b = db.one("SELECT * FROM briefings WHERE incident_id = ? AND language = ? ORDER BY id DESC LIMIT 1", (incident_id, lang))
            if b:
                briefings.append({**dict(b), "stale": b["state_hash"] != current})
        requests_ = [dict(r) for r in db.query(
            "SELECT * FROM review_requests WHERE incident_id = ? AND status = 'open' ORDER BY id", (incident_id,))]
        return {"run": dict(run) if run else None, "actions": actions, "briefings": briefings, "review_requests": requests_}

    @app.post("/api/zones/{zone_id}/priority")
    def zone_priority(zone_id: int, body: ZonePriorityIn, request: Request) -> dict:
        z = db.one("SELECT * FROM zones WHERE id = ?", (zone_id,))
        if z is None:
            raise HTTPException(404, "zone not found")
        incident_for(z["incident_id"], request, write=True)
        try:
            set_human_priority(db, z["incident_id"], zone_id, body.priority)
        except ToolRejected as exc:
            raise HTTPException(400, str(exc))
        return {"ok": True}

    @app.post("/api/review-requests/{request_id}/resolve")
    def resolve(request_id: int, request: Request) -> dict:
        r = db.one("SELECT * FROM review_requests WHERE id = ?", (request_id,))
        if r is None:
            raise HTTPException(404, "review request not found")
        incident_for(r["incident_id"], request, write=True)
        resolve_review(db, r["incident_id"], request_id)
        return {"ok": True}

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
