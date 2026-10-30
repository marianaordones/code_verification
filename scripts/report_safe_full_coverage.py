"""Audit all six SAFE repair batches from saved results; no solver/model calls."""
import argparse
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def report(first, second, remaining, output):
    batches = [('first1000', first, 'safe-repair-pilot1000.json'),
               ('second1000', second, 'safe-repair-second1000.json')]
    batches += [('remaining-' + name, remaining / name / 'seed-20261018', f'safe-repair-remaining-{name}.json')
                for name in ('a', 'b', 'c', 'd')]
    seen, summaries, all_missing = set(), {}, []
    for name, folder, selection_name in batches:
        expected = load(ROOT / 'configs' / selection_name)
        cases = expected['cases']
        ids = {c['id'] for c in cases}
        if seen & ids:
            raise ValueError('Overlap between batch selections')
        seen |= ids
        manifest_path = folder / 'manifest.json'
        if manifest_path.exists():
            manifest = load(manifest_path)
            if manifest['selection']['cases'] != cases or manifest['dataset_sha256'] != expected['dataset_sha256']:
                raise ValueError('Different dataset/selection: ' + str(folder))
        rows, missing = [], []
        for case in cases:
            path = folder / 'examples' / case['id'] / 'result.json'
            if path.exists():
                row = load(path)
                if row['id'] != case['id']:
                    raise ValueError('Result ID mismatch: ' + str(path))
                rows.append(row)
            else:
                missing.append(case['id'])
        summaries[name] = {'path': str(folder), 'expected': len(cases), 'completed': len(rows),
                           'target_verified': sum(r['target_success'] for r in rows),
                           'internals_available': sum(r['status'] == 'internals_available' for r in rows),
                           'eligible': sum(r.get('training_eligibility', {}).get('eligible', False) for r in rows),
                           'eligible_with_internals': sum(r.get('training_eligibility', {}).get('eligible', False)
                                                         and r['status'] == 'internals_available' for r in rows),
                           'statuses': dict(Counter(r['status'] for r in rows)), 'missing': missing}
        all_missing.extend(missing)
    if len(seen) != 13768:
        raise ValueError('Expected all 13,768 SAFE repair row IDs')
    result = {'scope': 'repair-row coverage; no inference/solver; not a train/test split', 'expected': len(seen),
              'completed': sum(s['completed'] for s in summaries.values()), 'complete': not all_missing,
              'target_verified': sum(s['target_verified'] for s in summaries.values()),
              'internals_available': sum(s['internals_available'] for s in summaries.values()),
              'eligible': sum(s['eligible'] for s in summaries.values()),
              'eligible_with_internals': sum(s['eligible_with_internals'] for s in summaries.values()),
              'batches': summaries, 'missing': all_missing,
              'generation_rows': 11060, 'generation_scope': 'not collected; retain original generation examples separately'}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'coverage.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# SAFE: complete repair coverage', '', '| Batch | Completed | Internals | Target verified | Eligible |', '|---|---|---|---|---|']
    for name, s in summaries.items():
        lines.append(f"| {name} | {s['completed']}/{s['expected']} | {s['internals_available']} | {s['target_verified']} | {s['eligible']} |")
    lines += ['', f"Complete: {result['complete']}; {result['completed']}/13768 records evaluated.",
              f"Eligible positives: {result['eligible']}; eligible with internals: {result['eligible_with_internals']}.",
              'Completion means all selected rows were evaluated, not that all yielded solver internals or valid targets.',
              'All 11060 generation rows remain outside this repair collection. Missing IDs appear in coverage.json.']
    (output / 'coverage.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(output / 'coverage.md')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first', type=Path, default=ROOT / 'results/safe-internals-pilot1000-attrs-v2/seed-20261018')
    parser.add_argument('--second', type=Path, default=ROOT / 'results/safe-internals-second1000-attrs-v2/seed-20261018')
    parser.add_argument('--remaining', type=Path, default=ROOT / 'results/safe-internals-remaining-attrs-v2')
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis/safe-full-repair-coverage')
    args = parser.parse_args()
    report(args.first, args.second, args.remaining, args.output)


if __name__ == '__main__':
    main()
