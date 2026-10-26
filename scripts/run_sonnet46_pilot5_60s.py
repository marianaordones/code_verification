"""Fixed five-task, 60-second pilot; original study stays unchanged."""
import argparse
from collections import Counter
from pathlib import Path
import shutil

from baseline.storage import digest, read_json, write_json, write_text
from scripts.claude_bounded import BoundedClaude, POLICY
from scripts.resume_sonnet46_remaining import pending_tasks, provenance
from verusbench_sonnet46 import __main__ as study

IDS = ['misc_conditional_average', 'misc_fib', 'misc_filter', 'misc_findmax', 'misc_len_intersect']
LIMITS = {**POLICY, 'version': 'bounded-60s-v1', 'seconds_per_proposal': 60}
DEFAULT = study.ROOT / 'results/verusbench-sonnet46-pilot5-60s-v1'


def implementation():
    return {name: digest((study.ROOT / name).read_bytes()) for name in
            ('scripts/run_sonnet46_pilot5_60s.py', 'scripts/claude_bounded.py')}


def summary(root):
    rows, counts = [], {}
    for task in IDS:
        shared = root / 'shared' / task / 'task.json'
        first = read_json(shared) if shared.exists() else None
        row = {'id': task, 'shared': first}
        for arm in study.vb.ARMS:
            path = root / arm / task / 'task.json'
            row[arm] = read_json(path) if path.exists() else None
        rows.append(row)
    for arm in ('shared', *study.vb.ARMS):
        outcomes = Counter()
        for task in IDS:
            for folder in (root / arm / task).glob('attempt_*'):
                response, result = folder / 'response.json', folder / 'result.json'
                if not response.exists():
                    if (folder / 'claude-call.json').exists():
                        outcomes['incomplete_infrastructure'] += 1
                    continue
                r = read_json(response)
                if r.get('resource_exhausted'):
                    outcomes[r['resource_stop_reason']] += 1
                elif result.exists():
                    record = read_json(result)
                    outcomes['success' if record['success'] else ('invalid_proposal' if record.get('edit_error') else 'rejected_proposal')] += 1
                else:
                    outcomes['verification_pending'] += 1
        counts[arm] = dict(outcomes)
    complete = all(r['shared'] and (r['shared']['success'] or all(r[a] for a in study.vb.ARMS)) for r in rows)
    report = {'ids': IDS, 'policy': LIMITS, 'complete': complete, 'rows': rows, 'proposal_outcomes': counts}
    write_json(root / 'pilot-summary.json', report)
    lines = ['# Sonnet 4.6 Low: five-task / 60-second pilot', '',
             '| Task | Shared first | With internals: final | Without internals: final |', '|---|---|---|---|']
    for r in rows:
        first = r['shared']
        def outcome(arm):
            if first and first['success']:
                return 'success (shared)'
            return ('success' if r[arm]['success'] else 'failed') if r[arm] else 'pending'
        lines.append(f"| {r['id']} | {('success' if first['success'] else 'failed') if first else 'pending'} | {outcome(study.vb.ARMS[0])} | {outcome(study.vb.ARMS[1])} |")
    lines += ['', f'Complete: {complete}', '', 'Proposal outcomes (resource stops are separate from rejected proofs):', '']
    lines += [f'- {arm}: {values}' for arm, values in counts.items()]
    write_text(root / 'pilot-summary.md', '\n'.join(lines) + '\n')
    print('\n'.join(lines), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'status'))
    parser.add_argument('--source', type=Path, default=study.DEFAULT)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    root, source = args.output.resolve(), args.source.resolve()
    if root == source or root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError('Use a separate output directory')
    if args.command == 'prepare':
        with study.vb.run_lock(source):
            manifest = study.validate(source)
            pending = {t['id'] for _, t in pending_tasks(source, manifest)}
            if not set(IDS).issubset(pending):
                raise ValueError('Fixed selection is no longer pending; inspect before changing selection')
            if root.exists():
                raise ValueError('Output exists; use run or status')
            root.mkdir(parents=True)
            shutil.copy2(source / 'manifest.json', root / 'manifest.json')
            shutil.copytree(source / 'inputs', root / 'inputs')
            write_json(root / 'pilot-plan.json', {'ids': IDS, 'policy': LIMITS, 'implementation': implementation(),
                'source': str(source), 'source_runtime': read_json(source / 'runtime.json'),
                'selection_rule': 'next five pending IDs in original order, excluding misc_bubble already tested in bounded pilot'})
            study.validate(root)
        print('Prepared; no Claude requests:', root)
        return
    with study.vb.run_lock(root):
        manifest = study.validate(root)
        plan = read_json(root / 'pilot-plan.json')
        if plan['ids'] != IDS or plan['policy'] != LIMITS or plan['implementation'] != implementation():
            raise ValueError('Pilot policy/code changed; use a new output directory')
        if args.command == 'status':
            summary(root)
            return
        runtime = study.vb.tools()
        if study.vb.identity(runtime) != manifest['tools'] or provenance() != plan['source_runtime']:
            raise ValueError('Toolchain/CLI/runtime changed')
        inference = BoundedClaude(study.load_tokenizer({'provider': 'claude_code'}), LIMITS)
        verifier, guard = study.vb.verify_tools(runtime, manifest['config'])
        try:
            for index, task in enumerate(manifest['selection']):
                if task['id'] not in IDS:
                    continue
                print('TASK', task['id'], flush=True)
                order = study.vb.ARMS if index % 2 == 0 else study.vb.ARMS[::-1]
                study.run_task(root, task, manifest['config'], inference, verifier, guard, order)
                summary(root)
        finally:
            summary(root)


if __name__ == '__main__':
    main()
