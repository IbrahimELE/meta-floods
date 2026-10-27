"""Run the actual app pipeline against frozen LADI labels, isolated under data/eval."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path
from common import ROOT, DATA, Ledger, classification, percentile, provenance, save_json, truth, freeze_app
from make_splits import read_csv, image_path

os.environ['FH_DATA_DIR'] = str(DATA)
os.environ['FH_AI_LOCATE'] = '0'
freeze_app()
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from app.api import ModelApi
from app.config import Settings
from app.db import Database
from app.pipeline import Pipeline
from app.schema import validate

class MeasuredApi(ModelApi):
    def __init__(self, settings, ledger):
        super().__init__(settings, os.getenv('MODEL_API_KEY'), os.getenv('BASETEN_API_KEY'))
        self.ledger = ledger
        self.assessments = {}
        self.requests = []
        self.active_image = None
        for client, chat in [(self.meta,False), (self.baseten,True)]:
            if client is None:
                continue
            endpoint = client.chat.completions if chat else client.responses
            original = endpoint.create
            def measured(*args, _original=original, _chat=chat, **kwargs):
                sam = kwargs['model'] == self.s.sam_model
                kind = 'sam' if sam else 'e1_'+('baseten' if _chat else 'meta')
                if not sam:
                    kwargs['max_tokens' if _chat else 'max_output_tokens'] = 12000
                reservation = self.ledger.reserve(kind, .0025 if sam else .12)
                start = time.perf_counter()
                response = _original(*args, **kwargs)
                usage = self.ledger.settle(reservation,response,sam)
                if not sam:
                    target = DATA/'responses'/f'{reservation}.json'
                    save_json(target, response.model_dump(mode='json'))
                    self.requests.append(dict(image_id=self.active_image, seconds=time.perf_counter()-start, **usage))
                return response
            endpoint.create = measured

    def segment(self, image, concept):
        # Reuse identical SAM raw output across backends so both see the same masks.
        key = hashlib.sha256(image.read_bytes() + concept.encode() + self.s.sam_model.encode()).hexdigest()
        path = DATA/'sam_cache'/f'{key}.txt'
        if path.exists():
            return path.read_text(encoding='utf-8')
        text = super().segment(image,concept)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return text

    def assess(self, image, overlay, listing, feedback):
        image_id = image.stem
        self.active_image = image_id  # processing is sequential; SAM alone fans out
        start = time.perf_counter()
        record = dict(seconds=None, parsed_json=False, valid=False, first=not feedback)
        self.assessments.setdefault(image_id, []).append(record)
        try:
            result, model = super().assess(image,overlay,listing,feedback)
            record['parsed_json'] = True
            ids = {int(x) for x in re.findall(r'^#(\d+):',listing,re.M)}
            errors = validate(result,ids)
            record.update(valid=not errors, errors=errors, prediction=result.get('image_labels'))
            return result, model
        finally:
            record['seconds'] = time.perf_counter()-start

async def run(args):
    rows = read_csv(ROOT/'eval/test_set.csv')[:args.limit]
    ledger = Ledger()
    stamp = provenance()
    for backend in args.backends:
        os.environ['ASSESS_BACKEND'] = backend
        s = Settings(data_dir=DATA, assess_backend=backend, ai_locate=False,
                     budget_images=300, budget_api_calls=2000, image_workers=1)
        db = Database(s.db_path)
        api = MeasuredApi(s,ledger)
        if not api.meta or (backend=='baseten' and not api.baseten):
            raise RuntimeError('Required API key missing (key values are not logged)')
        pipe = Pipeline(db,s,api)
        file = DATA/f'e1_{backend}.json'
        state = json.loads(file.read_text()) if file.exists() else {
            'backend':backend,'source_hashes':stamp,'test_sha256':hashlib.sha256((ROOT/'eval/test_set.csv').read_bytes()).hexdigest(),
            'incident_id':db.create_incident('E1 '+backend), 'records':[]}
        if state['source_hashes'] != stamp:
            raise RuntimeError('app sources changed since this run. Do not mix versions; see NOTES_FOR_CLAUDE.')
        if state['test_sha256'] != hashlib.sha256((ROOT/'eval/test_set.csv').read_bytes()).hexdigest():
            raise RuntimeError('Test manifest changed')
        done = {r['url'] for r in state['records']}
        semaphore = asyncio.Semaphore(args.workers)
        async def one(row):
            if row['url'] in done:
                return
            if provenance() != stamp:
                raise RuntimeError('app changed while running; stopped before next paid image')
            path = image_path(row)
            if not path.exists():
                raise FileNotFoundError(path)
            iid = pipe.ingest(state['incident_id'],path.read_bytes(),path.name)
            if iid is None:
                found = db.one('SELECT id FROM images WHERE incident_id=? AND original_name=?',(state['incident_id'],path.name))
                iid = found['id']
                if db.image(iid)['processing_state'] != 'queued':
                    raise RuntimeError('Interrupted image already processed: reconcile manually, do not silently pay twice')
            start = time.perf_counter()
            await pipe.process_image(iid)
            image = dict(db.image(iid))
            labels = db.one('SELECT labels_json FROM image_labels WHERE image_id=?',(iid,))
            record = dict(url=row['url'], image_id=iid, truth=truth(row),
                          prediction=json.loads(labels['labels_json']) if labels else None,
                          state=image['processing_state'],error=image['last_error'],
                          pipeline_seconds=time.perf_counter()-start,
                          assessment_attempts=api.assessments.get(iid,[]))
            state['records'].append(record)
            save_json(file,state)
            print(f"{backend} {len(state['records'])}/{args.limit}: {image['processing_state']}; ${ledger.summary()['estimated_or_reserved_usd']:.3f}",flush=True)
        async def bounded(row):
            async with semaphore:
                await one(row)
        await asyncio.gather(*(bounded(row) for row in rows))
        order = {r['url']:i for i,r in enumerate(rows)}
        state['records'].sort(key=lambda r:order.get(r['url'],1000))
        save_json(file,state)
        records = state['records'][:args.limit]
        attempts = [a for r in records for a in r['assessment_attempts']]
        first = [a for a in attempts if a['first']]
        latencies = [sum(a['seconds'] for a in r['assessment_attempts']) for r in records if r['state']=='done']
        summary = dict(backend=backend,n=len(records), **classification(records),
                       valid_json_percent=100*sum(a['parsed_json'] for a in attempts)/len(attempts) if attempts else 0,
                       valid_schema_first_percent=100*sum(a['valid'] for a in first)/len(first) if first else 0,
                       valid_pipeline_percent=100*sum(r['state']=='done' for r in records)/len(records),
                       assess_p50_s=percentile(latencies,.5),assess_p95_s=percentile(latencies,.95),
                       latency_definition='Successful images: sum of assessment attempt wall times, including invalid-response retry; excludes shared cached SAM.',
                       attempted_responses=len(attempts), source_hashes=stamp, cost=ledger.summary())
        save_json(ROOT/'eval'/f'e1_{backend}_summary.json',summary)
    summaries = [ROOT/'eval'/f'e1_{b}_summary.json' for b in ('meta','baseten')]
    if all(p.exists() for p in summaries):
        meta, op = [json.loads(p.read_text()) for p in summaries]
        comparable = meta['n']==op['n']==100 and meta['source_hashes']==op['source_hashes'] and meta['macro_classes']==op['macro_classes'] and bool(meta['macro_classes'])
        checks = dict(full_comparable_run=comparable,
                      macro_f1=op['macro_f1'] is not None and meta['macro_f1'] is not None and op['macro_f1']>=meta['macro_f1']-.05,
                      valid_json=op['valid_json_percent']>=98,
                      schema_valid=op['valid_pipeline_percent']>=98,
                      latency=op['assess_p95_s'] is not None and meta['assess_p95_s'] is not None and op['assess_p95_s']<=1.5*meta['assess_p95_s'])
        save_json(ROOT/'eval/e1_decision.json',dict(checks=checks, selected_backend='baseten' if all(checks.values()) else 'meta',
                    provisional=not comparable, note='Conservative extra schema-validity gate; pilot cannot select a backend. No app/.env changes.',cost=ledger.summary()))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=5,choices=range(1,101),metavar='1..100')
    parser.add_argument('--backends',nargs='+',choices=['meta','baseten'],default=['meta','baseten'])
    parser.add_argument('--workers',type=int,default=1,choices=range(1,5))
    asyncio.run(run(parser.parse_args()))
