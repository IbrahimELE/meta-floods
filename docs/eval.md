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
