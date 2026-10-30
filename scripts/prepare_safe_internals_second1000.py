"""Freeze SAFE examples 1001-2000 without changing the running first collector."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from baseline.storage import digest, read_json, write_json, write_text
from safe_internals import pipeline
from safe_internals.data import select as original_select
from safe_internals.__main__ import lock

CONFIG = ROOT / 'configs/safe-internals-second1000.json'


def selection(rows, count=1000, seed=20261018):
    if count != 1000:
        raise ValueError('This launcher selects exactly the second 1000 unique repair inputs')
    full = original_select(rows, 2000, seed)
    first = read_json(ROOT / 'configs/safe-repair-pilot1000.json')
    if full['cases'][:1000] != first['cases']:
        raise ValueError('The original first-1000 selection differs')
    second = {**full, 'count': 1000, 'cases': full['cases'][1000:],
              'method': full['method'] + '; offset 1000 after frozen first batch'}
    if set(c['input_code_sha256'] for c in second['cases']) & set(c['input_code_sha256'] for c in first['cases']):
        raise ValueError('Input program overlap between the two batches')
    return second


def prepare(dataset, output):
    driver = Path(__file__).read_text(encoding='utf-8')
    previous = output / 'selection-driver.py'
    if previous.exists() and previous.read_text(encoding='utf-8') != driver:
        raise ValueError('Second-batch selection driver changed; use another output directory')
    # Change the selector only in this preparation process, restoring it afterwards.
    # Do not edit pipeline/data modules: the first job may already be running.
    before = pipeline.select
    pipeline.select = selection
    try:
        pipeline.prepare(dataset, output, CONFIG)
    finally:
        pipeline.select = before
    write_text(previous, driver)
    write_json(output / 'selection-driver.json', {
        'offset': 1000, 'count': 1000, 'driver_sha256': digest(driver.encode()),
        'first_selection_sha256': digest((ROOT / 'configs/safe-repair-pilot1000.json').read_bytes()),
        'selection_scope': 'next distinct input programs in the same deterministic ordering; not a family-disjoint train/test split'})
    frozen = read_json(output / 'frozen-files.json')
    for name in ('selection-driver.py', 'selection-driver.json'):
        frozen[name] = digest((output / name).read_bytes())
    write_json(output / 'frozen-files.json', frozen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with lock(args.output):
        prepare(args.dataset.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
