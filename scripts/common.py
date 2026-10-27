"""Shared helpers for the day-1 API tests.

Every script in this folder imports from here, so the API key, base URL and
image encoding live in one place.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "samples"
OUTPUTS_DIR = ROOT / "outputs"

META_BASE_URL = "https://api.meta.ai/v1"
BASETEN_BASE_URL = "https://inference.baseten.co/v1"

# Model IDs from https://dev.meta.ai/docs/models
MUSE_SPARK = "muse-spark-1.3"
SAM = "sam-3.1"
# Hackathon-specific slug (participant guide: use -1026, not the docs' slug)
MUSE_SPARK_OPEN_BASETEN = "meta-models/muse-spark-open-1026"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

load_dotenv(ROOT / ".env")


def meta_client() -> OpenAI:
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        sys.exit(
            "MODEL_API_KEY is not set. Copy .env.example to .env and paste your "
            "key from dev.meta.ai."
        )
    # The OpenAI SDK does not read MODEL_API_KEY by itself, so pass it explicitly.
    return OpenAI(base_url=META_BASE_URL, api_key=key)


def baseten_client() -> OpenAI:
    key = os.environ.get("BASETEN_API_KEY")
    if not key:
        sys.exit("BASETEN_API_KEY is not set in .env.")
    return OpenAI(base_url=BASETEN_BASE_URL, api_key=key)


def image_to_data_url(path: Path) -> str:
    """Inline a local image as a data URL (limit: 50 MB per image)."""
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def pick_images(args: list[str], limit: int | None = None) -> list[Path]:
    """Images given on the command line, or else everything in samples/."""
    if args:
        paths = [Path(a) for a in args]
    else:
        paths = sorted(
            p for p in SAMPLES_DIR.rglob("*") if p.suffix.lower() in IMAGE_EXTENSIONS
        )
    missing = [p for p in paths if not p.exists()]
    if missing:
        sys.exit(f"Not found: {', '.join(map(str, missing))}")
    if not paths:
        sys.exit(
            "No images. Put a few flood/earthquake photos in samples/ "
            "(see docs/plan.md, 'Data') or pass paths as arguments."
        )
    return paths[:limit] if limit else paths


def out_path(name: str) -> Path:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    return OUTPUTS_DIR / name


def final_text(response) -> str:
    """Text of the LAST assistant message.

    With server-side tools (web_search) Muse Spark also emits short
    'commentary' messages between searches, and `response.output_text`
    concatenates all of them in front of the JSON. The final answer is the
    last message item.
    """
    messages = [item for item in response.output if getattr(item, "type", "") == "message"]
    if not messages:
        return response.output_text or ""
    parts = [c.text for c in messages[-1].content if getattr(c, "type", "") == "output_text"]
    return "".join(parts)
