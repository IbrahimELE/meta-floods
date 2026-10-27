"""Deploy FirstHour on Modal (PLAN 5.5).

One container, one writer: the working SQLite DB lives on the container's local
disk; after every committed transaction a consistent snapshot is written to the
Modal Volume and the volume is committed before the request returns. Photos and
overlays are written straight to the volume. On start, the DB is restored from
the last snapshot; on the very first start the read-only demo is seeded.

Setup (once):
    pip install modal
    modal token new
    modal secret create firsthour-keys MODEL_API_KEY=... BASETEN_API_KEY=...
Deploy:
    modal deploy deploy/modal_app.py
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
VOL_PATH = "/vol"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(ROOT / "requirements.txt"))
    .add_local_dir(str(ROOT / "app"), "/root/app")
    .add_local_dir(str(ROOT / "data" / "demo"), "/root/seed/demo")
)
volume = modal.Volume.from_name("firsthour-data", create_if_missing=True)
app = modal.App("firsthour")


def seed_demo(data_dir: Path, snapshot: Path) -> None:
    """First start only: copy the demo scenario onto the volume as `demo_readonly`."""
    seed = Path("/root/seed/demo")
    if snapshot.exists() or not (seed / "firsthour.sqlite").exists():
        return
    for sub in ("images", "masks"):
        shutil.copytree(seed / sub, data_dir / sub, dirs_exist_ok=True)
    shutil.copy(seed / "firsthour.sqlite", snapshot)
    c = sqlite3.connect(snapshot)
    for col, sub in (("path", "images"), ("overlay_path", "masks")):
        for image_id, value in c.execute(f"SELECT id, {col} FROM images").fetchall():
            if value:
                c.execute(f"UPDATE images SET {col} = ? WHERE id = ?", (str(data_dir / sub / Path(value).name), image_id))
    c.execute("UPDATE incidents SET mode = 'demo_readonly'")
    c.commit()
    c.close()
    volume.commit()


@app.function(
    image=image,
    volumes={VOL_PATH: volume},
    secrets=[modal.Secret.from_name("firsthour-keys")],
    max_containers=1,            # exactly one writer (PLAN 5.5)
    min_containers=0,
    scaledown_window=900,
    timeout=3600,
    cpu=4.0,                     # SAM mask decoding runs in a process pool
    memory=4096,
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def web():
    data_dir = Path(VOL_PATH) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    snapshot = Path(VOL_PATH) / "firsthour.snapshot.sqlite"
    seed_demo(data_dir, snapshot)

    os.environ.update({
        "FH_DATA_DIR": str(data_dir),
        "FH_DB_PATH": "/tmp/firsthour/firsthour.sqlite",   # local working copy
        "FH_SNAPSHOT_PATH": str(snapshot),
        "FH_ALLOW_DEV": "0",                               # public: demo is read-only, uploads go to sandboxes
        "FH_NO_APP": "1",
    })
    from app.server import create_app  # imported after env is set
    return create_app(on_snapshot=volume.commit)
