"""SQLite storage (PLAN 5.1). One process, one writer: every write goes through
`Database.tx()`, which holds a process-wide lock, so parallel workers never
interleave transactions. Every state change also appends an event (event_seq)
that the web layer streams over SSE."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    region_text TEXT,
    mode TEXT NOT NULL DEFAULT 'dev',           -- dev | demo_readonly | sandbox
    as_of TEXT,                                 -- fixed time for historical scenarios
    access_token_hash TEXT,                     -- sandbox: sha256 of the visitor's secret token
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incidents(id),
    sha256 TEXT NOT NULL,
    original_name TEXT,
    path TEXT NOT NULL,
    width INTEGER, height INTEGER,
    captured_at TEXT,                           -- NULL = unknown, never upload time
    uploaded_at TEXT NOT NULL,
    camera_lat REAL, camera_lon REAL,
    viewpoint TEXT,
    processing_state TEXT NOT NULL DEFAULT 'queued',   -- queued|running|done|failed
    stage TEXT,                                        -- ingest|segment|assess
    location_state TEXT NOT NULL DEFAULT 'pending',    -- pending|camera|proposed|confirmed|needs_pin
    segmentation_state TEXT NOT NULL DEFAULT 'pending',-- pending|objects|no_objects
    published INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    api_calls_used INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    overlay_path TEXT,
    scene_json TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (incident_id, sha256)
);
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id TEXT NOT NULL REFERENCES images(id),
    kind TEXT NOT NULL,                         -- camera_exif | ai_scene_estimate | human_pin
    lat REAL, lon REAL,
    uncertainty_m REAL,
    source_detail TEXT,
    confirmed_by_human INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS objects (
    id TEXT PRIMARY KEY,                        -- {image_id}:{n}, n = number on the overlay
    image_id TEXT NOT NULL REFERENCES images(id),
    n INTEGER NOT NULL,
    concept TEXT NOT NULL,
    box_json TEXT NOT NULL,
    sam_confidence REAL,
    area_px INTEGER,
    flood_overlap REAL                          -- roads only: share of mask under flood water
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id TEXT NOT NULL REFERENCES images(id),
    object_id TEXT,                             -- NULL = scene level
    damage TEXT, passability TEXT,
    hazards_json TEXT,
    people_visible INTEGER,                     -- NULL = cannot tell
    people_may_need_help INTEGER,               -- NULL = cannot tell
    self_confidence REAL,
    evidence_text TEXT,
    model TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS image_labels (
    image_id TEXT PRIMARY KEY REFERENCES images(id),
    labels_json TEXT NOT NULL,
    model TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,                  -- finding | location | zone
    target_id TEXT NOT NULL,
    action TEXT NOT NULL,                       -- confirm | reject | correct
    value_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS budget (
    day TEXT PRIMARY KEY,
    images_reserved INTEGER NOT NULL DEFAULT 0,
    api_calls_reserved INTEGER NOT NULL DEFAULT 0,
    agent_runs_reserved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL REFERENCES incidents(id),
    revision INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    locked INTEGER NOT NULL DEFAULT 0,             -- human lock freezes membership (PLAN 7.3)
    human_priority INTEGER,
    agent_delta INTEGER NOT NULL DEFAULT 0,        -- -1 | 0 | +1, valid only for agent_revision
    agent_revision INTEGER,
    agent_reason TEXT,
    agent_evidence_json TEXT,
    label TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS zone_members (
    zone_id INTEGER NOT NULL REFERENCES zones(id),
    image_id TEXT NOT NULL REFERENCES images(id),
    PRIMARY KEY (zone_id, image_id)
);
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    status TEXT NOT NULL,                          -- running | done | incomplete | failed
    steps INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES agent_runs(id),
    tool TEXT NOT NULL,
    args_json TEXT NOT NULL,
    result TEXT NOT NULL,                          -- applied | rejected:<reason> | read
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    kind TEXT NOT NULL,                            -- check | duplicate
    target_type TEXT NOT NULL,                     -- image | finding | zone
    target_ids_json TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',           -- open | resolved
    run_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    language TEXT NOT NULL,
    headline TEXT NOT NULL,
    body TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    run_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blockages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL REFERENCES incidents(id),
    way_id INTEGER,                                -- OSM way (informative)
    a_node INTEGER, b_node INTEGER,                -- the exact graph edge (PLAN 5.3, R2-6a)
    a_lat REAL NOT NULL, a_lon REAL NOT NULL, b_lat REAL NOT NULL, b_lon REAL NOT NULL,
    direction TEXT NOT NULL DEFAULT 'both',        -- both | a_to_b | b_to_a
    finding_id INTEGER,                            -- the AI finding it confirms, if any
    note TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_incident ON images(incident_id);
CREATE INDEX IF NOT EXISTS idx_events_incident ON events(incident_id, seq);
"""


def restore(snapshot: Path, path: Path) -> None:
    """Start from the last durable snapshot."""
    source = sqlite3.connect(snapshot)
    target = sqlite3.connect(path)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BudgetExceeded(Exception):
    """Daily global budget reached – the API call must not be made."""


class Database:
    def __init__(self, path: Path, snapshot: Path | None = None, on_snapshot=None):
        """`snapshot`: after every committed transaction a consistent copy is written
        there (SQLite backup API → temp file → atomic rename) and `on_snapshot()` is
        called (Modal: volume.commit()). Only then does tx() return, so the caller
        reports success only for durable changes (PLAN 5.5)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if snapshot is not None and snapshot.exists() and not path.exists():
            restore(snapshot, path)
        self.path = path
        self.snapshot = snapshot
        self.on_snapshot = on_snapshot
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._lock = threading.RLock()

    def _migrate(self) -> None:
        """Columns added after the first release of the schema."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(incidents)")}
        if "access_token_hash" not in cols:
            self._conn.execute("ALTER TABLE incidents ADD COLUMN access_token_hash TEXT")

    # ---- transactions -------------------------------------------------------------
    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Serialized write transaction. Durability hook (backup + volume commit,
        PLAN 5.5) is added at deploy time in `after_commit`."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self.after_commit()

    def after_commit(self) -> None:
        """Runs under the write lock, so snapshots never interleave (PLAN R3-2).
        Any failure propagates: the caller must not report success."""
        if self.snapshot is None:
            return
        self.snapshot.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.snapshot.with_suffix(".tmp")
        target = sqlite3.connect(tmp)
        try:
            self._conn.backup(target)
        finally:
            target.close()
        os.replace(tmp, self.snapshot)
        if self.on_snapshot:
            self.on_snapshot()

    def query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        rows = self.query(sql, args)
        return rows[0] if rows else None

    # ---- helpers -----------------------------------------------------------------
    @staticmethod
    def emit(conn: sqlite3.Connection, incident_id: str, type_: str, payload: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO events (incident_id, type, payload_json, created_at) VALUES (?,?,?,?)",
            (incident_id, type_, json.dumps(payload), now_iso()),
        )

    def create_incident(self, name: str, region_text: str | None = None, mode: str = "dev",
                        as_of: str | None = None, access_token_hash: str | None = None) -> str:
        incident_id = uuid.uuid4().hex[:12]
        with self.tx() as c:
            c.execute(
                """INSERT INTO incidents (id, name, region_text, mode, as_of, access_token_hash, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (incident_id, name, region_text, mode, as_of, access_token_hash, now_iso()),
            )
        return incident_id

    def update_image(self, image_id: str, event: str | None = None, **fields: Any) -> None:
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.tx() as c:
            c.execute(f"UPDATE images SET {cols} WHERE id = ?", (*fields.values(), image_id))
            if event:
                row = c.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
                self.emit(c, row["incident_id"], event, image_public(row))

    def image(self, image_id: str) -> sqlite3.Row:
        row = self.one("SELECT * FROM images WHERE id = ?", (image_id,))
        if row is None:
            raise KeyError(image_id)
        return row

    # ---- budget (PLAN 5.5): reserve BEFORE the API call, atomically ---------------
    def reserve(self, kind: str, limit: int, amount: int = 1) -> None:
        column = {"image": "images_reserved", "api_call": "api_calls_reserved",
                  "agent_run": "agent_runs_reserved"}[kind]
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self.tx() as c:
            c.execute("INSERT OR IGNORE INTO budget (day) VALUES (?)", (day,))
            used = c.execute(f"SELECT {column} FROM budget WHERE day = ?", (day,)).fetchone()[0]
            if used + amount > limit:
                raise BudgetExceeded(f"daily {kind} budget reached ({used}/{limit})")
            c.execute(f"UPDATE budget SET {column} = {column} + ? WHERE day = ?", (amount, day))


def image_public(row: sqlite3.Row) -> dict[str, Any]:
    """The image fields the UI needs (no file paths)."""
    keys = ("id", "incident_id", "original_name", "width", "height", "captured_at",
            "camera_lat", "camera_lon", "processing_state", "stage", "location_state",
            "segmentation_state", "published", "attempts", "last_error")
    return {k: row[k] for k in keys}
