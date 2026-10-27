"""Export auditable per-image results and append only the owned docs/eval.md section."""
import csv
import json
from common import ROOT, DATA, CLASSES, Ledger, save_json

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def number(v):
    return 'n/a' if v is None else f'{v:.3f}'

def main():
    lines = ['## E1/E2 results', '', 'Evaluated 2026-10-27. Sources and frozen application hashes are in `eval/*_summary.json`; per-image results are in `eval/e1_predictions.csv` and `eval/e2_predictions.csv`.', '',
             '### Dataset and method', '',
             'LADI **v2**, seed 42: 40 tuning images from val, 100 unique test images from test. Identical repeated source CSV rows were deduplicated before sampling; conflicting duplicates would stop the run. Excluded every smoke URL and the entire event/mission/flight folder containing it. The same `A0001` name in a different event is a different flight.', '',
             'After exclusion the eligible test population has 900 non-flood and 28 flood images; proportional stratification gives **97 non-flood / 3 flood** images. Flood classes therefore cannot enter the ≥10-positive macro-F1; this run is not a strong flood-performance benchmark. Split provenance and source hashes: `eval/split_metadata.json`.', '',
             'The unmodified app pipeline was copied to ignored `eval/.runtime/app` before evaluation so concurrent backend work could not change the measured code. `FH_DATA_DIR=data/eval`; separate incidents per assessment backend. Identical SAM responses were cached and reused between backends. No production database or app settings were changed.', '',
             '### E1 — image-level assessment', '',
             'Missing/failed predictions count as negative predictions and remain in the denominator. Zero-denominator P/R/F1 is reported as 0. Macro-F1 includes only labels with ≥10 positive test images; the same labels are used for both backends. This evaluates the separate `image_labels` output, not object-level damage, route safety or precise localization.', '']
    predictions=[]
    for backend in ('meta','baseten'):
        s=read(ROOT/'eval'/f'e1_{backend}_summary.json')
        lines += [f"#### {backend} (n={s['n']})", '', '| Class | Positives | Precision | Recall | F1 | Nonanswers |', '|---|---:|---:|---:|---:|---:|']
        for label,m in s['per_class'].items():
            lines.append(f"| {label} | {m['positive']} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['nonanswers']} |")
        lines += ['',f"Macro-F1: **{number(s['macro_f1'])}** ({', '.join(s['macro_classes'])}).",
                  f"Parseable JSON: {s['valid_json_percent']:.1f}% of {s['attempted_responses']} assessment attempts. First-response schema/semantic validity: {s['valid_schema_first_percent']:.1f}%. Final valid pipeline output: {s['valid_pipeline_percent']:.1f}% of images.",
                  f"Assessment p50 / p95: **{number(s['assess_p50_s'])} / {number(s['assess_p95_s'])} s**. Timing sums assessment attempts for successful images (including corrective retries), excludes SAM and backoff; failures are separately counted above. This is E1 backend timing, not E3 end-to-end latency.", '']
        for r in read(DATA/f'e1_{backend}.json')['records']:
            entry=dict(backend=backend,url=r['url'],state=r['state'],pipeline_seconds=r['pipeline_seconds'])
            for k in CLASSES:
                entry['truth_'+k]=r['truth'][k]
                entry['pred_'+k]=(r.get('prediction') or {}).get(k)
            predictions.append(entry)
    with (ROOT/'eval/e1_predictions.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(predictions[0])); w.writeheader(); w.writerows(predictions)
    decision=read(ROOT/'eval/e1_decision.json')
    lines += [f"**Backend decision: `{decision['selected_backend']}`**. Checks: `{json.dumps(decision['checks'])}`. Provisional: {decision['provisional']}.",
              'In addition to the plan’s JSON/F1/latency conditions, promotion requires ≥98% final schema-valid pipeline outputs. A pilot cannot promote a backend. Label definitions for non-building classes are operational interpretations as documented in PLAN.md.', '',
              '### E2 — web-assisted camera geolocation', '']
    e=read(ROOT/'eval/e2_summary.json')
    lines += [f"Random seed 42; {e['attempts']} attempted images selected from {e['selection_eligible']} GPS-bearing test images. Fresh random filenames and re-encoded pixel-only JPEGs remove EXIF/XMP/comments; the API receives no source filename, URL, GPS or image ID. Ground truth is **camera GPS**, not the photographed object.",
              'Region priors are assigned by event, not per-image GPS: US state names, with a broader Florida/Georgia/South Carolina prior for Hurricane Idalia. The baseline uses fixed approximate regional centers in `eval/run_e2.py`. The multi-state exception avoids leaking the target state from GPS. Web search can recognize public images, so this is explicitly web-assisted performance.', '',
              f"Coverage: **{e['coordinate_answers']}/{e['attempts']} ({e['coverage_percent']:.1f}%)**.", '',
              '| Method | Median km | p90 km | All attempts ≤1 km | All attempts ≤5 km |', '|---|---:|---:|---:|---:|']
    for name in ('model','baseline'):
        m=e[name]; lines.append(f"| {name} | {number(m['median_km'])} | {number(m['p90_km'])} | {m['within_1km_percent']:.1f}% | {m['within_5km_percent']:.1f}% |")
    lines += ['', 'Distance quantiles use coordinate answers only; within-distance percentages use **all attempted images**, including abstentions and API/parse failures.',
              f"**Geolocation decision: `{e['decision']}`; recommended `FH_AI_LOCATE={e['FH_AI_LOCATE']}`** (threshold: at least 30% of all 40 attempts within 5 km). Provisional: {e['provisional']}. No configuration was modified.", '']
    out=[]
    for r in read(DATA/'e2_records.json')['records']:
        est=r.get('estimate',{})
        out.append(dict(url=r['url'],region=r['region'],camera_lat=r['gps'][0],camera_lon=r['gps'][1],
                        predicted_lat=est.get('latitude'),predicted_lon=est.get('longitude'),error_km=r['error_km'],
                        baseline_error_km=r['baseline_error_km'],seconds=r['seconds'],error_type=r.get('error_type','')))
    with (ROOT/'eval/e2_predictions.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    cost=Ledger().summary(); save_json(ROOT/'eval/cost_summary.json',cost)
    lines += ['### Cost and reproducibility', '',
              f"Total usage-based estimate plus conservative reservations for unresolved calls: **${cost['estimated_or_reserved_usd']:.3f}**, shared stop threshold $9 (user ceiling $10). Not a provider invoice. Details: `eval/cost_summary.json`.",
              'Rates checked 2026-10-27: [Meta pricing](https://dev.meta.ai/docs/pricing-rate-limits), [Baseten Muse Spark Open](https://www.baseten.co/library/muse-spark-open/). SAM $0.0025/image request; input/output $1.25/$4.25 per million tokens, ignoring cache discounts; search $0.0025/query. Request output caps: E1 12,000 tokens, E2 6,000 tokens and at most 5 tool calls. Reservations remain charged after uncertain failures.', '',
              'Run instructions: `eval/README.md`. Raw responses, database, source-label CSV copies, resized EXIF images, blinded images and SAM cache remain under ignored `data/eval/`; credentials are never exported. `eval/NOTES_FOR_CLAUDE.md` records integration notes.', '']
    section='\n'.join(lines)
    target=ROOT/'docs/eval.md'
    previous=target.read_text(encoding='utf-8')
    prefix=previous.split('## E1/E2 results',1)[0].rstrip()
    target.write_text(prefix+'\n\n'+section,encoding='utf-8')

if __name__=='__main__':
    main()
