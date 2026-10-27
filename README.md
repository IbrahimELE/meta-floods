# Rescue Map (working title)

AI disaster-response system that turns chaotic post-disaster imagery into an
actionable rescue map.

After a flood or earthquake, first responders are flooded with photos from
citizens, drones and social media, with no fast way to make sense of them.
This system ingests those images, uses **SAM 3.1** to segment every building,
road and bridge, uses **Muse Spark** to assess damage severity and road
passability per segmented object, and an **agent** fuses everything into a
live, prioritized map: where help is needed first, which routes are safe, and
where conditions are dangerous.

Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026),
problem statement **"Build for Your World"**. I'm from Bosnia and Herzegovina,
hit by deadly floods in 2014 and in Jablanica in 2024.

> Decision support for trained responders, not a replacement for their
> judgement. Every AI finding links back to the photo and mask it came from.

## Status

Day 1 – API test scripts work against the live Meta Model API (SAM 3.1,
Muse Spark 1.3). The full plan is in [`PLAN.md`](PLAN.md).

**Built during the hackathon:** all code here was written during the event.
The test scripts in `scripts/` and `docs/api-notes.md` were created on Oct 26
in the evening (after the kickoff, one day before the official building period
started on Oct 27); everything else from Oct 27 on. See commit history.

## Setup (Windows, PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env     # then paste your MODEL_API_KEY into .env
```

## Day-1 tests

```powershell
python scripts/00_check_setup.py          # key works? models visible?
python scripts/01_test_sam.py             # SAM 3.1 masks -> outputs/*_sam.png
python scripts/02_test_muse_spark.py      # damage per SAM object -> outputs/*_assessment_meta.json
python scripts/03_test_geolocation.py --region "Jablanica, Bosnia and Herzegovina"
```

Put test photos in `samples/` first (see `docs/plan.md`, section Data).

## Meta models used

| Model | Role |
|---|---|
| `sam-3.1` | Segments buildings, roads, bridges, flood water (one concept per request) |
| `muse-spark-1.3` | Per-object damage + passability, grounded in SAM's numbered masks; geolocation; agent |
| Muse Spark Open (Baseten) | Open-weight backend for the same assessment |

## Data & credits

- LADI dataset – MIT Lincoln Laboratory / Civil Air Patrol, CC BY 4.0
