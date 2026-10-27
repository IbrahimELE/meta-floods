# Data sources

Only data we have the right to use. Every photo shown in the demo or the video is listed here.

| Use | Source | License / terms | Attribution |
|---|---|---|---|
| Development, evaluation (E1–E3), smoke tests | LADI v2 – Low Altitude Disaster Imagery, labels `Labels/v2/*`, images from the Civil Air Patrol (`fema-cap-imagery`) | CC BY 4.0 (registry.opendata.aws/ladi) | "LADI v2, MIT Lincoln Laboratory / Civil Air Patrol, CC BY 4.0" |
| Demo scenario "Eastern Kentucky flash floods, July 2022 (replay)" | 26 photos from LADI v2 train labels, event `CAP_-_KY_Flooding_July_2022`, selected for flooding / building damage / road damage and EXIF GPS | CC BY 4.0 | as above |
| Map tiles | OpenStreetMap | ODbL | "© OpenStreetMap contributors" |
| Jablanica 2024 scenario | planned: Wikimedia Commons, per-file license | per file (to be listed here with author and link before use) | per file |

Not used: photos from news media or social networks without permission.

Per-image lists: `samples/ladi_dev_set.csv`, `eval/test_set.csv`, `eval/tuning_set.csv`; the demo photos are
listed with source URL in `samples/demo_kentucky.csv` and can be regenerated with
`scripts/build_demo.py` from the LADI v2 train label file.
