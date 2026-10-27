"""Blinded web-assisted camera geolocation; event-level prior, never per-image GPS."""
from __future__ import annotations
import argparse
import json
import math
import os
import random
import time
import uuid
from common import ROOT, DATA, Ledger, distance_km, percentile, save_json, freeze_app
from make_splits import read_csv, image_path
freeze_app()
from dotenv import load_dotenv
from PIL import Image, ImageOps
from openai import OpenAI
from app.api import final_text, data_url
from app.pipeline import read_metadata
load_dotenv(ROOT/'.env')

# Fixed before looking at per-image GPS. Approximate state geographic centers.
# Idalia is a multi-state event; use the whole named event area, not truth-selected state.
REGIONS = {
 'CAP_-_AR_Storms_APR_2023': ('Arkansas, USA', (34.9,-92.4)),
 'CAP_-_PA_Storms_Aug_2023': ('Pennsylvania, USA', (40.9,-77.8)),
 'CAP_-_HI_Wildfires_Aug_2023': ('Hawaii, USA', (20.3,-156.4)),
 'CAP_-_MS_Tornadoes_MAR_2023': ('Mississippi, USA', (32.7,-89.7)),
 'CAP_-_CA_Storms_Jan_2023': ('California, USA', (37.2,-119.5)),
 'CAP_-_VT_Flooding_Jul_2023': ('Vermont, USA', (44.1,-72.7)),
 'CAP_-_Hur_Idalia_Aug_2023': ('Florida, Georgia and South Carolina, USA', (29.7,-83.3)),
}
SCHEMA = {'type':'object','additionalProperties':False,
 'required':['latitude','longitude','place_name','precision','clues_used','confidence'],
 'properties':{'latitude':{'type':['number','null']},'longitude':{'type':['number','null']},
 'place_name':{'type':'string'},'precision':{'type':'string','enum':['building','street','neighborhood','town','region','unknown']},
 'clues_used':{'type':'array','items':{'type':'string'}},'confidence':{'type':'number'}}}

def select():
    target = DATA/'e2_selection.json'
    if target.exists():
        return json.loads(target.read_text())
    eligible = []
    rows = read_csv(ROOT/'eval/test_set.csv')
    for row in rows:
        path = image_path(row)
        if not path.exists():
            raise FileNotFoundError('Download all test images before selecting E2: '+str(path))
        with Image.open(path) as im:
            gps = read_metadata(im).gps
        if gps and all(math.isfinite(v) for v in gps):
            event = row['url'].split('/Images/')[1].split('/')[0]
            region, center = REGIONS[event]
            eligible.append(dict(url=row['url'], image=str(path.relative_to(ROOT)), gps=gps,
                                 event=event,region=region,baseline=center,blind_id=uuid.uuid4().hex))
    if len(eligible)<40:
        raise RuntimeError(f'Only {len(eligible)} images have GPS; need metadata fallback, do not change sample silently')
    selected = random.Random(42).sample(eligible,40)
    state = dict(seed=42,eligible_count=len(eligible),records=selected,
                 note='State-level event priors; Idalia uses a multi-state event prior. Baselines are fixed approximate geographic centers, not fitted to sample GPS.')
    save_json(target,state)
    return state

def blind(record):
    dest = DATA/'e2_blind'/f"{record['blind_id']}.jpg"
    dest.parent.mkdir(parents=True,exist_ok=True)
    with Image.open(ROOT/record['image']) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        clean = Image.new('RGB',im.size)
        clean.paste(im)
        clean.save(dest,'JPEG',quality=90) # fresh image, no EXIF/XMP/ICC/comments
    with Image.open(dest) as im:
        assert not im.getexif() and not any(k in im.info for k in ('exif','xmp','icc_profile','comment'))
    return dest

def summarize(records):
    errors = [r['error_km'] for r in records if r.get('error_km') is not None]
    base = [r['baseline_error_km'] for r in records]
    n = len(records)
    def metrics(values):
        return dict(median_km=percentile(values,.5),p90_km=percentile(values,.9),
                    within_1km_percent=100*sum(x<=1 for x in values)/n if n else 0,
                    within_5km_percent=100*sum(x<=5 for x in values)/n if n else 0)
    return dict(attempts=n,coordinate_answers=len(errors),coverage_percent=100*len(errors)/n if n else 0,
                model=metrics(errors),baseline=metrics(base),web_assisted=True,
                denominator='All attempts including refusals, malformed output and API failures; distance quantiles use coordinate answers only.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=5,choices=range(1,41),metavar='1..40')
    parser.add_argument('--prepare-only',action='store_true')
    args = parser.parse_args()
    selection = select()
    if args.prepare_only:
        print(f"Selected 40 of {selection['eligible_count']} GPS images",flush=True)
        return
    ledger = Ledger()
    file = DATA/'e2_records.json'
    state = json.loads(file.read_text()) if file.exists() else {'records':[]}
    done = {r['blind_id'] for r in state['records']}
    client = OpenAI(base_url='https://api.meta.ai/v1',api_key=os.getenv('MODEL_API_KEY'),max_retries=0)
    for row in selection['records'][:args.limit]:
        if row['blind_id'] in done:
            continue
        path = blind(row)
        reservation = ledger.reserve('e2_meta', .20)
        record = dict(blind_id=row['blind_id'],url=row['url'],region=row['region'],gps=row['gps'],
                      baseline_error_km=distance_km(row['gps'],row['baseline']),error_km=None)
        start = time.perf_counter()
        try:
            response = client.responses.create(model='muse-spark-1.3',
                instructions="Estimate where this post-disaster photo was taken, for placing it on a rescue map. Use visible text, signs, landmarks, bridges, rivers, terrain and architecture. Use web search to confirm landmark locations. Never use people's faces. If unsure, return a coarser precision and null coordinates rather than inventing a point.",
                input=[{'type':'message','role':'user','content':[
                    {'type':'input_text','text':f"The disaster area is: {row['region']}. The photo was almost certainly taken there; narrow it down as far as the evidence allows."},
                    {'type':'input_image','image_url':data_url(path)}]}],
                tools=[{'type':'web_search'}], reasoning={'effort':'medium'},
                max_output_tokens=6000, max_tool_calls=5, timeout=120,
                text={'format':{'type':'json_schema','name':'photo_location','schema':SCHEMA}})
            record['usage'] = ledger.settle(reservation,response)
            save_json(DATA/'responses'/f'{reservation}.json',response.model_dump(mode='json'))
            estimate = json.loads(final_text(response))
            record['estimate'] = estimate
            lat,lon = estimate.get('latitude'),estimate.get('longitude')
            if type(lat) in (int,float) and type(lon) in (int,float) and math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180:
                record['error_km'] = distance_km(row['gps'],(lat,lon))
        except Exception as exc:
            # Log type only: SDK exceptions may contain request payloads.
            record['error_type'] = type(exc).__name__
        record['seconds'] = time.perf_counter()-start
        state['records'].append(record)
        save_json(file,state)
        print(f"E2 {len(state['records'])}/{args.limit}: error_km={record['error_km']}; ${ledger.summary()['estimated_or_reserved_usd']:.3f}",flush=True)
        if record.get('error_type') in ('AuthenticationError','PermissionDeniedError','BadRequestError'):
            break
    result = summarize(state['records'][:args.limit])
    result.update(selection_eligible=selection['eligible_count'],cost=ledger.summary(),
                  decision='keep_disabled' if result['attempts']<40 or result['model']['within_5km_percent']<30 else 'passes_5km_gate',
                  FH_AI_LOCATE=0 if result['attempts']<40 or result['model']['within_5km_percent']<30 else 1,
                  provisional=result['attempts']<40,
                  note=selection['note']+' No app/.env settings modified.')
    save_json(ROOT/'eval/e2_summary.json',result)

if __name__ == '__main__':
    main()
