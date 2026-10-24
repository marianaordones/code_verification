"""Freeze a stratified exploratory selection without reading model outcomes."""
import argparse
from collections import Counter
import random

from baseline.storage import read_json, write_json
from .data import LABELS, SELECTION, cases
from .download import REVISION


def select(rows, excluded_ids, per_label=10, seed=20261023):
    rng = random.Random(seed)
    excluded = set(excluded_ids)
    counts = Counter(r['source_path'] for r in rows if r['id'] in excluded)
    pools = {label: sorted([r for r in rows if r['paper_label'] == label and r['id'] not in excluded],
                           key=lambda r: r['id']) for label in LABELS}
    for pool in pools.values():
        rng.shuffle(pool)
        if len(pool) < per_label:
            raise ValueError('Not enough cases for the requested category quota')
    chosen = []
    for _ in range(per_label):
        for label in LABELS:
            pool = pools[label]
            index = min(range(len(pool)), key=lambda i: counts[pool[i]['source_path']])
            row = pool.pop(index)
            counts[row['source_path']] += 1
            chosen.append(row)
    sources = Counter(r['source_path'] for r in chosen)
    return {'revision': REVISION, 'seed': seed,
            'method': 'Sorted-ID pools shuffled per category; label round-robin; prefer least-repeated source programs including development sources; no model outcomes read',
            'scope': 'exploratory; excludes six development IDs, not necessarily their source programs',
            'excluded_ids': list(excluded_ids), 'ids': [r['id'] for r in chosen],
            'category_counts': dict(Counter(r['paper_label'] for r in chosen)),
            'unique_source_programs': len(sources),
            'repeated_source_programs': {k: v for k, v in sources.items() if v > 1},
            'development_source_overlap': sorted(set(sources) & {r['source_path'] for r in rows if r['id'] in excluded}),
            'cases': [{k: r[k] for k in ('id', 'paper_label', 'source_path')} for r in chosen]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    from pathlib import Path
    if Path(args.output).exists():
        parser.error('Selection already exists; never silently overwrite fixed IDs')
    result = select(cases(), read_json(SELECTION)['ids'][:6])
    write_json(args.output, result)
    print(result['category_counts'], 'unique programs:', result['unique_source_programs'])


if __name__ == '__main__':
    main()
