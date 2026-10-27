# Meta Model API – notes (checked Oct 26, 2026)

Source: https://dev.meta.ai/docs (models, quickstart, sam/*, image-understanding,
structured-output, tool-calling, reasoning, pricing-rate-limits).

## Basics

- Base URL: `https://api.meta.ai/v1` (OpenAI-compatible). Auth: `Authorization: Bearer <key>`.
- Key env var: `MODEL_API_KEY`. The OpenAI SDK does **not** read it automatically,
  so pass `api_key=` explicitly.
- Python: `pip install openai`, then `OpenAI(base_url=..., api_key=...)`.
- Recommended endpoint: **Responses API** (`client.responses.create`). Chat Completions
  and an Anthropic-style Messages API also work.

## Models

| Model ID | In → Out | Notes |
|---|---|---|
| `muse-spark-1.3` | text, image, video, audio, PDF → text | 1M context. Tool calling, structured output, web-search grounding. Recommended. |
| `muse-spark-1.3-contributor` | same | ~10x cheaper, but Meta may train on your data. Don't send citizen photos there. |
| `sam-3.1` | text prompt / boxes / points + image or video → boxes + masks | Tracks objects across video frames. |
| `muse-image-1.0` | text, image → image | Not needed for us. |
| Muse Spark Open | open weights, not on Model API | Via Baseten / Modal / Fireworks. Baseten slug for the hackathon: `meta-models/muse-spark-open-1026`, base URL `https://inference.baseten.co/v1`, Chat Completions. |

## Pricing (rough budget: $150 Meta credits)

- Muse Spark 1.3: $1.25 / 1M input, $4.25 / 1M output. A ~1280px image is ~1.3–1.5k
  tokens, so one image + overlay is ~3k input tokens ≈ $0.004. Reasoning tokens bill as output.
- SAM 3.1: **$2.50 per 1,000 image requests**; video $0.20 per 1,000 frames (min 50 frames).
  4 concepts × 100 photos = 400 requests ≈ $1.
- Rate limits (per team): Muse Spark 3,000 RPM / 4M TPM; SAM 3,000 RPM.

→ Budget isn't a real constraint; we can process hundreds of photos.

## SAM 3.1

- Request: `model="sam-3.1"`, input = one user message with `input_text` (the concept)
  + `input_image` (`image_url` = URL or data URL) or `input_video`.
- **One concept per request.** "building, road" or "building and road" does NOT give two
  concepts → one request per concept (scripts/01 does this).
- Text prompt = short concrete noun phrase ("collapsed building" may or may not work
  better than "building" – test it).
- Or prompt with boxes/points: up to 16 objects per request
  (`meta_sam_parser.build_object_prompt`). Never mix with a noun phrase.
- `metadata` (string values!): `include_confidence: "true"` adds `c` (0–1);
  `mask_encoding: "lossless"` (default) or `"one_bit"`;
  `propagation_direction` for video box/point prompts.
- No confidence threshold param – filter in our code.
- Output: `output_text` with special tokens, one line per frame:
  `<0f>0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..;c=..|><|mask;x=0;y=0;data=H,W,~<base85>|>,1<|box...`
  Boxes in source pixels, half-open. Masks are **box-local** (parser gives `bounds`).
  Object ids are stable across video frames but not dense – key by id.
- Empty `output_text` = nothing found.
- Streaming (`stream=True`) recommended for video; non-streaming fine for images.
- Parser: `pip install meta-sam-parser` → `image_segmentation_format()`,
  `video_segmentation_format()`, `parse_responses_stream()` (async, for streams),
  `decode_mask_to_raster / _rle / _svg_path`. JS: `@meta-sam/parser`, plus
  `@meta-sam/graphics` (canvas overlays) and `@meta-sam/react` – useful for the web UI.
  Verified locally: the parser handles the documented sample output.

## Images (Muse Spark)

- Responses: `{"type": "input_image", "image_url": "<url or data URL>"}` or `file_id`.
- Up to **50 images per request**, 50 MB inline per image, jpeg/png/gif/webp.
- Images only in `user` messages.

## Structured output

- Responses API: `text={"format": {"type": "json_schema", "name": ..., "schema": ...}}`
  (NOT `response_format`, that's Chat Completions).
- Output is always constrained to the schema. `strict: true` only adds server-side
  schema validation (needs additionalProperties:false + all properties required).
- No recursive schemas, max depth 10.

## Tool calling / agent

- Tools: `{"type": "function", "name", "description", "parameters"}` (flat, no `function` key).
- Model returns `function_call` items (`name`, `arguments` JSON string, `call_id`).
  Send back `{"type": "function_call_output", "call_id", "output"}` with
  `previous_response_id`. Parallel calls on by default.
- Built-in server-side tools: `{"type": "web_search"}`, `tool_search`. Can be mixed
  with our own functions. `tool_choice` must be `"auto"`.
- Validate arguments – they're not guaranteed to match the schema.

## Reasoning

- Responses: `reasoning={"effort": "minimal"|"low"|"medium"|"high"|"xhigh"|"max"}`
  (`none` → 400). Higher = slower and more output tokens.
- Use `low` for per-image assessment (many calls), `high` for the agent's planning.

## AUP points that shape the design

- Human oversight for consequential actions; disclose limitations → responder confirms,
  UI shows "AI estimate – verify on site".
- No identifying people / facial recognition → only "people visible / may need help".
- Don't present outputs as human-generated; keep Meta provenance labels.
- No military/war use cases.

## Learned while building (Oct 27)

- **Agent:** `previous_response_id` can fail with "referenced response not found or expired" → resend
  the full input history each turn (that is what `app/agent.py` does).
- **web_search + JSON:** `output_text` also contains commentary messages → parse the last message only.
- **SAM video** (`input_video`: `video_url` URL/data URL or `file_id`): MP4/MOV, H.264/H.265/MPEG-4 only
  (no WebM/VP9), ≤ 15,000 frames, **≤ 16 tracked objects per frame**, frames streamed in order for concept
  prompts. A 100-frame 1280×720 clip takes 8–12 s per concept. Object ids are strings.
- **SAM parser speed:** it decodes every mask to validate it and drops the raster; cache that decode and
  reuse it (masks decoded once → E3 batch 150 s → 96 s). For box-only indexing, skip validation.
- **Muse Voice Transcribe:** `POST /v1/asr/transcribe`, multipart `request` (JSON) + `audio` (WAV, mono
  16-bit PCM at 16/24 kHz, ≤ 10 min, body ≤ 32 MB). `request` needs `model: "muse-voice-transcribe-1.0"`,
  **`audioEncoding: "WAV"` (required)**, optional `mode` (PUSH_TO_TALK / ENDPOINTING / DIARIZATION),
  `keywords` (bias toward names), `languageBias`. Response `{transcript, turns, audioDurationMs}`.
  25 languages; Bosnian/Croatian/Serbian not listed. ~3 s for a 13 s clip.
- **Muse Spark Open on Baseten:** `response_format` json_schema gave poor output (fields filled with the
  schema's descriptions, enums violated); `{"type": "json_object"}` + keys spelled out in the system
  prompt works well (3–7 s).
- **Wikimedia Commons** rate-limits this cloud container (429, retry-after 600) → download on the user's
  computer and stage the files.
