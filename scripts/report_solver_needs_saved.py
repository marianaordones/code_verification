"""Report saved study records despite code drift; never resume inference/solver."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Saved artifact path escapes study: ' + name)
    return path


def report(study, output):
    manifest = load(study / 'manifest.json')
    for name, expected in manifest['files'].items():
        if sha(contained(study, name)) != expected:
            raise ValueError('Frozen input changed: ' + name)
    changed = [name for name, expected in manifest.get('implementation', {}).items()
               if not (REPO / name).is_file() or sha(REPO / name) != expected]
    config = manifest['config']
    arms = ([config['single_arm']] if config.get('single_arm') else
            config.get('advanced_blocks') or ['with_internals', 'without_internals'])
    limit = config['max_attempts']
    cases, summaries = manifest['cases'], {}
    for arm in arms:
        completed, missing = [], []
        initial = 0
        categories = {}
        for case in cases:
            initial_case = load(contained(study, 'inputs/' + case['id'] + '/verification.json'))['success']
            initial += initial_case
            category = categories.setdefault(case['paper_label'], {'expected': 0, 'solved': 0})
            category['expected'] += 1
            path = contained(study, arm + '/' + case['id'] + '/task.json')
            if not path.exists():
                missing.append(case['id'])
                continue
            task = load(path)
            records = task['attempts']
            if len({r['attempt'] for r in records}) != len(records):
                raise ValueError('Duplicate proposal numbers: ' + str(path))
            first = min((r['attempt'] for r in records if r['success']), default=None)
            if first is not None and not all(n in {r['attempt'] for r in records} for n in range(1, first + 1)):
                raise ValueError('Missing earlier proposal records: ' + str(path))
            solved = not initial_case and first is not None and first <= limit
            completed.append({'id': case['id'], 'first_success': first if not initial_case else None, 'attempts': records})
            category['solved'] += solved
        attempts = [r for task in completed for r in task['attempts'] if r['attempt'] <= limit]
        summaries[arm] = {'expected': len(cases), 'completed': len(completed),
            'initially_verified': initial, 'repair_denominator': len(cases) - initial,
            'solved': sum(t['first_success'] is not None and t['first_success'] <= limit for t in completed),
            'solved_by_attempt': {str(k): sum(t['first_success'] is not None and t['first_success'] <= k for t in completed)
                                  for k in range(1, limit + 1)},
            'attempts': len(attempts), 'unchanged': sum(r.get('unchanged', False) for r in attempts),
            'errors': dict(Counter(r.get('error_type') for r in attempts)),
            'input_tokens': sum(r.get('input_tokens', 0) for r in attempts),
            'output_tokens': sum(r.get('output_tokens', 0) for r in attempts),
            'by_paper_label': categories, 'missing': missing}
    result = {'scope': 'saved task/attempt records only; no model, solver, or historical prompt certification',
              'manifest_sha256': sha(study / 'manifest.json'), 'study': str(study),
              'frozen_files_validated': True, 'current_implementation_changes': changed,
              'config': config, 'summaries': summaries,
              'complete': all(not s['missing'] for s in summaries.values()),
              'first_pair_check_passed': None}
    lines = ['# Solver Needs: saved-record report', '',
             'No inference or solver execution. Frozen input hashes checked.',
             'Current-code drift does not block reporting; this does not certify unchanged code/prompts during the original job.', '',
             '| Arm | Completed | ' + ' | '.join('Through ' + str(k) for k in range(1, limit + 1)) + ' |',
             '|---|---|' + '---|' * limit]
    for arm, summary in summaries.items():
        lines.append(f"| {arm} | {summary['completed']}/{summary['expected']} | " +
                     ' | '.join(str(summary['solved_by_attempt'][str(k)]) for k in range(1, limit + 1)) + ' |')
    lines += ['', '| Category | Selected | ' + ' | '.join(arms) + ' |', '|---|---|' + '---|' * len(arms)]
    labels = sorted({c['paper_label'] for c in cases})
    for label in labels:
        lines.append(f"| {label} | {sum(c['paper_label'] == label for c in cases)} | " +
                     ' | '.join(str(summaries[a]['by_paper_label'][label]['solved']) for a in arms) + ' |')
    if config.get('single_arm') and config.get('complement_token_budget'):
        lines += ['', 'Single arm: base24k + complement16k. No base-only or no-internals control was run.']
    lines += ['', f"Complete: {result['complete']}. Current implementation differences: {len(changed)}.",
              'Missing tasks are listed in comparison.json and are not counted as successes.']
    output.mkdir(parents=True, exist_ok=True)
    (output / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(output / 'comparison.md')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    study = args.study.resolve()
    report(study, args.output.resolve() if args.output else study / 'saved-report')


if __name__ == '__main__':
    main()
