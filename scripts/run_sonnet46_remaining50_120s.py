"""Complementary 50-task batch, 120-second bounded proposals; no old results modified."""
import argparse
from collections import Counter
from pathlib import Path

from baseline.storage import digest, read_json, write_json, write_text
from scripts.claude_bounded import BoundedClaude, POLICY
from scripts.resume_sonnet46_remaining import provenance
from baseline.benchmark import load_tasks
from scripts.run_sonnet46_new25_120s import IDS as PREVIOUS25
from scripts.run_sonnet46_final25_120s import IDS as FINAL25
from scripts.resume_sonnet46_new25 import validate_quota_failure, archive

from verusbench_sonnet46 import __main__ as study

SELECTION = study.ROOT / 'configs/verusbench-sonnet46-remaining50-selection.json'
IDS = read_json(SELECTION)['ids']
LIMITS = {**POLICY, 'version': 'bounded-120s-v1', 'seconds_per_proposal': 120}
DEFAULT = study.ROOT / 'results/verusbench-sonnet46-remaining50-120s-v1'


class SyntaxLabelAdapter:
    """Keep the frozen runner's compilation-error branch compatible with syntax."""
    def __init__(self, inner):
        self.inner = inner

    def verify(self, path):
        result = self.inner.verify(path)
        if result.get('error_type') == 'syntax':
            return {**result, 'original_error_type': 'syntax', 'error_type': 'compilation'}
        return result


def implementation():
    return {name: digest((study.ROOT / name).read_bytes()) for name in
            ('scripts/run_sonnet46_remaining50_120s.py', 'scripts/claude_bounded.py')}


def summary(root):
    rows, counts = [], {}
    for task in IDS:
        shared = root / 'shared' / task / 'task.json'
        first = read_json(shared) if shared.exists() else None
        ready = read_json(root / 'inputs' / task / 'ready.json')
        if not ready.get('eligible', True):
            first = {'success': False, 'initially_verified': False, 'ineligible': True,
                     'exclusion_reason': ready['exclusion_reason']}
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
    complete = all(r['shared'] and (r['shared'].get('ineligible') or r['shared'].get('initially_verified') or r['shared']['success'] or all(r[a] for a in study.vb.ARMS)) for r in rows)
    ineligible = sum(bool(r['shared'] and r['shared'].get('ineligible')) for r in rows)
    initial = sum(bool(r['shared'] and r['shared'].get('initially_verified')) for r in rows)
    shared_successes = sum(bool(r['shared'] and r['shared']['success']) for r in rows)
    repair_candidates = [r for r in rows if r['shared'] and not r['shared'].get('initially_verified') and not r['shared'].get('ineligible') and not r['shared']['success']]
    totals = {arm: {'solved_including_shared': shared_successes + sum(bool(r[arm] and r[arm]['success']) for r in repair_candidates),
                   'repair_successes': sum(bool(r[arm] and r[arm]['success']) for r in repair_candidates),
                   'repairs_completed': sum(r[arm] is not None for r in repair_candidates)} for arm in study.vb.ARMS}
    report = {'ids': IDS, 'policy': LIMITS, 'complete': complete, 'rows': rows, 'proposal_outcomes': counts,
              'ineligible': ineligible, 'eligible': len(IDS) - ineligible, 'initially_verified': initial, 'shared_successes': shared_successes,
              'repair_candidates_so_far': len(repair_candidates), 'totals': totals}
    write_json(root / 'pilot-summary.json', report)
    lines = ['# Sonnet 4.6 Low: remaining 50 IDs / 120 seconds', '',
             '| Task | Shared first | With internals: final | Without internals: final |', '|---|---|---|---|']
    for r in rows:
        first = r['shared']
        def outcome(arm):
            if first and first.get('ineligible'):
                return 'ineligible (original policy violation)'
            if first and first.get('initially_verified'):
                return 'initially verified (excluded)'
            if first and first['success']:
                return 'success (shared)'
            return ('success' if r[arm]['success'] else 'failed') if r[arm] else 'pending'
        first_label = ('ineligible' if first.get('ineligible') else 'initially verified (excluded)' if first.get('initially_verified') else ('success' if first['success'] else 'failed')) if first else 'pending'
        lines.append(f"| {r['id']} | {first_label} | {outcome(study.vb.ARMS[0])} | {outcome(study.vb.ARMS[1])} |")
    lines += ['', f'Complete: {complete}; ineligible: {ineligible}; initially verified (excluded): {initial}; shared successes: {shared_successes}',
              f'Repair candidates so far: {len(repair_candidates)}', '']
    lines += [f'- {arm}: {values}' for arm, values in totals.items()]
    lines += ['', 'Proposal outcomes (resource stops are separate from rejected proofs):', '']
    lines += [f'- {arm}: {values}' for arm, values in counts.items()]
    write_text(root / 'pilot-summary.md', '\n'.join(lines) + '\n')
    print('\n'.join(lines), flush=True)


def selected_tasks():
    inventory = {t['id']: t for t in load_tasks(study.ROOT / 'data/manifest.json')}
    previous = set(read_json(study.SELECTION)['ids']) | set(PREVIOUS25) | set(FINAL25)
    if len(previous) != 100 or len(inventory) != 150:
        raise ValueError('Expected 100 previous IDs in the pinned 150-task inventory')
    if len(IDS) != 50 or len(set(IDS)) != 50 or set(IDS) != set(inventory) - previous:
        raise ValueError('Expected exactly the remaining 50 IDs')
    expected = [{k: inventory[i][k] for k in ('id', 'category', 'path', 'sha256')} for i in IDS]
    if read_json(SELECTION)['tasks'] != expected:
        raise ValueError('Selection source hashes changed')
    return [inventory[i] for i in IDS]


def fingerprints():
    return {'study': study.implementation(), 'driver': implementation(),
            'selection': digest(SELECTION.read_bytes()),
            'benchmark_manifest': digest((study.ROOT / 'data/manifest.json').read_bytes()),
            'earlier_selection_code': digest((study.ROOT / 'scripts/run_sonnet46_new25_120s.py').read_bytes())}


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
                'selection_rule': 'exact complement of previous 100 Sonnet 4.6 IDs; no outcome-based selection or replacements',
                'tools': study.vb.identity(runtime), 'config': config}
        if (root / 'pilot-plan.json').exists() and read_json(root / 'pilot-plan.json') != plan:
            raise ValueError('Preparation changed; use a new output')
        write_json(root / 'pilot-plan.json', plan)
        verifier, guard = study.vb.verify_tools(runtime, config)
        verifier = SyntaxLabelAdapter(verifier)
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
            if checked['error_type'] == 'verifier_error':
                raise RuntimeError('Original verifier infrastructure failure: ' + task['id'])
            eligible = integrity['valid']
            if not eligible and not (integrity.get('status') == 'invalid' and
                    integrity.get('reason', '').startswith('Forbidden trusted/bypass construct:')):
                raise RuntimeError('Unexpected original integrity failure: ' + task['id'] + '; inspect; no replacement')
            write_json(folder / 'ready.json', {'initially_verified': checked['success'], 'eligible': eligible,
                        'exclusion_reason': None if eligible else integrity['reason'],
                        'source_sha256': digest((folder / 'original.rs').read_bytes())})
            print('Prepared', task['id'], 'initially_verified=', checked['success'], 'eligible=', eligible, flush=True)
        write_json(root / 'manifest.json', {'config': config, 'tools': plan['tools'],
            'selection': [{k: t[k] for k in ('id', 'category', 'path', 'sha256')} for t in tasks],
            'files': {str(p.relative_to(root)): digest(p.read_bytes())
                      for p in (root / 'inputs').rglob('*') if p.is_file()}})
        validate(root)
    print('Prepared; no Claude inference requests:', root)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'status', 'release-quota'))
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--max-tasks', type=int, help='Optional limit on incomplete eligible tasks processed in this invocation')
    args = parser.parse_args()
    root = args.output.resolve()
    if args.max_tasks is not None and args.max_tasks < 1:
        parser.error('--max-tasks must be positive')
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
        if args.command == 'release-quota':
            folders = []
            for task in IDS:
                for arm in ('shared', *study.vb.ARMS):
                    for folder in (root / arm / task).glob('attempt_*'):
                        if (folder / 'claude-call.json').exists() and not (folder / 'response.json').exists() and not (folder / 'result.json').exists():
                            validate_quota_failure(folder)
                            folders.append(folder)
            for folder in folders:
                print('Archived zero-token quota rejection:', archive(root, folder))
            print('No Claude inference requests made.')
            return
        inference = BoundedClaude(study.load_tokenizer({'provider': 'claude_code'}), LIMITS)
        verifier, guard = study.vb.verify_tools(runtime, manifest['config'])
        verifier = SyntaxLabelAdapter(verifier)
        processed = 0
        try:
            for index, task in enumerate(manifest['selection']):
                if task['id'] not in IDS:
                    continue
                ready = read_json(root / 'inputs' / task['id'] / 'ready.json')
                if not ready['eligible']:
                    print('INELIGIBLE', task['id'], ready['exclusion_reason'], flush=True)
                    continue
                first_path = root / 'shared' / task['id'] / 'task.json'
                if first_path.exists():
                    first = read_json(first_path)
                    if first.get('initially_verified') or first['success'] or all((root / a / task['id'] / 'task.json').exists() for a in study.vb.ARMS):
                        continue
                if args.max_tasks is not None and processed >= args.max_tasks:
                    break
                processed += 1
                print('TASK', task['id'], flush=True)
                order = study.vb.ARMS if index % 2 == 0 else study.vb.ARMS[::-1]
                study.run_task(root, task, manifest['config'], inference, verifier, guard, order)
                summary(root)
        finally:
            summary(root)


if __name__ == '__main__':
    main()
