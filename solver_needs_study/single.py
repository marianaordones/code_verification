"""Report one feedback arm without inventing a paired control."""
from collections import Counter

from baseline.storage import read_json, write_json, write_text
from .data import LABELS


def summarize(root, manifest):
    arm = manifest['config']['single_arm']
    rows, completed = [], []
    for case in manifest['cases']:
        path = root / arm / case['id'] / 'task.json'
        task = read_json(path) if path.exists() else None
        initial = read_json(root / 'inputs' / case['id'] / 'verification.json')['success']
        rows.append({**case, 'initially_verified': initial,
                     'success': task['success'] if task else None})
        if task is not None:
            completed.append(task)
    attempts = [a for task in completed for a in task['attempts']]
    summary = {
        'expected': len(rows), 'completed': len(completed),
        'solved': sum(t['success'] for t in completed),
        'initially_verified': sum(r['initially_verified'] for r in rows),
        'repair_denominator': sum(not r['initially_verified'] for r in rows),
        'solved_by_attempt': {str(k): sum(any(a['success'] and a['attempt'] <= k for a in t['attempts'])
                                        for t in completed)
                              for k in range(1, manifest['config']['max_attempts'] + 1)},
        'attempts': len(attempts), 'unchanged': sum(a['unchanged'] for a in attempts),
        'edit_errors': dict(Counter(a['edit_error'] for a in attempts if a['edit_error'])),
        'errors': dict(Counter(a['error_type'] for a in attempts)),
        'input_tokens': sum(a['input_tokens'] for a in attempts),
        'output_tokens': sum(a['output_tokens'] for a in attempts),
        'truncated': sum(a['truncated'] for a in attempts),
        'exposed_attempts': sum(a['internals_exposed'] for a in attempts),
        'inference_seconds': sum(a['inference_seconds'] for a in attempts),
        'processing_seconds': sum(a['processing_seconds'] + a.get('feedback_seconds', 0) for a in attempts),
        'by_paper_label': {label: {'expected': sum(r['paper_label'] == label for r in rows),
                                  'solved': sum(r['paper_label'] == label and r['success'] is True for r in rows)}
                           for label in LABELS},
        'missing': [r['id'] for r in rows if r['success'] is None]}
    report = {'summaries': {arm: summary}, 'cases': rows, 'complete': not summary['missing'],
              'first_pair_check_passed': None, 'paired_comparison': False,
              'arm_meanings': {arm: 'base24k plus complement16k'},
              'sessions': [read_json(p) for p in root.glob('session-*.json')]}
    write_json(root / arm / 'summary.json', summary)
    write_json(root / 'comparison.json', report)
    lines = ['# Solver Needs: base24k + complement16k (single arm)', '',
             'No base-only control was executed.', '', '| Completed | Through 1 | Through 2 | Through 3 |',
             '|---|---|---|---|',
             f"| {summary['completed']}/{summary['expected']} | " + ' | '.join(str(summary['solved_by_attempt'][str(k)]) for k in (1, 2, 3)) + ' |',
             '', '| Category | Selected | Solved |', '|---|---|---|']
    for label, counts in summary['by_paper_label'].items():
        lines.append(f"| {label} | {counts['expected']} | {counts['solved']} |")
    lines += ['', f"Complete: {report['complete']}; initially verified without a model: {summary['initially_verified']}.",
              'Three TOTAL proposals. Labels and successful probes remain hidden. Missing tasks are not successes.']
    write_text(root / 'comparison.md', '\n'.join(lines))
    print(root / 'comparison.md', flush=True)
    return report
