"""New user-selected 25-task study, 120-second bounded proposals."""
import argparse
from collections import Counter
from pathlib import Path

from baseline.storage import digest, read_json, write_json, write_text
from scripts.claude_bounded import BoundedClaude, POLICY
from scripts.resume_sonnet46_remaining import provenance
from baseline.benchmark import load_tasks

from verusbench_sonnet46 import __main__ as study

IDS = [
    "cloverbench_all_digits_strong",
    "diffy_conda",
    "diffy_ms4",
    "diffy_res1",
    "diffy_res2",
    "diffy_s3lif",
    "diffy_s4if",
    "diffy_s4lif",
    "diffy_s5if",
    "diffy_sina1",
    "diffy_sina5",
    "mbpp_task_id_133",
    "mbpp_task_id_170",
    "mbpp_task_id_579",
    "mbpp_task_id_586",
    "mbpp_task_id_588",
    "mbpp_task_id_70",
    "mbpp_task_id_728",
    "mbpp_task_id_764",
    "mbpp_task_id_807",
    "misc_arg_free",
    "misc_cell_2_sum",
    "misc_choose_odd",
    "misc_deduplicate",
    "misc_simple_nested"
]
LIMITS = {**POLICY, 'version': 'bounded-120s-v1', 'seconds_per_proposal': 120}
DEFAULT = study.ROOT / 'results/verusbench-sonnet46-new25-120s-v1'


def implementation():
    return {name: digest((study.ROOT / name).read_bytes()) for name in
            ('scripts/run_sonnet46_new25_120s.py', 'scripts/claude_bounded.py')}


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
    complete = all(r['shared'] and (r['shared'].get('initially_verified') or r['shared']['success'] or all(r[a] for a in study.vb.ARMS)) for r in rows)
    initial = sum(bool(r['shared'] and r['shared'].get('initially_verified')) for r in rows)
    shared_successes = sum(bool(r['shared'] and r['shared']['success']) for r in rows)
    repair_candidates = [r for r in rows if r['shared'] and not r['shared'].get('initially_verified') and not r['shared']['success']]
    totals = {arm: {'solved_including_shared': shared_successes + sum(bool(r[arm] and r[arm]['success']) for r in repair_candidates),
                   'repair_successes': sum(bool(r[arm] and r[arm]['success']) for r in repair_candidates),
                   'repairs_completed': sum(r[arm] is not None for r in repair_candidates)} for arm in study.vb.ARMS}
    report = {'ids': IDS, 'policy': LIMITS, 'complete': complete, 'rows': rows, 'proposal_outcomes': counts,
              'initially_verified': initial, 'shared_successes': shared_successes,
              'repair_candidates_so_far': len(repair_candidates), 'totals': totals}
    write_json(root / 'pilot-summary.json', report)
    lines = ['# Sonnet 4.6 Low: new 25 IDs / 120 seconds', '',
             '| Task | Shared first | With internals: final | Without internals: final |', '|---|---|---|---|']
    for r in rows:
        first = r['shared']
        def outcome(arm):
            if first and first.get('initially_verified'):
                return 'initially verified (excluded)'
            if first and first['success']:
                return 'success (shared)'
            return ('success' if r[arm]['success'] else 'failed') if r[arm] else 'pending'
        first_label = ('initially verified (excluded)' if first.get('initially_verified') else ('success' if first['success'] else 'failed')) if first else 'pending'
        lines.append(f"| {r['id']} | {first_label} | {outcome(study.vb.ARMS[0])} | {outcome(study.vb.ARMS[1])} |")
    lines += ['', f'Complete: {complete}; initially verified (excluded): {initial}; shared successes: {shared_successes}',
              f'Repair candidates so far: {len(repair_candidates)}', '']
    lines += [f'- {arm}: {values}' for arm, values in totals.items()]
    lines += ['', 'Proposal outcomes (resource stops are separate from rejected proofs):', '']
    lines += [f'- {arm}: {values}' for arm, values in counts.items()]
    write_text(root / 'pilot-summary.md', '\n'.join(lines) + '\n')
    print('\n'.join(lines), flush=True)


def selected_tasks():
    previous = set(read_json(study.SELECTION)['ids'])
    if len(IDS) != 25 or len(set(IDS)) != 25 or previous.intersection(IDS):
        raise ValueError('Expected 25 distinct IDs outside the previous 50')
    inventory = {t['id']: t for t in load_tasks(study.ROOT / 'data/manifest.json')}
    missing = [i for i in IDS if i not in inventory]
    if missing:
        raise ValueError('Unknown IDs; no silent replacement: ' + ', '.join(missing))
    return [inventory[i] for i in IDS]


def fingerprints():
    return {'study': study.implementation(), 'driver': implementation(),
            'benchmark_manifest': digest((study.ROOT / 'data/manifest.json').read_bytes())}


def validate(root):
    manifest = read_json(root / 'manifest.json')
    plan = read_json(root / 'pilot-plan.json')
    expected = [{k: t[k] for k in ('id', 'category', 'path', 'sha256')} for t in selected_tasks()]
    if (manifest['selection'] != expected or plan['ids'] != IDS or
            plan['policy'] != LIMITS or plan['fingerprints'] != fingerprints() or
            manifest['config'] != {**study.configuration(), 'count': len(IDS)}):
        raise ValueError('Frozen inputs/config/code changed; use a new output')
    for name, sha in manifest['files'].items():
        if digest((root / name).read_bytes()) != sha:
            raise ValueError('Frozen input changed: ' + name)
    return manifest


def prepare_new(root):
    if (root / 'manifest.json').exists():
        validate(root)
        print('Already prepared:', root)
        return
    root.mkdir(parents=True, exist_ok=True)
    with study.vb.run_lock(root):
        tasks = selected_tasks()
        config = {**study.configuration(), 'count': len(IDS)}
        runtime = study.vb.tools()
        plan = {'ids': IDS, 'policy': LIMITS, 'implementation': implementation(),
                'fingerprints': fingerprints(), 'runtime': provenance(),
                'selection_rule': 'exact user list in supplied order; disjoint from previous 50',
                'tools': study.vb.identity(runtime), 'config': config}
        if (root / 'pilot-plan.json').exists() and read_json(root / 'pilot-plan.json') != plan:
            raise ValueError('Preparation changed; use a new output')
        write_json(root / 'pilot-plan.json', plan)
        verifier, guard = study.vb.verify_tools(runtime, config)
        for task in tasks:
            folder = root / 'inputs' / task['id']
            if (folder / 'ready.json').exists():
                ready = read_json(folder / 'ready.json')
                if ready['source_sha256'] != digest((folder / 'original.rs').read_bytes()):
                    raise ValueError('Prepared input changed')
                continue
            write_text(folder / 'original.rs', Path(task['file']).read_text(encoding='utf-8'))
            checked = verifier.verify(folder / 'original.rs')
            integrity = guard.validate(folder / 'original.rs', folder / 'original.rs')
            write_json(folder / 'verification.json', checked)
            write_json(folder / 'integrity.json', integrity)
            if checked['error_type'] == 'verifier_error' or not integrity['valid']:
                raise RuntimeError('Original verifier/integrity failure: ' + task['id'] + '; inspect; no replacement')
            write_json(folder / 'ready.json', {'initially_verified': checked['success'],
                        'source_sha256': digest((folder / 'original.rs').read_bytes())})
            print('Prepared', task['id'], 'initially_verified=', checked['success'], flush=True)
        write_json(root / 'manifest.json', {'config': config, 'tools': plan['tools'],
            'selection': [{k: t[k] for k in ('id', 'category', 'path', 'sha256')} for t in tasks],
            'files': {str(p.relative_to(root)): digest(p.read_bytes())
                      for p in (root / 'inputs').rglob('*') if p.is_file()}})
        validate(root)
    print('Prepared; no Claude inference requests:', root)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'status'))
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    root = args.output.resolve()
    if args.command == 'prepare':
        prepare_new(root)
        return
    with study.vb.run_lock(root):
        manifest = validate(root)
        plan = read_json(root / 'pilot-plan.json')
        if plan['ids'] != IDS or plan['policy'] != LIMITS or plan['implementation'] != implementation():
            raise ValueError('Pilot policy/code changed; use a new output directory')
        if args.command == 'status':
            summary(root)
            return
        runtime = study.vb.tools()
        if study.vb.identity(runtime) != manifest['tools'] or provenance() != plan['runtime']:
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
