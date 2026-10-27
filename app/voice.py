"""Voice field reports: a responder records a short message at a map point.

Muse Voice Transcribe turns the recording into text; Muse Spark Open (Baseten)
extracts a structured observation from it (falls back to Muse Spark 1.3 when no
Baseten key is configured). A report is a HUMAN observation, so it is shown as
such – it is never mixed up with AI image findings.

Note: Muse Voice Transcribe lists 25 languages; Bosnian/Croatian/Serbian are not
among them, so reports should be spoken in English (or another listed language).
The extraction step answers in English and keeps the original transcript.
"""

from __future__ import annotations

import io
import json
import wave
from typing import Any

import httpx

from .api import final_text
from .config import Settings

ASR_URL = "https://api.meta.ai/v1/asr/transcribe"
ASR_MODEL = "muse-voice-transcribe-1.0"
MAX_WAV_BYTES = 8_000_000   # ~2.5 min at 24 kHz mono 16-bit

REPORT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "road_status", "people_need_help", "hazards", "place_mentioned"],
    "properties": {
        "summary": {"type": "string", "description": "one sentence in English"},
        "road_status": {"type": "string", "enum": ["blocked", "caution", "open", "not_mentioned"]},
        "people_need_help": {"type": ["boolean", "null"], "description": "null if not mentioned"},
        "hazards": {"type": "array", "items": {"type": "string", "enum": [
            "deep_water", "fast_current", "landslide", "collapse_risk", "downed_power_lines", "debris", "fire", "other"]}},
        "place_mentioned": {"type": "string", "description": "place names exactly as spoken, or empty"},
    },
}

EXTRACT_INSTRUCTIONS = """A rescue responder recorded this field report at a location they marked on the map.
Extract only what the speaker actually says. Do not add facts. If something is not mentioned use
"not_mentioned", null or an empty list. Answer in English; keep place names as spoken."""


OPEN_KEYS = """

Return ONLY a JSON object with these keys: summary (one English sentence describing what the speaker
reports), road_status (blocked|caution|open|not_mentioned), people_need_help (true|false|null),
hazards (list from: deep_water, fast_current, landslide, collapse_risk, downed_power_lines, debris, fire, other),
place_mentioned (string, empty if none)."""


def place_keywords(*texts: str | None) -> list[str]:
    """Place names from the incident name/region ("Zenica, Doboj, Odžak – BiH" → Zenica, Doboj, Odžak)."""
    import re
    words = re.findall(r"[A-ZČĆŽŠĐ][\wčćžšđ]+", " ".join(t for t in texts if t))
    stop = {"Floods", "Flood", "May", "July", "Bosnia", "Herzegovina", "And", "The", "Replay", "Eastern", "USA"}
    return list(dict.fromkeys(w for w in words if w not in stop))


def check_wav(data: bytes) -> tuple[int, float]:
    """Muse Voice Transcribe accepts mono 16-bit PCM WAV at 16 or 24 kHz."""
    if len(data) > MAX_WAV_BYTES:
        raise ValueError("recording too long (max ~2.5 minutes)")
    try:
        with wave.open(io.BytesIO(data)) as w:
            rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"not a WAV file: {exc}") from exc
    if channels != 1 or width != 2 or rate not in (16000, 24000):
        raise ValueError(f"need mono 16-bit WAV at 16/24 kHz, got {channels} ch, {width * 8} bit, {rate} Hz")
    return rate, frames / rate


def transcribe(api_key: str, wav: bytes, keywords: list[str] | None = None, timeout: float = 90.0) -> dict:
    """keywords bias recognition toward local place names (e.g. from the incident region)."""
    request: dict[str, Any] = {"model": ASR_MODEL, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
    if keywords:
        request["keywords"] = keywords[:50]
    with httpx.Client(timeout=timeout) as client:
        res = client.post(ASR_URL, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                          files={"request": (None, json.dumps(request), "application/json"),
                                 "audio": ("report.wav", wav, "audio/wav")})
    if res.status_code >= 400:
        raise RuntimeError(f"transcription failed ({res.status_code}): {res.text[:200]}")
    return res.json()


def extract(settings: Settings, meta_client, baseten_client, transcript: str) -> tuple[dict, str]:
    """Structured observation from the transcript. Returns (report, model)."""
    if baseten_client is not None:
        # On Baseten, schema-constrained decoding made Muse Spark Open fill fields with the schema's own
        # descriptions; plain JSON mode with the keys spelled out works well (tested 27.10.).
        response = baseten_client.chat.completions.create(
            model=settings.baseten_assess_model,
            messages=[{"role": "system", "content": EXTRACT_INSTRUCTIONS + OPEN_KEYS},
                      {"role": "user", "content": f"Transcript:\n{transcript}"}],
            response_format={"type": "json_object"},
            timeout=60,
        )
        raw, model = response.choices[0].message.content, settings.baseten_assess_model
    else:
        response = meta_client.responses.create(
            model=settings.meta_assess_model, instructions=EXTRACT_INSTRUCTIONS,
            input=f"Transcript:\n{transcript}", reasoning={"effort": "minimal"},
            text={"format": {"type": "json_schema", "name": "field_report", "schema": REPORT_SCHEMA}}, timeout=60)
        raw, model = final_text(response), settings.meta_assess_model
    report = json.loads(raw)
    report["hazards"] = sorted(set(report.get("hazards") or []))   # Open sometimes repeats items
    return validate_report(report), model


def validate_report(r: Any) -> dict:
    import jsonschema
    jsonschema.validate(r, REPORT_SCHEMA)
    return r
