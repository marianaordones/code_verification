"""Paper's 462 keys, stratified without revealing task labels or removed assertions."""
from collections import Counter
import random
import sys

from baseline.storage import read_json
from .download import SOURCE
from .download import REVISION
from baseline.prompts import ROOT

LABELS = ('AX', 'INST-forall', 'INST-witness', 'NLA', 'FUEL', 'Other')
SELECTION = ROOT / 'configs/solver-needs-tasks100.json'


def selected_cases(count=100, selection_path=SELECTION):
    selection = read_json(selection_path)
    ids = selection['ids']
    if selection['revision'] != REVISION or not ids or len(set(ids)) != len(ids):
        raise ValueError('Expected unique IDs from the pinned dataset')
    if not 1 <= count <= len(ids):
        raise ValueError(f'tasks must be between 1 and {len(ids)} for this selection')
    rows = {row['id']: row for row in cases()}
    if any(key not in rows for key in ids):
        raise ValueError('Selection contains an ID outside the paper Verus/Z3 benchmark')
    return [rows[key] for key in ids[:count]]


def upstream():
    # Plain source imports work on the cluster's Python 3.12; no installation of
    # upstream's Python>=3.13 project or its development dependencies is needed.
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))
    from solver_needs.verus import source, laws
    return source, laws


def cases():
    dataset = read_json(SOURCE / 'data/essential/essential_verus_z3.json')
    benchmark = read_json(SOURCE / 'data/benchmark_sets/verus_tasks.json')
    release = read_json(SOURCE / 'results/verus_z3/labels.json')['labels']
    rows = {r['key']: r for r in dataset['assertions']}
    result = []
    for key, label in benchmark['fine_labels'].items():
        actual = benchmark.get('aliases', {}).get(key, key)
        if actual not in rows:
            raise ValueError('Paper task is absent from extraction: ' + key)
        result.append({**rows[actual], 'id': key, 'paper_label': label, 'release_label': release[actual]})
    if len(result) != 462:
        raise ValueError('Unexpected paper task count')
    return result


def ordered_cases(seed):
    pools = {label: [] for label in LABELS}
    for row in cases():
        pools[row['paper_label']].append(row)
    rng = random.Random(seed)
    for label in LABELS:
        rng.shuffle(pools[label])
    counts, ordered = Counter(), []
    while any(pools.values()):
        for label in LABELS:
            pool = pools[label]
            if not pool:
                continue
            # Prefer less-repeated source programs; no model outcomes are used.
            index = min(range(len(pool)), key=lambda i: counts[pool[i]['source_path']])
            row = pool.pop(index)
            counts[row['source_path']] += 1
            ordered.append(row)
    return ordered


def split_task(row):
    parser, _ = upstream()
    path = (SOURCE / row['source_path']).resolve()
    if not path.is_relative_to((SOURCE / 'data/corpora').resolve()) or path.suffix != '.rs':
        raise ValueError('Not a Verus corpus file')
    reference = path.read_text(encoding='utf-8')
    matches = [(a, b) for a, b in parser.assert_statements(reference)
               if reference.count('\n', 0, a) + 1 == row['line']
               and ''.join(reference[a:b].split()) == ''.join(row['text'].split())]
    if len(matches) != 1:
        raise ValueError('Cannot uniquely match recorded assertion: ' + row['id'])
    begin, end = matches[0]
    prefix, suffix = reference[:begin], reference[end:]
    return {'reference': reference, 'prefix': prefix, 'suffix': suffix,
            'proof_context': parser.in_proof_context(reference, begin),
            'line': reference.count('\n', 0, begin) + 1}
