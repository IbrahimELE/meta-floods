# FirstHour

**From the first photo to a rescue map – in the first hour, when it matters most.**

After a flood, landslide or earthquake, rescue coordinators are flooded with photos from citizens, drones and
aircraft, and nobody has time to look at them. FirstHour turns that pile of photos into a live, verifiable
map: what is damaged, which roads are cut, where to send teams first – and what still needs to be checked.

Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026), problem statement
**Build for Your World**. I'm from Bosnia and Herzegovina. In May 2014 record floods hit large parts of the country; on the
night of 3/4 October 2024 floods and landslides killed 27 people, 19 of them in the Jablanica area, and cut
roads, bridges and the railway. In both cases the first hours were chaos.

> Decision support for trained responders, not a replacement for their judgement. Every AI statement on the
> map links back to the photo and the mask it came from, and a responder can confirm or reject it.

## How it works

```
photos ──► SAM 3.1: one request per concept (road, building, house, bridge, flood water) → masks
       ──► merge building+house, measure how much of each road lies under flood water
       ──► numbered overlay (#1, #2, …)
       ──► Muse Spark 1.3 sees the photo AND the numbered overlay → damage / passability per object,
           hazards, people (never identified), image-level labels   [validated server-side, 1 retry]
       ──► server priority 1–5 from a fixed, transparent rule (PLAN 7.2)
       ──► Coordinator agent (Muse Spark 1.3 + 6 validated tools): zones, ±1 corrections with evidence,
           "please check" requests, briefing in English and Bosnian
       ──► live map (SSE): triage-tag markers, uncertainty circles, evidence panel, confirm/reject, pin

drone clip ──► SAM 3.1 video tracking (house, road, flood water): every object keeps one id through the
       clip, so it is counted once, not once per frame ──► the fewest keyframes that show every tracked house
       go through the photo pipeline above ──► the clip is shown with the tracks drawn in

responder on the ground ──► voice report at a map point ──► Muse Voice Transcribe ──► Muse Spark Open
       (Baseten) extracts road status / people needing help / hazards ──► shown as a HUMAN observation,
       raises the priority of the zone it falls in, and the coordinator agent sees it
responder ──► marks a road segment blocked (exact OpenStreetMap edge) ──► suggested routes avoid it;
       AI "impassable" findings near a route are shown as warnings, never as closures
```

**Meta models**

| Model | What it does here |
|---|---|
| `sam-3.1` (Meta Model API) | Segments every building, road, bridge and flood-water area. The numbered masks are what Muse Spark talks about, so every finding points at a concrete pixel region. On drone clips it **tracks** houses, roads and flood water across frames, which decides which frames are worth assessing. |
| `muse-spark-1.3` (Meta Model API) | Per-object damage (xBD scale) and passability, grounded in SAM's numbered masks; the coordinator agent with function tools; bilingual briefing. |
| Muse Spark Open (Baseten) | Turns a transcribed voice report into a structured observation (~3 s); also an alternative photo-assessment backend (`ASSESS_BACKEND=baseten`), evaluated head-to-head below. |
| `muse-voice-transcribe-1.0` (Meta Model API) | Transcribes field reports recorded in the browser, biased toward the incident's place names. |

**What makes it verifiable**
- The model never sets a priority. The server computes it from the findings with a fixed rule; the agent
  may suggest ±1 per zone *only* with finding ids as evidence. If a cited finding is rejected later, the
  correction expires automatically.
- A responder's priority locks a zone: the agent cannot change it, re-clustering cannot move its photos.
- "Unknown" is never treated as safe. Zones that could not be assessed are listed separately, not ranked low.
- Camera GPS is shown as camera position with an uncertainty circle; AI-guessed locations are off by default
  (see E2) – responders pin photos without GPS.
- Every agent action – including the ones the server refused – is logged and shown in the UI.

## Results (details in [`docs/eval.md`](docs/eval.md))

| | |
|---|---|
| **E1** image labels vs LADI v2 human labels, 100 test photos (class-enriched, flight-disjoint) | Muse Spark 1.3 macro-F1 **0.79** (Open: 0.72); 100 % valid outputs; recall 0.88–1.00 on flooding, building damage, debris; weak on subtle road damage (recall 0.17) |
| **E2** blinded geolocation, 40 photos, metadata removed | model answers only 5/40 (good: it abstains); 5 % of all attempts within 5 km → AI location stays **off**, responders pin |
| **E3** speed, 26 photos uploaded at once (2 CPU cores) | first photo on the map in **15 s**, whole batch in **96 s** |
| Drone clip (20 s) / voice report | tracked counts after **16 s** / report on the map after **7 s** |
| Tests | 26 automated tests (pipeline states, retries, budget, durability, access, agent validation) |

## Run it

```bash
python -m venv .venv && .venv\Scripts\activate          # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
copy .env.example .env                                   # add MODEL_API_KEY (and BASETEN_API_KEY)
uvicorn app.server:app                                   # http://localhost:8000
```

Demo scenario (Eastern Kentucky floods 2022, 26 LADI photos, replayed "as of" that day):
`python scripts/build_demo.py --name "..." --images "data/demo_src/ky/*.jpg"` – or run the server with
`FH_DATA_DIR=data/demo`. Command line: `python -m app.cli new|ingest|process|pin|status`. Tests: `pytest`.
Deploy: `deploy/modal_app.py` (one container, SQLite snapshot to a Modal Volume after every commit,
read-only demo + private per-visitor sandboxes with a global daily budget).

## Built during the hackathon

Everything in this repository was written during the event; see the commit history. The first test scripts
in `scripts/` and `docs/api-notes.md` were written on Oct 26 in the evening, after the kickoff and one day
before the official building period started (Oct 27); everything else from Oct 27 on. Project plan with three
rounds of external review: [`PLAN.md`](PLAN.md).

## Limitations and ethics

- AI findings can be wrong; precision on flooding/debris is ~0.6 (it prefers false alarms to misses).
  Every finding is labelled as an AI estimate and can be rejected.
- People are only reported as "visible / may need help / cannot tell" – no faces, no identification.
- Photos are sent to the Meta Model API (and Baseten if selected). While free credits are used, Meta may use
  content for product improvement – use only photos you may share.
- SAM 3.1 video tracks at most 16 objects per frame, so a clip's house count is shown as "at least N" when a
  frame hits that limit. Clips are cut to 30 s at 5 fps (billing is per frame).
- Muse Voice Transcribe does not list Bosnian/Croatian/Serbian among its 25 languages, so field reports
  should be spoken in English for now; place names are passed as recognition keywords.
- Evaluation labels are image-level; per-object damage was spot-checked, not benchmarked.
- No military use; not a replacement for official damage assessment.

## Data

Demo scenarios: May 2014 floods in Bosnia and Herzegovina (Wikimedia Commons photos by Dalibor Platenik,
CC BY 3.0, and Commons user "BiH", CC BY-SA 3.0 – credited under each photo), a drone clip of the 2019 Chikuma
River levee breach in Nagano (Geospatial Information Authority of Japan, CC BY 4.0) and the July 2022 Kentucky
floods (LADI v2, MIT Lincoln Laboratory / Civil Air Patrol, CC BY 4.0). Details: [`DATA_SOURCES.md`](DATA_SOURCES.md).
Map tiles © OpenStreetMap contributors.

## License

MIT
