"""Read saved results for the three mutually exclusive advanced-feedback arms."""
from itertools import combinations
from collections import Counter
from baseline.storage import read_json, write_json, write_text, digest
from .data import LABELS


def compare_blocks(root, manifest):
    arms = manifest['config']['advanced_blocks']
    rows, summaries = [], {}
    for case in manifest['cases']:
        initial = root / 'inputs' / case['id']
        verified = read_json(initial / 'verification.json')['success']
        row = {**case, 'initially_verified': verified}
        requests = []
        for arm in arms:
            folder = root / arm / case['id']
            row[arm] = read_json(folder / 'task.json')['success'] if (folder / 'task.json').exists() else None
            path = folder / 'attempt_01/request.json'
            requests.append(read_json(path) if path.exists() else None)
        keys = ('candidate_sha256', 'common_messages_sha256', 'shared_feedback_sha256', 'seed')
        row['first_pair_valid'] = verified or (all(requests) and all(
            requests[0].get(k) is not None and all(r.get(k) == requests[0][k] for r in requests) for k in keys)
            and requests[0]['candidate_sha256'] == digest((initial / 'candidate.rs').read_bytes())
            and all({k: v for k, v in r['parameters'].items() if k != 'advanced_block'} == manifest['config'] for r in requests))
        rows.append(row)
    for arm in arms:
        tasks = [read_json(root / arm / c['id'] / 'task.json') for c in rows if c[arm] is not None]
        attempts = [a for task in tasks for a in task['attempts']]
        requests = [read_json(p) for p in (root / arm).glob('*/attempt_*/request.json')]
        s = {'expected': len(rows), 'completed': len(tasks), 'solved': sum(t['success'] for t in tasks),
            'solved_by_attempt': {str(k): sum(any(a['success'] and a['attempt'] <= k for a in t['attempts']) for t in tasks) for k in (1, 2, 3)},
            'attempts': len(attempts), 'unchanged': sum(a['unchanged'] for a in attempts),
            'errors': dict(Counter(a['error_type'] for a in attempts)),
            'edit_errors': dict(Counter(a['edit_error'] for a in attempts if a['edit_error'])),
            'input_tokens': sum(a['input_tokens'] for a in attempts), 'output_tokens': sum(a['output_tokens'] for a in attempts),
            'inference_seconds': sum(a['inference_seconds'] for a in attempts),
            'advanced_exposed_attempts': sum(a.get('advanced_exposed', False) for a in attempts),
            'truncated': sum(a['truncated'] for a in attempts),
            'context_violations': sum(r['headroom_after_output_reserve'] < 0 for r in requests),
            'minimum_context_headroom': min((r['headroom_after_output_reserve'] for r in requests), default=None),
            'by_paper_label': {label: {'expected': sum(r['paper_label'] == label for r in rows),
                'solved': sum(r['paper_label'] == label and r[arm] is True for r in rows)} for label in LABELS},
            'missing': [r['id'] for r in rows if r[arm] is None]}
        summaries[arm] = s
        write_json(root / arm / 'summary.json', s)
    pairs = {}
    for a, b in combinations(arms, 2):
        pairs[a + '_vs_' + b] = {'a_only': [r['id'] for r in rows if r[a] is True and r[b] is False],
            'b_only': [r['id'] for r in rows if r[b] is True and r[a] is False],
            'both': [r['id'] for r in rows if r[a] is True and r[b] is True]}
    report = {'summaries': summaries, 'paired': rows, 'pairwise': pairs,
        'complete': all(not s['missing'] for s in summaries.values()),
        'first_pair_check_passed': all(r['first_pair_valid'] for r in rows),
        'scope': 'All three arms receive base24k + complement12k; each receives up to12k of one advanced block. No no-extra control.',
        'sessions': [read_json(p) for p in root.glob('session-*.json')]}
    write_json(root / 'comparison.json', report)
    lines = ['# Solver Needs: three advanced blocks', '', report['scope'], '',
        '| Arm | Completed | Proposal 1 | Through 2 | Through 3 | Unchanged |', '|---|---|---|---|---|---|']
    for arm, s in summaries.items():
        curve = s['solved_by_attempt']
        lines.append(f"| {arm} | {s['completed']}/{s['expected']} | {curve['1']} | {curve['2']} | {curve['3']} | {s['unchanged']} |")
    lines += ['', '| Category | Selected | Matching | Chains | Clauses |', '|---|---|---|---|---|']
    for label in LABELS:
        counts = [summaries[a]['by_paper_label'][label] for a in arms]
        lines.append(f"| {label} | {counts[0]['expected']} | " + ' | '.join(str(c['solved']) for c in counts) + ' |')
    lines += ['', f"Complete: {report['complete']}; initial triplets valid: {report['first_pair_check_passed']}"]
    write_text(root / 'comparison.md', '\n'.join(lines))
    print(root / 'comparison.md', flush=True)
    return report
