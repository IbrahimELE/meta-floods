# Data sources

Only data we have the right to use. Every photo shown in the demo or the video is listed here.

| Use | Source | License / terms | Attribution |
|---|---|---|---|
| Development, evaluation (E1–E3), smoke tests | LADI v2 – Low Altitude Disaster Imagery, labels `Labels/v2/*`, images from the Civil Air Patrol (`fema-cap-imagery`) | CC BY 4.0 (registry.opendata.aws/ladi) | "LADI v2, MIT Lincoln Laboratory / Civil Air Patrol, CC BY 4.0" |
| Demo scenario "Eastern Kentucky flash floods, July 2022 (replay)" | 26 photos from LADI v2 train labels, event `CAP_-_KY_Flooding_July_2022`, selected for flooding / building damage / road damage and EXIF GPS | CC BY 4.0 | as above |
| Map tiles | OpenStreetMap | ODbL | "© OpenStreetMap contributors" |
| Demo scenario "Floods in Bosnia and Herzegovina, May 2014 (replay)" | 21 photos from Wikimedia Commons: 14 by Dalibor Platenik (Doboj, Prud and three without a named place), 4 by Commons user "BiH" (Zenica, 15 May 2014) | CC BY 3.0 (Platenik), CC BY-SA 3.0 ("BiH") | per photo, shown under the photo in the app; full list with links in `samples/demo_bih2014.csv` |
| Jablanica 2024 scenario | not used: Wikimedia Commons has no freely licensed photos of the 2024 Jablanica flood (checked 27 Oct 2026) | – | – |

Not used: photos from news media or social networks without permission.

Photo locations in the BiH scenario: none of the photos has GPS. Where the Commons title names a town,
the photo is pinned to that town with a large uncertainty circle (±0.8–1.5 km) and the app says
"approximate"; markers in the same town are offset slightly so they can be clicked. Three photos whose
place is not named stay in "Needs a location" – we do not guess. Capture times: the four Zenica photos
have EXIF times; the others only "May 2014", so the app treats their age as unknown.

Per-image lists: `samples/ladi_dev_set.csv`, `eval/test_set.csv`, `eval/tuning_set.csv`; the demo photos are
listed with source URL in `samples/demo_kentucky.csv` and can be regenerated with
`scripts/build_demo.py` from the LADI v2 train label file.
