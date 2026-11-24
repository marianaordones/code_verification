"""Read-only experiment overview; writes only a separate combined report."""
from pathlib import Path

from baseline.storage import read_json, write_json, write_text
from scripts.run_sonnet46_final25_120s import IDS as FINAL25
from scripts.run_sonnet46_new25_120s import IDS as NEW25
from scripts.run_sonnet46_remaining7_120s import IDS as REMAINING7
from scripts.run_sonnet46_pilot5_60s import IDS as PILOT5
from verusbench_sonnet46 import __main__ as study


def main():
    old50 = read_json(study.SELECTION)['ids']
    groups = [
        ('legacy, timeout 900s, no explicit output cap', 'verusbench-sonnet46-low-shared50-14k-50x3-v1',
         [i for i in old50 if i not in set(PILOT5 + REMAINING7 + ['misc_bubble'])]),
        ('bounded 180s', 'verusbench-sonnet46-bounded-misc-bubble-v1', ['misc_bubble']),
        ('bounded 60s', 'verusbench-sonnet46-pilot5-60s-v1', [i for i in PILOT5 if i != 'misc_filter']),
        ('bounded 120s, including misc_filter rerun', 'verusbench-sonnet46-remaining7-120s-v1', REMAINING7),
        ('bounded 120s, user-selected new25', 'verusbench-sonnet46-new25-120s-v1', NEW25),
        ('bounded 120s, final25', 'verusbench-sonnet46-final25-120s-v1', FINAL25)]
    flat = [i for _, _, ids in groups for i in ids]
    if len(flat) != 100 or len(set(flat)) != 100:
        raise ValueError('Expected exactly 100 distinct IDs')
    rows = []
    for policy, directory, ids in groups:
        for task in ids:
            root = study.ROOT / 'results' / directory
            first_path = root / 'shared' / task / 'task.json'
            first = read_json(first_path) if first_path.exists() else None
            row = {'id': task, 'policy': policy, 'source': str(root),
                   'initially_verified': bool(first and first.get('initially_verified'))}
            for arm in study.vb.ARMS:
                path = root / arm / task / 'task.json'
                row[arm] = ('excluded' if row['initially_verified'] else 'success' if first and first['success'] else
                            ('success' if read_json(path)['success'] else 'failed') if first and path.exists() else 'pending')
            rows.append(row)
    totals = {arm: {state: sum(r[arm] == state for r in rows) for state in ('success', 'failed', 'pending', 'excluded')}
              for arm in study.vb.ARMS}
    output = study.ROOT / 'results/verusbench-sonnet46-100-overview'
    report = {'selected': 100, 'mixed_resource_policies': True,
              'deduplication': 'Use 120s misc_filter rerun; do not double count its earlier 60s run',
              'totals': totals, 'rows': rows}
    write_json(output / 'overview.json', report)
    lines = ['# Sonnet 4.6: 100 distinct VerusBench IDs', '',
             'Exploratory aggregate: resource limits differ between cohorts. Do not interpret as one uniform 100-task experiment.', '',
             '| Cohort | IDs | With solved | Without solved | Pending in either arm |', '|---|---|---|---|---|']
    for policy, _, ids in groups:
        part = [r for r in rows if r['id'] in ids]
        lines.append(f"| {policy} | {len(part)} | {sum(r['with_internals'] == 'success' for r in part)} | {sum(r['without_internals'] == 'success' for r in part)} | {sum(any(r[a] == 'pending' for a in study.vb.ARMS) for r in part)} |")
    lines += ['', str(totals)]
    write_text(output / 'overview.md', '\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('Saved:', output)


if __name__ == '__main__':
    main()
