"""SAFE enriched SFT preparation and conservative benchmark contamination screening."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from baseline.integrity import tokens
from safe_internals.data import FENCE, families


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def normalized(code):
    return tokens(code)


def grams(ts, width=12):
    return {tuple(ts[i:i + width]) for i in range(max(0, len(ts) - width + 1))}


def overlap(rows, benchmark):
    """Exact token equality and >=80% containment of a benchmark's 12-token shingles.

    Similarity is a review flag, not a proof of identity. Renaming is not normalized.
    """
    bench = []
    inverted = defaultdict(set)
    exact_index = defaultdict(set)
    for task in read(benchmark)['tasks']:
        code = (benchmark.parent / task['path']).read_text(encoding='utf-8')
        ts = normalized(code)
        gs = grams(ts)
        bench.append((task['id'], ts, gs))
        exact_index[tuple(ts)].add(len(bench) - 1)
        for g in gs:
            inverted[g].add(len(bench) - 1)
    hits, failures = [], []
    for index, row in enumerate(rows):
        # Both the incorrect input and the corrected target can expose a benchmark.
        for field in ('input', 'output'):
            blocks = FENCE.findall(row.get(field, ''))[:1]
            for code in blocks:
                try:
                    ts = normalized(code)
                except ValueError as error:
                    failures.append({'id': f'safe-{index:05d}', 'field': field, 'error': str(error)})
                    continue
                counts = Counter(j for g in grams(ts) for j in inverted.get(g, ()))
                for j in exact_index.get(tuple(ts), ()):
                    counts.setdefault(j, 0)
                for j, count in counts.items():
                    key, target, gs = bench[j]
                    coverage = count / len(gs) if gs else 0
                    exact = ts == target
                    if exact or (len(gs) >= 20 and coverage >= .8):
                        hits.append({'id': f'safe-{index:05d}', 'field': field, 'benchmark': key,
                                     'match': 'token_exact' if exact else 'shingle_containment_review',
                                     'benchmark_shingle_coverage': coverage})
    return {'benchmark_tasks': len(bench), 'hits': hits, 'parse_errors': failures,
            'scope': 'First program fence in SAFE input/output vs local VerusBench manifest programs. '
                     'Comments/whitespace ignored; approximate matches require review. '
                     'No guarantee against renamed or proof-modified variants.'}


def build(args):
    rows = read(args.dataset)
    contamination = overlap(rows, args.benchmark)
    family_ids = families(rows)
    # Also join programs identical after removing comments/whitespace.
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    code_families = {}
    for i, row in enumerate(rows):
        for field in ('input', 'output'):
            for code in FENCE.findall(row.get(field, ''))[:1]:
                try:
                    key = sha(json.dumps(normalized(code)).encode())
                except ValueError:
                    continue
                a, b = find(family_ids[i]), find(code_families.setdefault(key, family_ids[i]))
                parent[max(a, b)] = min(a, b)
    family_ids = [find(f) for f in family_ids]
    blocked = {family_ids[int(hit['id'].split('-')[1])] for hit in contamination['hits']}
    folders = [args.first, args.second] + [args.remaining / b / 'seed-20261018' for b in 'abcd']
    records, missing, decisions, seen = [], [], [], set()
    dataset_sha = sha(args.dataset.read_bytes())
    for folder in folders:
        if not (folder / 'manifest.json').exists():
            missing.append(str(folder))
            continue
        manifest = read(folder / 'manifest.json')
        if manifest['dataset_sha256'] != dataset_sha:
            raise ValueError('Dataset mismatch: ' + str(folder))
        for case in manifest['selection']['cases']:
            key, index = case['id'], case['index']
            if key in seen:
                raise ValueError('Duplicate repair ID: ' + key)
            seen.add(key)
            base = folder / 'examples' / key
            if not (base / 'result.json').exists():
                missing.append(key)
                continue
            result = read(base / 'result.json')
            metadata = read(base / 'metadata.json')
            reason = None
            if (not result.get('training_eligibility', {}).get('eligible') or not result['target_success']
                    or result['preservation_status'] != 'valid' or metadata['target_tags']['assume_call'] is not False):
                reason = 'not_validated_positive'
            elif family_ids[index] in blocked:
                reason = 'benchmark_overlap_family'
            if result['status'] == 'internals_available' and result['packages'][args.package]['availability'] == 'available':
                kind = 'repair_internals'
                messages_path = base / f'messages-{args.package}.json'
            elif result['status'] == 'no_captured_failing_queries' and result['input_error_type'] in ('compilation', 'syntax'):
                capture = read(base / 'solver/report.json')
                if capture['queries'] or capture['capture_errors']:
                    reason = reason or 'frontend_capture_not_empty'
                kind = 'repair_frontend'
                messages_path = base / 'messages-baseline.json'
            else:
                kind = 'other'
                reason = reason or 'not_selected_category'
                messages_path = None
            if reason:
                decisions.append({'id': key, 'reason': reason})
                continue
            if read(base / 'original.json') != rows[index]:
                raise ValueError('Original record mismatch: ' + key)
            messages = read(messages_path)
            if kind == 'repair_frontend':
                verification = read(base / 'verification.json')
                if not (verification.get('stdout', '').strip() or verification.get('stderr', '').strip()):
                    raise ValueError('Missing frontend diagnostic: ' + key)
                messages[-1]['content'] += '\n\nNo SMT internals were obtained: this candidate failed during compilation or parsing, before SMT proof obligations were captured.'
            records.append({'id': key, 'family_id': family_ids[index], 'kind': kind,
                            'messages': messages + [{'role': 'assistant', 'content': rows[index]['output']}]})
    generation_count = sum('provided Verus code contains errors' not in r.get('prompt', '') for r in rows)
    expected_repairs = {f'safe-{i:05d}' for i, r in enumerate(rows)
                        if 'provided Verus code contains errors' in r.get('prompt', '')}
    if seen - expected_repairs:
        raise ValueError('Selection contains non-repair IDs')
    missing.extend(sorted(expected_repairs - seen))
    if args.generation_validation:
        validations = read(args.generation_validation)
        if validations['dataset_sha256'] != dataset_sha:
            raise ValueError('Generation validation dataset mismatch')
        for value in validations['records']:
            index = value['index']
            if 'provided Verus code contains errors' in rows[index].get('prompt', ''):
                raise ValueError('Repair incorrectly tagged as generation')
            if (not value['success'] or not value['assume_free']
                    or value.get('preservation_status') != 'valid' or family_ids[index] in blocked):
                continue
            row = rows[index]
            records.append({'id': f'safe-{index:05d}', 'family_id': family_ids[index], 'kind': 'generation',
                            'messages': [{'role': 'system', 'content': row['prompt']},
                                         {'role': 'user', 'content': row['input']},
                                         {'role': 'assistant', 'content': row['output']}]})
    if missing and not args.allow_partial:
        raise ValueError(f'{len(missing)} missing records/batches. Finish collection or explicitly use --allow-partial for a pilot.')
    args.output.mkdir(parents=True, exist_ok=False)
    splits = defaultdict(list)
    for record in records:
        bucket = int(sha(f"{args.seed}:{record['family_id']}".encode())[:8], 16) / 2**32
        split = 'validation' if bucket < .05 else 'train'
        splits[split].append(record)
    files = {}
    for split in ('train', 'validation'):
        path = args.output / f'{split}.jsonl'
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in splits[split]), encoding='utf-8')
        files[path.name] = sha(path.read_bytes())
    report = {'dataset_sha256': dataset_sha, 'package': args.package, 'seed': args.seed,
              'benchmark_manifest_sha256': sha(args.benchmark.read_bytes()),
              'preparation_code_sha256': sha(Path(__file__).read_bytes()),
              'files_sha256': files, 'counts': {s: dict(Counter(r['kind'] for r in rs)) for s, rs in splits.items()},
              'missing': missing, 'excluded': decisions, 'overlap': contamination,
              'generation_original': generation_count, 'generation_validation_supplied': bool(args.generation_validation),
              'split': '95/5 deterministic hash of exact-connected family; no semantic independence guarantee'}
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report['counts'], indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, default=ROOT / 'data/safe/sft_safe_25k.json')
    p.add_argument('--benchmark', type=Path, default=ROOT / 'data/manifest.json')
    p.add_argument('--overlap-only', action='store_true')
    p.add_argument('--first', type=Path, default=ROOT / 'results/safe-internals-pilot1000-attrs-v2/seed-20261018')
    p.add_argument('--second', type=Path, default=ROOT / 'results/safe-internals-second1000-attrs-v2/seed-20261018')
    p.add_argument('--remaining', type=Path, default=ROOT / 'results/safe-internals-remaining-attrs-v2')
    p.add_argument('--output', type=Path, default=ROOT / 'data/safe/sft-enriched-v1')
    p.add_argument('--package', choices=['20x3', '50x3'], default='50x3')
    p.add_argument('--generation-validation', type=Path)
    p.add_argument('--allow-partial', action='store_true')
    p.add_argument('--seed', type=int, default=20261018)
    a = p.parse_args()
    if a.overlap_only:
        a.output.mkdir(parents=True, exist_ok=True)
        result = overlap(read(a.dataset), a.benchmark)
        (a.output / 'overlap.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps({'matches': len(result['hits']), 'safe_rows': len({h['id'] for h in result['hits']}),
                          'benchmark_tasks': result['benchmark_tasks'], 'parse_errors': len(result['parse_errors'])}))
    else:
        build(a)
