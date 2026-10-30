"""Freeze all remaining SAFE repair rows into four shards; retain duplicate inputs."""
import argparse
from collections import defaultdict
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from baseline.storage import digest, read_json, write_json, write_text
from safe_internals import pipeline
from safe_internals.__main__ import lock
from safe_internals.data import select as original_select, codes, code_tags, stratum

BATCHES = ('a', 'b', 'c', 'd')


def selections(rows, seed=20261018):
    first = read_json(ROOT / 'configs/safe-repair-pilot1000.json')
    second = read_json(ROOT / 'configs/safe-repair-second1000.json')
    prior = first['cases'] + second['cases']
    original = original_select(rows, 2000, seed)
    if original['cases'] != prior:
        raise ValueError('The original two 1000-example selections differ')
    excluded = {c['id'] for c in prior}
    if len(excluded) != 2000:
        raise ValueError('Expected 2000 distinct previously selected row IDs')
    buckets = defaultdict(list)
    total = 0
    for index, row in enumerate(rows):
        if 'provided Verus code contains errors' not in row.get('prompt', ''):
            continue
        total += 1
        key = f'safe-{index:05d}'
        if key in excluded:
            continue
        source, _ = codes(row)
        category = (stratum(row), bool(code_tags(source)['loop_isolation_false']))
        buckets[category].append({'id': key, 'index': index, 'input_code_sha256': digest(source.encode()),
                                  'diagnostic_stratum': category[0], 'input_loop_isolation_false': category[1]})
    rng = random.Random(seed)
    for key in sorted(buckets):
        rng.shuffle(buckets[key])
    ordered = []
    while any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key]:
                ordered.append(buckets[key].pop())
    if len(ordered) != total - 2000:
        raise ValueError('Remaining selection does not cover all repair rows')
    values = {}
    for index, name in enumerate(BATCHES):
        cases = ordered[index::4]
        values[name] = {'seed': seed, 'count': len(cases), 'repair_rows_in_source': total,
                        'unique_repair_inputs': original['unique_repair_inputs'],
                        'method': f'all remaining repair ROWS after frozen first 2000; round-robin diagnostic x input-loop-isolation; interleaved shard {index+1}/4; duplicate input rows retained',
                        'cases': cases}
    return values


def selection(rows, count, seed, batch):
    value = selections(rows, seed)[batch]
    if value['count'] != count:
        raise ValueError('Configuration count differs from frozen shard')
    return value


def prepare(dataset, output, batch):
    config = ROOT / f'configs/safe-internals-remaining-{batch}.json'
    driver = Path(__file__).read_text(encoding='utf-8')
    previous = output / 'selection-driver.py'
    if previous.exists() and previous.read_text(encoding='utf-8') != driver:
        raise ValueError('Remaining-selection driver changed; use another output directory')
    before = pipeline.select
    pipeline.select = lambda rows, count, seed: selection(rows, count, seed, batch)
    try:
        pipeline.prepare(dataset, output, config)
    finally:
        pipeline.select = before
    write_text(previous, driver)
    write_json(output / 'selection-driver.json', {
        'batch': batch, 'batches': 4, 'driver_sha256': digest(driver.encode()),
        'reference_selections': {name: digest((ROOT / 'configs' / name).read_bytes()) for name in
                                 ('safe-repair-pilot1000.json', 'safe-repair-second1000.json', f'safe-repair-remaining-{batch}.json')},
        'selection_scope': 'all repair rows not in first 2000; duplicate input rows retained; no claim of family-disjointness'})
    frozen = read_json(output / 'frozen-files.json')
    for name in ('selection-driver.py', 'selection-driver.json'):
        frozen[name] = digest((output / name).read_bytes())
    write_json(output / 'frozen-files.json', frozen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch', choices=BATCHES, required=True)
    args = parser.parse_args()
    with lock(args.output):
        prepare(args.dataset.resolve(), args.output.resolve(), args.batch)


if __name__ == '__main__':
    main()
