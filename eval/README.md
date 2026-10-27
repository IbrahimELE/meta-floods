# E1 / E2 evaluation

Run from repository root with Python 3.12 and the app requirements installed.
Credentials are read from root `.env`; never pass or commit them.

```powershell
python -B eval/make_splits.py --download-limit 5
python -B eval/test_eval.py
python -B eval/run_e1.py --limit 5
python -B eval/make_splits.py
python -B eval/run_e2.py --limit 5
# Inspect pilot outputs and data/eval/cost.sqlite before continuing.
python -B eval/run_e1.py --limit 100 --workers 4
python -B eval/run_e2.py --limit 40
python -B eval/report.py
```

`make_splits` always derives the same manifests from the downloaded original v2
label files, seed 42 and the smoke flight exclusions. Exact duplicate URLs are
removed; conflicting duplicate labels cause an error. Flight identity includes
the event and mission directory, because A0001 is reused by different events.
Original EXIF GPS survives resizing (maximum dimension 1600 px).

Paid runs resume from `data/eval/e1_meta.json`, `e1_baseten.json` and
`e2_records.json`. They do not rerun completed failures to cherry-pick successes.
The two E1 backends share identical cached SAM outputs. The pipeline is invoked
programmatically with separate incidents in `data/eval/firsthour.sqlite`.

The first run pins unmodified `app/*.py` into ignored `eval/.runtime/app`, with
hashes in reports, to isolate concurrent development. Delete neither the pinned
source nor run state mid-evaluation. To evaluate a new pipeline version, archive
the current evaluation first and explicitly create a new run; never mix outputs.
On this workstation the missing jsonschema dependency was installed only into
ignored `eval/.deps`; the normal project requirements remain unchanged.

The shared SQLite cost ledger reserves before requests and records provider
usage afterwards. It refuses new calls if the total including outstanding
reservations would exceed $9. The $1 margin covers estimation uncertainty. Failed
requests with unknown usage keep their reservation. This is not invoice-level
accounting. No account-wide costs from Claude's concurrent work are included.

E2 uses a fixed event-to-state prior, approximate region-center baseline, and
fresh metadata-free random-name images. The Idalia event spans multiple states:
its whole Florida/Georgia/South Carolina prior is used rather than choosing a
state from the image's hidden GPS. Raw inputs, outputs, GPS and costs stay in
ignored `data/eval`; selected per-image measurements and summaries are exported
under `eval` for reproducibility. Public-image recognition is possible via search,
so the result is web-assisted, not purely visual geolocation.

Data attribution: LADI v2, MIT Lincoln Laboratory / Civil Air Patrol, CC BY 4.0.
Source: https://registry.opendata.aws/ladi/ .
