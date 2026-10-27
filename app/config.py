"""Settings in one place. Values can be overridden with environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("FH_DATA_DIR", ROOT / "data")))

    # Models (docs/api-notes.md)
    meta_base_url: str = "https://api.meta.ai/v1"
    baseten_base_url: str = "https://inference.baseten.co/v1"
    sam_model: str = "sam-3.1"
    meta_assess_model: str = "muse-spark-1.3"
    baseten_assess_model: str = "meta-models/muse-spark-open-1026"
    assess_backend: str = field(default_factory=lambda: os.environ.get("ASSESS_BACKEND", "meta"))
    assess_effort: str = "low"

    # SAM concepts – chosen in E4 (docs/eval.md). building + house are merged.
    concepts: tuple[str, ...] = ("road", "building", "house", "bridge", "flood water")
    merge_iou: float = 0.5
    road_flood_overlap: float = 0.15  # share of a road mask under flood water to flag it

    # AI geolocation stays off until E2 says it is good enough (PLAN 5.3, 6.2)
    ai_locate: bool = field(default_factory=lambda: os.environ.get("FH_AI_LOCATE", "0") == "1")

    # Image validation (PLAN 5.5)
    max_bytes: int = 15_000_000
    max_pixels: int = 40_000_000
    max_side: int = 1600

    # Concurrency, retries, timeouts (PLAN 5.2)
    image_workers: int = _int("FH_IMAGE_WORKERS", 4)   # first results sooner; decoding is CPU-bound
    max_attempts: int = 3                 # per image (restart recovery)
    retry_delays: tuple[float, ...] = (2.0, 8.0, 30.0)  # per API call
    timeout_sam: float = 60.0
    timeout_assess: float = 150.0  # 50+ objects can take >90 s
    timeout_locate: float = 90.0

    # Global daily budget, shared by everyone (PLAN 5.5)
    budget_images: int = _int("FH_BUDGET_IMAGES", 150)
    budget_api_calls: int = _int("FH_BUDGET_API_CALLS", 1500)
    budget_agent_runs: int = _int("FH_BUDGET_AGENT_RUNS", 30)

    # Durability (PLAN 5.5): working DB on local disk, consistent snapshot after every commit
    db_override: str | None = field(default_factory=lambda: os.environ.get("FH_DB_PATH"))
    snapshot_path: str | None = field(default_factory=lambda: os.environ.get("FH_SNAPSHOT_PATH"))

    @property
    def db_path(self) -> Path:
        return Path(self.db_override) if self.db_override else self.data_dir / "firsthour.sqlite"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def masks_dir(self) -> Path:
        return self.data_dir / "masks"

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"


settings = Settings()
