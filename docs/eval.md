# Evaluation log

## E4 – SAM 3.1 concept choice (27.10.2026, 6 smoke-set images, visual review)

| image | road | street | flooded road | paved road | building | house | damaged building |
|---|---|---|---|---|---|---|---|
| vt-flood__CAP0200 | 2 | 0 | 1 | 2 | **0** | 16 | 0 |
| vt-flood_CAP_4726 | 4 | 1 | 0 | 4 | 46 | 43 | 0 |
| vt-flood_DSC_5862 | 2 | 0 | 3 | 2 | 33 | 3 | 0 |
| vt-flood__CAP0696 | 5 | 0 | 0 | 4 | 30 | 36 | 0 |
| ar-storm_DSC_2126 | 2 | 1 | 0 | 2 | 74 | 85 | 0 |
| ca-storm__DSC0264 | 1 | 0 | 0 | 1 | 6 | 13 | 0 |

Findings (from the overlays, not only counts):
- `road` returns whole connected road networks as one mask (highway + ramps = 1 object), so low counts are fine. Keep `road`; `paved road` is equivalent, `street` misses most.
- `flooded road` segments flood water, not roads → drop. Instead: a road mask overlapping a `flood water` mask = deterministic "road under water" evidence for passability.
- `building` and `house` are complementary (`building` found 0 on one rural image where `house` found 16; `house` finds fewer large commercial buildings). Use both and merge overlapping boxes (IoU > 0.5).
- `damaged building` returns nothing → damage must come from Muse Spark, not SAM prompts.

**Decision:** concepts = `road`, `building`, `house` (merged), `bridge`, `flood water`.

## Backend smoke test – ar-storm_DSC_2126 (77 SAM objects)

| | Muse Spark 1.3 (Meta) | Muse Spark Open (Baseten) |
|---|---|---|
| objects assessed | 77/77 | 77/77 |
| damage counts | 37 none, 20 minor, 13 major, 1 destroyed, 6 unknown | 47 none, 10 minor, 10 major, 10 destroyed |
| scene / priority | storm, 5/5 | disaster_type `none`, priority **9/5** |
| time | – | 61.8 s |

LADI labels for this image: affected+minor+major, not destroyed, debris → 1.3 is closer.
Open broke enum/range constraints (structured output on Baseten is not enforced the same way) → server-side validation from PLAN 5.2 is required, and E1 decides the default backend.

## Geolocation smoke test – vt-flood_DSC_5862

Camera GPS 43.090, −72.450. Muse Spark + web_search (region "Vermont, USA"): "Richmond, VT" 44.405, −72.993, self-confidence 0.62 → **~150 km off** with a convincing but wrong chain of evidence. Supports PLAN 5.3 (AI location = suggestion only) and the E2 decision rule.

## Pipeline smoke run – 6 smoke-set images (27.10.2026)

`python -m app.cli` end to end (ingest → SAM 5 concepts → merge → Muse Spark 1.3 → DB): 6/6 `done`, all published with camera GPS. 15–88 objects per image.

Image-level labels vs LADI v2 (6 images × 6 classes): **27/36 agree**. Systematic miss: `buildings_affected_or_greater` (0 vs 1 on 4 flood images). In FEMA terms "affected" includes flood water reaching a building, not only visible structural damage → our definition was too narrow. Fixed the definition (semantic fix from the FEMA scale, not tuned on test data). Real numbers come from E1 on the separate test split.

Some assessments needed retries (up to 17 API calls for one image instead of 6): large images (50+ objects) hit the 90 s assess timeout → raised to 150 s.

## E1/E2 results

Evaluated 2026-10-27. Sources and frozen application hashes are in `eval/*_summary.json`; per-image results are in `eval/e1_predictions.csv` and `eval/e2_predictions.csv`.

### Dataset and method

LADI **v2**, seed 42: 40 tuning images from val, 100 unique test images from test. Identical repeated source CSV rows were deduplicated before sampling; conflicting duplicates would stop the run. Excluded every smoke URL and the entire event/mission/flight folder containing it. The same `A0001` name in a different event is a different flight.

After exclusion the eligible population has only 28 flood images out of 928; natural (proportional) sampling would give 3 flood images in 100. The test set is therefore **class-enriched**: for each class, random positives were added until it had 15 (or all available: flooding_structures 4, buildings_major_or_greater 8, roads_damage 6), then filled at random to 100 (seed 42). Result: 19 flood, 15 debris, 15 buildings-affected positives. **Prevalence is not natural**, so precision would be different in a real incident. Split provenance and source hashes: `eval/split_metadata.json`.

The unmodified app pipeline was copied to ignored `eval/.runtime/app` before evaluation so concurrent backend work could not change the measured code. `FH_DATA_DIR=data/eval`; separate incidents per assessment backend. Identical SAM responses were cached and reused between backends. No production database or app settings were changed.

### E1 — image-level assessment

Missing/failed predictions count as negative predictions and remain in the denominator. Zero-denominator P/R/F1 is reported as 0. Macro-F1 includes only labels with ≥10 positive test images; the same labels are used for both backends. This evaluates the separate `image_labels` output, not object-level damage, route safety or precise localization.

#### meta (n=100)

| Class | Positives | Precision | Recall | F1 | Nonanswers |
|---|---:|---:|---:|---:|---:|
| flooding_any | 19 | 0.607 | 0.895 | 0.723 | 0 |
| flooding_structures | 4 | 1.000 | 0.500 | 0.667 | 0 |
| buildings_affected_or_greater | 15 | 0.833 | 1.000 | 0.909 | 0 |
| buildings_major_or_greater | 8 | 0.583 | 0.875 | 0.700 | 0 |
| roads_damage | 6 | 1.000 | 0.167 | 0.286 | 0 |
| debris_any | 15 | 0.577 | 1.000 | 0.732 | 0 |

Macro-F1: **0.788** (flooding_any, buildings_affected_or_greater, debris_any).
Parseable JSON: 100.0% of 100 assessment attempts. First-response schema/semantic validity: 100.0%. Final valid pipeline output: 100.0% of images.
Assessment p50 / p95: **11.263 / 23.131 s**. Timing sums assessment attempts for successful images (including corrective retries), excludes SAM and backoff; failures are separately counted above. This is E1 backend timing, not E3 end-to-end latency.

#### baseten (n=100)

| Class | Positives | Precision | Recall | F1 | Nonanswers |
|---|---:|---:|---:|---:|---:|
| flooding_any | 19 | 0.607 | 0.895 | 0.723 | 0 |
| flooding_structures | 4 | 0.500 | 0.500 | 0.500 | 0 |
| buildings_affected_or_greater | 15 | 0.714 | 1.000 | 0.833 | 0 |
| buildings_major_or_greater | 8 | 0.467 | 0.875 | 0.609 | 0 |
| roads_damage | 6 | 0.667 | 0.333 | 0.444 | 0 |
| debris_any | 15 | 0.441 | 1.000 | 0.612 | 0 |

Macro-F1: **0.723** (flooding_any, buildings_affected_or_greater, debris_any).
Parseable JSON: 98.1% of 103 assessment attempts. First-response schema/semantic validity: 97.0%. Final valid pipeline output: 100.0% of images.
Assessment p50 / p95: **21.133 / 41.359 s**. Timing sums assessment attempts for successful images (including corrective retries), excludes SAM and backoff; failures are separately counted above. This is E1 backend timing, not E3 end-to-end latency.

**Backend decision: `meta`**. Checks: `{"full_comparable_run": true, "macro_f1": false, "valid_json": true, "schema_valid": true, "latency": false}`. Provisional: False.
In addition to the plan’s JSON/F1/latency conditions, promotion requires ≥98% final schema-valid pipeline outputs. A pilot cannot promote a backend. Label definitions for non-building classes are operational interpretations as documented in PLAN.md.

### E2 — web-assisted camera geolocation

Random seed 42; 40 attempted images selected from 100 GPS-bearing test images. Fresh random filenames and re-encoded pixel-only JPEGs remove EXIF/XMP/comments; the API receives no source filename, URL, GPS or image ID. Ground truth is **camera GPS**, not the photographed object.
Region priors are assigned by event, not per-image GPS: US state names, with a broader Florida/Georgia/South Carolina prior for Hurricane Idalia. The baseline uses fixed approximate regional centers in `eval/run_e2.py`. The multi-state exception avoids leaking the target state from GPS. Web search can recognize public images, so this is explicitly web-assisted performance.

Coverage: **5/40 (12.5%)**.

| Method | Median km | p90 km | All attempts ≤1 km | All attempts ≤5 km |
|---|---:|---:|---:|---:|
| model | 5.007 | 20.814 | 0.0% | 5.0% |
| baseline | 124.721 | 205.665 | 0.0% | 0.0% |

Distance quantiles use coordinate answers only; within-distance percentages use **all attempted images**, including abstentions and API/parse failures.
**Geolocation decision: `keep_disabled`; recommended `FH_AI_LOCATE=0`** (threshold: at least 30% of all 40 attempts within 5 km). Provisional: False. No configuration was modified.

### Cost and reproducibility

Total usage-based estimate plus conservative reservations for unresolved calls: **$6.592**, shared stop threshold $20. Not a provider invoice. 
Rates checked 2026-10-27: [Meta pricing](https://dev.meta.ai/docs/pricing-rate-limits), [Baseten Muse Spark Open](https://www.baseten.co/library/muse-spark-open/). SAM $0.0025/image request; input/output $1.25/$4.25 per million tokens, ignoring cache discounts; search $0.0025/query. Request output caps: E1 12,000 tokens, E2 6,000 tokens and at most 5 tool calls. Reservations remain charged after uncertain failures.

Run instructions: `eval/README.md`. Raw responses, database, source-label CSV copies, resized EXIF images, blinded images and SAM cache remain under ignored `data/eval/`; credentials are never exported. `eval/NOTES_FOR_CLAUDE.md` records integration notes.

### Note: road damage misses (Claude, 27.10.)

Looked at the 5 `roads_damage` positives that Muse Spark 1.3 missed. They are subtle at this altitude: a farm road with small washouts, a landslide scarp next to (not on) a road, roads partly hidden by trees. LADI's `roads_damage` is broad (any visible damage near/at a road); our per-object `passability` asks a different question (can a rescue vehicle use the visible part). Not tuned on the test set; for the product, road status comes from passability + SAM flood-water overlap + human confirmation, not from this image label.

## E3 – end-to-end speed (27.10.2026)

26 photos (Eastern Kentucky floods) uploaded in one request through the HTTP API; time from upload until each photo is fully assessed (`eval/run_e3.py`, `eval/e3_summary.json`), on a 2-core machine:

| | First run | Process pool | + masks decoded once (27.10. late) |
|---|---:|---:|---:|
| first photo on the map | 68 s | 19 s | **15 s** |
| p50 / p95 per photo (incl. queueing behind the batch) | 169 / 214 s | 80 / 137 s | **50 / 88 s** |
| whole batch on the map | 217 s | 150 s | **96 s** |

Plan targets (PLAN 3): first photo < 30 s ✓, 30-photo batch < 3 min ✓ (26 photos).
Cause of the first result: a single SAM call takes 1–3 s, but SAM's mask codec is pure Python (~10 s of CPU for 150 masks per photo, decoded twice by the parser). In threads this serialized on the GIL across parallel photos. Fix: decode in a process pool, request `one_bit` masks, 4 photos in parallel so the first ones finish sooner. Deploy uses 4 CPUs.
Second fix: the parser decodes every mask once only to validate it and discards the raster; we cache that
result and reuse it for the overlay (`app/sam.py`), so each mask is decoded once.

## Drone clip and voice report (27.10.2026, browser tests with real models)

| | Measured |
|---|---|
| Drone clip, 20 s at 5 fps (100 frames), 3 concepts tracked in parallel – upload → counts shown | **16 s** |
| … → overlay video with tracks ready (2 cores, while the 4 keyframes are assessed) | 125 s |
| Tracked: houses / roads / flood-water areas | ≥ 16 (per-frame cap) / 2 / 2 |
| Keyframes picked (one per ~5 s; first one covers all 16 tracked houses) | 4 |
| Voice report, 13.5 s English recording → transcript + structured report on the map | **7 s** |
| Extraction with Muse Spark Open (JSON mode), 3 test transcripts | 3–7 s, all fields valid |

Tests: `tests/e2e_video.js`, `tests/e2e_voice.js` (the voice test uses synthetic speech, espeak-ng).
Cost per clip: 3 × 100 frames × $0.20 / 1000 = $0.06 plus 4 photo assessments.
