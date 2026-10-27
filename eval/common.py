"""Evaluation-only accounting, metrics and provenance. Never logs credentials."""
from __future__ import annotations
import hashlib
import json
import math
import sqlite3
import sys
from contextlib import contextmanager
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'eval/.deps'))
DATA = ROOT / 'data/eval'
CLASSES = ('flooding_any', 'flooding_structures', 'buildings_affected_or_greater',
           'buildings_major_or_greater', 'roads_damage', 'debris_any')

def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)

def freeze_app():
    """Pin the unmodified pipeline so concurrent backend edits cannot mix a run."""
    dest = ROOT/'eval/.runtime/app'
    marker = dest.parent/'source_hashes.json'
    if not marker.exists():
        original = {p.name:p.read_bytes() for p in (ROOT/'app').glob('*.py')}
        if original != {p.name:p.read_bytes() for p in (ROOT/'app').glob('*.py')}:
            raise RuntimeError('app is being saved; retry after the write completes')
        dest.mkdir(parents=True,exist_ok=True)
        for name, content in original.items():
            (dest/name).write_bytes(content)
        save_json(marker,{k:hashlib.sha256(v).hexdigest() for k,v in original.items()})
    sys.path.insert(0,str(dest.parent))

def provenance():
    folder = ROOT/'eval/.runtime/app'
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob('*.py'))}

def percentile(values, q):
    if not values:
        return None
    a = sorted(values)
    x = (len(a)-1)*q
    lo = int(x)
    return a[lo] + (a[min(lo+1, len(a)-1)] - a[lo]) * (x-lo)

def truth(row):
    y = {k: int(row[k]) for k in CLASSES if k in row}
    y['buildings_affected_or_greater'] = int(any(int(row['buildings_'+k]) for k in ('affected','minor','major','destroyed')))
    y['buildings_major_or_greater'] = int(any(int(row['buildings_'+k]) for k in ('major','destroyed')))
    return y

def classification(records):
    metrics = {}
    for label in CLASSES:
        tp = fp = fn = tn = missing = 0
        for r in records:
            y = r['truth'][label]
            value = (r.get('prediction') or {}).get(label)
            missing += type(value) is not bool
            pred = value is True  # failures/nonanswers are zero, retained in denominator
            tp += bool(y and pred)
            fp += bool(not y and pred)
            fn += bool(y and not pred)
            tn += bool(not y and not pred)
        p = tp/(tp+fp) if tp+fp else 0.0
        recall = tp/(tp+fn) if tp+fn else 0.0
        metrics[label] = dict(positive=tp+fn, tp=tp, fp=fp, fn=fn, tn=tn,
                              precision=p, recall=recall, f1=2*p*recall/(p+recall) if p+recall else 0.0,
                              nonanswers=missing)
    eligible = [k for k,m in metrics.items() if m['positive'] >= 10]
    return {'per_class': metrics, 'macro_classes': eligible,
            'macro_f1': sum(metrics[k]['f1'] for k in eligible)/len(eligible) if eligible else None}

def distance_km(a, b):
    lat1,lon1,lat2,lon2 = map(math.radians, (*a,*b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))

LIMIT_USD = 20


class CostLimit(RuntimeError):
    pass

@contextmanager
def connection(path):
    c = sqlite3.connect(path, timeout=60)
    try:
        with c:
            yield c
    finally:
        c.close()

class Ledger:
    """Shared E1/E2 persistent cost ceiling; uncertain calls retain their reservation.

    Prices: Meta pricing-rate-limits and baseten.co/library/muse-spark-open,
    checked 2026-10-27. Uncached input is used as a conservative estimate.
    Limit LIMIT_USD (raised from $9 to $20 on 27.10.: the enriched 100-image test set
    with two backends + E2 web search needs ~$12–15; Baseten usage is billed to Baseten credits).
    """
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.path = DATA/'cost.sqlite'
        with connection(self.path) as c:
            c.execute('CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, kind TEXT, cost REAL, status TEXT, input_tokens INTEGER, output_tokens INTEGER, searches INTEGER)')

    def reserve(self, kind, amount):
        with connection(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            total = c.execute('SELECT COALESCE(SUM(cost),0) FROM calls').fetchone()[0]
            if total + amount > LIMIT_USD:
                raise CostLimit(f'Evaluation cost ceiling: reserved/used ${total:.3f}')
            return c.execute('INSERT INTO calls(kind,cost,status) VALUES(?,?,?)', (kind,amount,'reserved')).lastrowid

    def settle(self, call_id, response, sam=False):
        usage = getattr(response, 'usage', None)
        u = usage.model_dump() if usage else {}
        inp = u.get('input_tokens', u.get('prompt_tokens', 0)) or 0
        out = u.get('output_tokens', u.get('completion_tokens', 0)) or 0
        searches = 0
        for item in getattr(response, 'output', []):
            if getattr(item, 'type', '') == 'web_search_call':
                action = getattr(item, 'action', None)
                queries = getattr(action, 'queries', None)
                searches += max(1, len(queries) if queries else 1)
        cost = .0025 if sam else (inp*1.25 + out*4.25)/1e6 + searches*.0025
        with connection(self.path) as c:
            if sam or usage:
                c.execute('UPDATE calls SET cost=?,status=?,input_tokens=?,output_tokens=?,searches=? WHERE id=?',
                          (cost,'reported',inp,out,searches,call_id))
        return dict(input_tokens=inp, output_tokens=out, search_queries=searches, estimated_usd=cost)

    def summary(self):
        with connection(self.path) as c:
            rows = c.execute('SELECT kind,COUNT(*),SUM(cost),SUM(status="reserved") FROM calls GROUP BY kind').fetchall()
        return {'estimated_or_reserved_usd': sum(r[2] for r in rows),
                'by_kind': {r[0]: dict(calls=r[1], usd=r[2], uncertain_calls=r[3]) for r in rows},
                'limit_usd': LIMIT_USD, 'note': 'Estimate from usage, not provider invoice; unresolved calls retain conservative reservations.'}
