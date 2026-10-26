"""Read-only three-proposal comparison. Python 3 standard library only."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARMS = ('with_internals', 'without_internals')
LABELS = ('AX', 'INST-forall', 'INST-witness', 'NLA', 'FUEL', 'Other')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_studies(paths, budget):
    rows, sources = {}, []
    for root in paths:
        manifest_path = root / 'manifest.json'
        manifest = load(manifest_path)
        config = manifest['config']
        if config.get('complement_token_budget'):
            raise ValueError('Use the original 24k/50x3 run, not the complement experiment: ' + str(root))
        if (config['internals_token_budget'], config['max_quantifiers'], config['max_instances_each']) != (budget, 20 if budget == 12288 else 50, 3):
            raise ValueError('Unexpected feedback configuration: ' + str(root))
        sources.append({'path': str(root), 'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                        'config': config, 'implementation_hashes': manifest.get('implementation')})
        for case in manifest['cases']:
            key = case['id']
            if key in rows:
                raise ValueError('Duplicate task across batches: ' + key)
            row = {'id': key, 'label': case['paper_label'], 'study': str(root), 'arms': {}}
            verification = root / 'inputs' / key / 'verification.json'
            row['initially_verified'] = load(verification)['success'] if verification.exists() else False
            for arm in ARMS:
                folder = root / arm / key
                task_path = folder / 'task.json'
                if task_path.exists():
                    task = load(task_path)
                    if task.get('initially_verified'):
                        row['initially_verified'] = True
                    records = task['attempts']
                else:
                    records = [load(p) for p in sorted(folder.glob('attempt_*/result.json'))]
                attempts = {}
                for record in records:
                    number = record['attempt']
                    if type(number) is not int or number < 1 or number in attempts:
                        raise ValueError('Invalid/duplicate one-based proposal number: ' + str(folder))
                    if type(record['success']) is not bool:
                        raise ValueError('Invalid success field: ' + str(folder))
                    attempts[number] = record['success']
                # A success after proposal 3 is explicitly NOT a three-proposal success.
                first = min((n for n, success in attempts.items() if success), default=None)
                if first is not None and any(n not in attempts for n in range(1, min(first, 3) + 1)):
                    raise ValueError('Missing earlier proposal records: ' + str(folder))
                row['arms'][arm] = {'first_success': first, 'solved': first is not None and first <= 3,
                    'complete_at_three': (first is not None and first <= 3) or all(n in attempts for n in (1, 2, 3)),
                    'success_only_after_three': first is not None and first > 3}
            rows[key] = row
    return rows, sources


def summarize(rows):
    eligible = [r for r in rows if not r['initially_verified']]
    value = {'selected': len(rows), 'denominator': len(eligible),
             'initially_verified': len(rows) - len(eligible), 'arms': {}, 'categories': {}}
    for arm in ARMS:
        value['arms'][arm] = {'solved': sum(r['arms'][arm]['solved'] for r in eligible),
            'completed_at_three': sum(r['arms'][arm]['complete_at_three'] for r in eligible),
            'missing_ids': [r['id'] for r in eligible if not r['arms'][arm]['complete_at_three']],
            'success_only_after_three_ids': [r['id'] for r in eligible if r['arms'][arm]['success_only_after_three']],
            'solved_by_proposal': {str(k): sum(r['arms'][arm]['first_success'] is not None and
                r['arms'][arm]['first_success'] <= k for r in eligible) for k in (1, 2, 3)}}
    value['complete'] = all(not a['missing_ids'] for a in value['arms'].values())
    for label in LABELS:
        selected = [r for r in eligible if r['label'] == label]
        value['categories'][label] = {'n': len(selected), **{
            arm: sum(r['arms'][arm]['solved'] for r in selected) for arm in ARMS}}
    value['with_only'] = [r['id'] for r in eligible if r['arms'][ARMS[0]]['solved'] and not r['arms'][ARMS[1]]['solved']]
    value['without_only'] = [r['id'] for r in eligible if r['arms'][ARMS[1]]['solved'] and not r['arms'][ARMS[0]]['solved']]
    return value


def latex(groups):
    lines = [r'% Requires \usepackage{booktabs}', r'\begin{table}[htbp]', r'    \centering',
        r'    \caption{Repairs within three proposals on the same 462 Solver Needs tasks. Limits are maxima.}',
        r'    \label{tab:solver-needs-full-budget-comparison}', r'    \begin{tabular}{lrrrrr}', r'        \toprule',
        r'        \shortstack{Internals\\tokens} & \shortstack{Groups $\times$\\instances} & Tasks & \shortstack{With\\internals} & \shortstack{Without\\internals} & Gain \\',
        r'        \midrule']
    for name, budget, sample in [('previous_full', '12,288', '$20 \\times 3$'), ('current_full', '24,576', '$50 \\times 3$')]:
        g = groups[name]; n = g['denominator']; a, b = [g['arms'][arm]['solved'] for arm in ARMS]
        lines.append(f'        {budget} & {sample} & {n} & {a} ({100*a/n:.1f}\\%) & {b} ({100*b/n:.1f}\\%) & {a-b:+d} \\\\')
    lines += [r'        \bottomrule', r'    \end{tabular}', r'\end{table}', '',
        r'\begin{table}[htbp]', r'    \centering',
        r'    \caption{Repairs by missing-assertion category within three proposals.}',
        r'    \label{tab:solver-needs-full-category-comparison}', r'    \begin{tabular}{lrrrrrrr}',
        r'        \toprule', r'        & & \multicolumn{3}{c}{12,288 tokens; $20 \times 3$} & \multicolumn{3}{c}{24,576 tokens; $50 \times 3$} \\',
        r'        \cmidrule(lr){3-5}\cmidrule(lr){6-8}',
        r'        Category & Tasks & With & Without & Gain & With & Without & Gain \\', r'        \midrule']
    for label in LABELS:
        old, new = [groups[name]['categories'][label] for name in ('previous_full', 'current_full')]
        a, b, c, d = old[ARMS[0]], old[ARMS[1]], new[ARMS[0]], new[ARMS[1]]
        lines.append(f'        {label} & {old["n"]} & {a} & {b} & {a-b:+d} & {c} & {d} & {c-d:+d} \\\\')
    lines += [r'        \bottomrule', r'    \end{tabular}', r'\end{table}', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    previous = ROOT.parent / 'code_verification'
    parser.add_argument('--previous', nargs='+', type=Path, default=[
        previous / 'results/solver-needs-qwen14b-100/seed-20261018',
        previous / 'results/solver-needs-qwen14b-remaining362/seed-20261018'])
    parser.add_argument('--current-first100', type=Path, default=ROOT / 'results/solver-needs-qwen14b-100-internals24k/seed-20261018')
    parser.add_argument('--current-remaining362', type=Path, default=ROOT / 'results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018')
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis/solver-needs-full-three-proposals')
    args = parser.parse_args()
    paths = [p.resolve() for p in [*args.previous, args.current_first100, args.current_remaining362]]
    output = args.output.resolve()
    if any(output == p or output.is_relative_to(p) for p in paths):
        parser.error('Output must be outside all saved study directories')
    old, old_sources = read_studies([p.resolve() for p in args.previous], 12288)
    new, new_sources = read_studies([args.current_first100.resolve(), args.current_remaining362.resolve()], 24576)
    if len(old) != 462 or set(old) != set(new):
        raise ValueError('Expected the same 462 unique task IDs in both complete configurations')
    if any(old[i]['label'] != new[i]['label'] or old[i]['initially_verified'] != new[i]['initially_verified'] for i in old):
        raise ValueError('Labels or initial eligibility differ between configurations')
    remaining_ids = {key for key, row in new.items() if Path(row['study']) == args.current_remaining362.resolve()}
    if len(remaining_ids) != 362:
        raise ValueError('Expected exactly 362 tasks in the continuation and 100 in its original batch')
    groups = {'previous_full': summarize(list(old.values())), 'current_full': summarize(list(new.values())),
              'previous_remaining362': summarize([old[key] for key in sorted(remaining_ids)]),
              'current_remaining362': summarize([new[key] for key in sorted(remaining_ids)])}
    report = {'proposal_limit': 3, 'groups': groups, 'sources': {'previous': old_sources, 'current': new_sources},
        'cases': {'previous': list(old.values()), 'current': list(new.values())},
        'scope': 'Saved records only. No inference, solver, or current-code hash validation. Does not certify unchanged prompts during the original jobs.'}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# Solver Needs: at most three proposals', '', report['scope'], '',
        '| Configuration | Tasks | Completed with / without | With internals | Without internals | Gain |', '|---|---|---|---|---|---|']
    for name, g in groups.items():
        a, b = [g['arms'][arm] for arm in ARMS]; n = g['denominator']
        lines.append(f'| {name} | {n} | {a["completed_at_three"]} / {b["completed_at_three"]} | {a["solved"]} ({a["solved"]/n:.1%}) | {b["solved"]} ({b["solved"]/n:.1%}) | {a["solved"]-b["solved"]:+d} |')
    complete = all(g['complete'] for g in groups.values())
    if complete:
        (output / 'tables.tex').write_text(latex(groups), encoding='utf-8')
    else:
        lines += ['', 'INCOMPLETE: missing cases are listed in comparison.json. Final LaTeX tables were not generated.']
        if (output / 'tables.tex').exists():
            (output / 'tables.tex').write_text('% INCOMPLETE: see comparison.json; no final table.\n', encoding='utf-8')
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    print('\nOutput:', output)
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
