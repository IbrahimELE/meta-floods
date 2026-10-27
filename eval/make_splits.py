"""Deterministic, flight-disjoint LADI v2 manifests and EXIF-preserving images."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import random
import re
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlsplit
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'eval'
DATA = ROOT / 'data/eval'
BUCKET = 'https://ladi.s3.us-west-2.amazonaws.com'

def flight(url):
    """A flight folder is scoped to its event/mission, not global A0001."""
    path = unquote(urlsplit(url).path)
    match = re.search(r'/A\d+[^/]*/', path)
    if not match:
        raise ValueError(f'No flight folder: {url}')
    return path[:match.end()].rstrip('/')

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def download(url):
    from urllib.parse import quote
    parts = urlsplit(url)
    url = parts._replace(path=quote(parts.path)).geturl()   # some keys contain spaces
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()

def source(split):
    path = DATA / 'sources' / f'ladi_v2_labels_{split}.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(download(f'{BUCKET}/Labels/v2/{path.name}'))
    rows = read_csv(path)
    unique = {}
    for row in rows:
        if row['url'] in unique and unique[row['url']] != row:
            raise ValueError('Conflicting repeated labels: ' + row['url'])
        unique[row['url']] = row
    return sorted(unique.values(), key=lambda r: r['url']), {
        'source_url': f'{BUCKET}/Labels/v2/{path.name}',
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'raw_rows': len(rows), 'unique_urls': len(unique)}

def stratified(rows, n, seed):
    if len(rows) < n:
        raise ValueError(f'Only {len(rows)} eligible unique images for {n}')
    rng = random.Random(seed)
    groups = [[r for r in rows if int(r['flooding_any']) == v] for v in (0, 1)]
    positive = int(n * len(groups[1]) / len(rows) + .5)
    counts = [n - positive, positive]
    selected = sum((rng.sample(g, k) for g, k in zip(groups, counts)), [])
    rng.shuffle(selected)
    return selected

def _truth(row):
    y = {k: int(row[k]) for k in ('flooding_any', 'flooding_structures', 'roads_damage', 'debris_any')}
    y['buildings_affected_or_greater'] = int(any(int(row['buildings_' + k]) for k in ('affected', 'minor', 'major', 'destroyed')))
    y['buildings_major_or_greater'] = int(any(int(row['buildings_' + k]) for k in ('major', 'destroyed')))
    return y


ENRICH_ORDER = ('flooding_any', 'flooding_structures', 'buildings_major_or_greater',
                'roads_damage', 'debris_any', 'buildings_affected_or_greater')


def enriched(rows, n, seed, target=15):
    """Natural prevalence leaves only 3 flood images in 100 (28 of 928 eligible), which makes
    per-class metrics meaningless. Instead: for each class (in ENRICH_ORDER) add random positives
    until it has `target` (or all available), then fill to n at random. Prevalence is therefore
    NOT natural – precision must be read with the reported class counts."""
    rng = random.Random(seed)
    pool = list(rows)
    rng.shuffle(pool)
    chosen, ids = [], set()
    for label in ENRICH_ORDER:
        have = sum(_truth(r)[label] for r in chosen)
        for r in pool:
            if have >= target:
                break
            if r['url'] not in ids and _truth(r)[label]:
                chosen.append(r); ids.add(r['url']); have += 1
    for r in pool:
        if len(chosen) >= n:
            break
        if r['url'] not in ids:
            chosen.append(r); ids.add(r['url'])
    rng.shuffle(chosen)
    return chosen[:n]


def image_path(row):
    return DATA / 'images' / (hashlib.sha256(row['url'].encode()).hexdigest()[:24] + '.jpg')

def save_image(row):
    target = image_path(row)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(download(row['url']))) as im:
        im = ImageOps.exif_transpose(im)
        exif = im.getexif().tobytes()
        im.thumbnail((1600, 1600))
        im.convert('RGB').save(target, 'JPEG', quality=90, exif=exif)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--download-limit', type=int, default=0, help='0 downloads all 140; otherwise first N of each split')
    p.add_argument('--manifests-only', action='store_true')
    args = p.parse_args()
    smoke = read_csv(ROOT / 'samples/ladi_dev_set.csv')
    excluded_urls = {r['url'] for r in smoke}
    excluded_flights = {flight(r['url']) for r in smoke}
    val, vi = source('val')
    test, ti = source('test')
    eligible = [r for r in test if r['url'] not in excluded_urls and flight(r['url']) not in excluded_flights]
    tuning = random.Random(42).sample(val, 40)
    selected = enriched(eligible, 100, 42)
    assert not ({r['url'] for r in tuning} & {r['url'] for r in selected})
    for name, rows in [('tuning', tuning), ('test', selected)]:
        with (OUT / f'{name}_set.csv').open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    metadata = {'seed': 42, 'version': 'v2', 'val': vi, 'test': ti,
                'excluded_flights': sorted(excluded_flights), 'eligible_test_urls': len(eligible),
                'eligible_flooding': dict(Counter(r['flooding_any'] for r in eligible)),
                'test_flooding': dict(Counter(r['flooding_any'] for r in selected)),
                'sampling': 'enriched: >=15 positives per class where available, then random fill (seed 42); prevalence is not natural',
                'test_positives': {k: sum(_truth(r)[k] for r in selected) for k in ENRICH_ORDER},
                'eligible_positives': {k: sum(_truth(r)[k] for r in eligible) for k in ENRICH_ORDER},
                'tuning_count': 40, 'test_count': 100,
                'flight_definition': 'full event/mission path through A00xx folder',
                'attribution': 'LADI v2, MIT Lincoln Laboratory / Civil Air Patrol, CC BY 4.0'}
    (OUT / 'split_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata, indent=2), flush=True)
    if not args.manifests_only:
        rows = tuning + selected if not args.download_limit else tuning[:args.download_limit] + selected[:args.download_limit]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i, _ in enumerate(pool.map(save_image, rows), 1):
                print(f'Downloaded/verified {i}/{len(rows)}', flush=True)

if __name__ == '__main__':
    main()
