# E1/E2 integration notes

- Only eval/ and the E1/E2 results section of docs/eval.md are edited. Runtime
  files are under data/eval as requested. No app/scripts/tests/PLAN edits.
- Evaluation pins an unmodified copy of app/*.py under ignored eval/.runtime to
  avoid combining results from your concurrent edits. Exact hashes are saved.
- The local venv lacked jsonschema. It is installed only in eval/.deps; please
  ensure project setup installs all declared requirements.
- Source LADI test CSV has 1,163 rows but only 1,049 unique image URLs. Identical
  repeated rows were removed before sampling. After full smoke-flight exclusion,
  only 28 of 928 eligible images are flooding_any positives; the proportional
  100-image test has 3 positives. Do not market its macro-F1 as flood accuracy.
- E1 evaluates image_labels, not road passability or per-object damage. E2
  evaluates camera GPS, not object coordinates. Historical/public-image search
  recognition can affect E2.
- Backend and geolocation recommendations are emitted in eval/e1_decision.json
  and eval/e2_summary.json. They do not modify .env or app defaults.
