"""Stable records and stratified pilot selection; targets never rank feedback."""
from collections import defaultdict
import random
import re

from baseline.integrity import tokens, protected
from baseline.storage import digest

FENCE = re.compile(r'```(?:rust|rs)\s*\r?\n(.*?)```', re.S | re.I)


def codes(row):
    source, target = FENCE.findall(row['input']), FENCE.findall(row['output'])
    if len(source) != 2 or len(target) != 1:
        raise ValueError('Expected two input Rust fences (program then diagnostic) and one output fence')
    return source[0], target[0]


def diagnostic(row):
    blocks = list(FENCE.finditer(row['input']))
    return row['input'][blocks[0].end():] if blocks else row['input']


def stratum(row):
    text = diagnostic(row).lower()
    for name, words in (
        ('type', ('e0308', 'mismatched types', 'type mismatch')),
        ('syntax', ('unexpected token', 'expected one of', 'unclosed delimiter', 'expected `')),
        ('invariant', ('invariant',)), ('postcondition', ('postcondition',)),
        ('assertion', ('assertion',)), ('precondition', ('precondition',)),
        ('arithmetic', ('overflow', 'underflow')), ('resource', ('timeout', 'resource limit'))):
        if any(word in text for word in words):
            return name
    return 'other'


def code_tags(code):
    try:
        ts = tokens(code)
        return {'assume_call': any(t.removeprefix('r#') == 'assume' and ts[i + 1:i + 2] == ['(']
                                   for i, t in enumerate(ts)),
                'loop_isolation_false': any('loop_isolation' in a and 'false' in a
                                             for a in protected(ts)[0]), 'lexing_error': None}
    except (ValueError, IndexError) as error:
        return {'assume_call': None, 'loop_isolation_false': None, 'lexing_error': str(error)}


def select(rows, count=200, seed=20261018):
    buckets, seen, repair_count = defaultdict(list), set(), 0
    for index, row in enumerate(rows):
        if 'provided Verus code contains errors' not in row.get('prompt', ''):
            continue
        repair_count += 1
        source, _ = codes(row)
        sha = digest(source.encode())
        if sha in seen:
            continue  # Diverse pilot, not silent deletion from the full dataset.
        seen.add(sha)
        key = (stratum(row), bool(code_tags(source)['loop_isolation_false']))
        buckets[key].append({'id': f'safe-{index:05d}', 'index': index,
                             'input_code_sha256': sha, 'diagnostic_stratum': key[0],
                             'input_loop_isolation_false': key[1]})
    rng = random.Random(seed)
    for key in sorted(buckets):
        rng.shuffle(buckets[key])
    chosen = []
    while len(chosen) < count:
        changed = False
        for key in sorted(buckets):
            if buckets[key] and len(chosen) < count:
                chosen.append(buckets[key].pop())
                changed = True
        if not changed:
            raise ValueError('Not enough unique repair inputs for the pilot')
    return {'seed': seed, 'count': count, 'repair_rows_in_source': repair_count,
            'unique_repair_inputs': len(seen), 'method': 'round-robin diagnostic x input-loop-isolation strata; shuffled unique input programs',
            'cases': chosen}


def families(rows):
    """Conservative exact input/output/label components; not a semantic split guarantee."""
    parent, first = list(range(len(rows))), {}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for index, row in enumerate(rows):
        inputs, outputs = FENCE.findall(row.get('input', '')), FENCE.findall(row.get('output', ''))
        keys = [('program', digest(code.encode())) for code in (inputs[:1] + outputs[:1])]
        if row.get('label'):
            keys.append(('label', row['label']))
        for key in keys:
            if key in first:
                a, b = find(index), find(first[key])
                parent[max(a, b)] = min(a, b)
            else:
                first[key] = index
    return [f'safe-family-{find(i):05d}' for i in range(len(rows))]
