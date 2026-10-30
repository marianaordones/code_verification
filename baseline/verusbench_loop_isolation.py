"""One internals arm, loop_isolation(false),105 frozen failures, two GPU shards."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random
import shutil
import time

from . import verusbench_local_v2 as local
from .__main__ import run_lock
from .benchmark import load_tasks
from .inference import LocalVLLM, extract_code
from .integrity import IntegrityValidator, lexical_check
from .loop_isolation import force_false
from .obligation import ObligationVerifier
from .prompts import ROOT
from .provenance import collect, file_hashes, tool_signature
from .storage import digest, read_json, write_json, write_text

DEFAULT_SOURCE = Path('results/verusbench-qwen14b-three-arms/seed-20261018')
DEFAULT_OUTPUT = Path('results/verusbench-loop-isolation-false/seed-20261018')


def implementation():
    return {**local.implementation(), **file_hashes([ROOT / 'prompts/verusbench-loop-isolation.txt'])}


def split_ids(ids, seed=20261018):
    if len(ids) != 105 or len(set(ids)) != 105:
        raise ValueError('Expected exactly105 distinct historical failures')
    values = sorted(ids)
    random.Random(seed).shuffle(values)
    return {'batch50': sorted(values[:50]), 'batch55': sorted(values[50:])}


def validate(root, batch=None):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation():
        raise ValueError('Code/prompts changed after preparation; use a NEW output directory')
    batches = manifest['batches']
    expected = split_ids([r['id'] for r in manifest['tasks']], manifest['config']['seed'])
    if batches != expected or batch is not None and batch not in batches:
        raise ValueError('Frozen shard partition changed or unknown batch')
    selected = set(batches[batch]) if batch else {r['id'] for r in manifest['tasks']}
    for name, sha in manifest['files'].items():
        parts = Path(name).parts
        if batch and len(parts) > 2 and parts[0] == 'frozen' and parts[2] not in selected:
            continue
        if digest((root / name).read_bytes()) != sha:
            raise ValueError('Frozen input changed: ' + name)
    return manifest


def prepare(source, root):
    source, root = source.resolve(), root.resolve()
    if source == root or source in root.parents or root in source.parents:
        raise ValueError('Source and output must be separate')
    if (root / 'manifest.json').exists():
        m = validate(root)
        if m['source'] != str(source):
            raise ValueError('Already prepared from another source')
        print('Already prepared:', root)
        return
    previous = read_json(source / 'run.json')
    config = {**previous['config'], 'experiment': 'verusbench-loop-isolation-false-base24k-105',
        'max_repairs': 2, 'max_attempts': 3, 'editor_version': 2, 'loop_isolation_fixed': True,
        'internals_token_budget': 24576, 'max_quantifiers': 50, 'max_instances_each': 3,
        'max_queries': 3, 'replay_max_instances': 5, 'collect_inventory': False,
        'extra_system_prompt': (ROOT / 'prompts/verusbench-loop-isolation.txt').read_text(encoding='utf-8')}
    config.pop('complement_token_budget', None)
    if (config['max_model_len'], config['max_tokens'], config['seed']) != (65536, 4096, 20261018):
        raise ValueError('Expected the previous64k three-arm VerusBench run')
    tasks = {t['id']: t for t in load_tasks(ROOT / 'data/manifest.json')}
    if len(tasks) != 150 or set(tasks) != {t['id'] for t in previous['tasks']}:
        raise ValueError('Source must contain the same150 official tasks')
    rows, excluded = [], []
    for old in previous['tasks']:
        task = tasks[old['id']]
        if task['sha256'] != old['sha256']:
            raise ValueError('Original benchmark input changed')
        initial = source / 'shared' / task['id'] / 'attempt_00'
        check, verified, result = [read_json(initial / name) for name in ('integrity.json', 'verification.json', 'result.json')]
        if result['success'] != bool(check['valid'] and verified['success']):
            raise ValueError('Inconsistent original success: ' + task['id'])
        if result['success'] or not check['valid']:
            excluded.append({'id': task['id'], 'status': 'initial_success' if result['success'] else check.get('status', 'integrity_rejected')})
            continue
        code = (initial / 'candidate.rs').read_text(encoding='utf-8')
        request, response = read_json(initial / 'request.json'), read_json(initial / 'response.json')
        if request['input_sha256'] != task['sha256'] or code != extract_code(response['text'], config['enable_thinking']):
            raise ValueError('Saved initial candidate/request mismatch: ' + task['id'])
        sites, audit = local.audit_sites(code)
        if not sites:
            raise ValueError('Historical failure has no corrected-editor sites: ' + task['id'])
        original = Path(task['file']).read_text(encoding='utf-8')
        changed_original, original_changes = force_false(original)
        changed, changes = force_false(code)
        valid, reason = lexical_check(changed_original, changed)
        if not valid:
            raise ValueError('Fixed option conflicts with preservation: ' + task['id'] + ': ' + reason)
        if not local.audit_sites(changed)[0]:
            raise ValueError('No sites after harness transformation')
        folder = root / 'frozen' / 'inputs' / task['id']
        for name, text in [('original.rs', changed_original), ('candidate.rs', changed), ('source-original.rs', original), ('source-candidate.rs', code)]:
            write_text(folder / name, text)
        write_json(folder / 'source-verification.json', verified)
        write_json(folder / 'source-integrity.json', check)
        write_json(folder / 'transformation.json', {'original': original_changes, 'candidate': changes,
            'source_request_sha256': digest((initial / 'request.json').read_bytes()),
            'source_response_sha256': digest((initial / 'response.json').read_bytes())})
        rows.append({k: task[k] for k in ('id', 'category', 'sha256')})
    batches = split_ids([r['id'] for r in rows], config['seed'])
    write_json(root / 'selected_ids.json', {'ids': sorted(r['id'] for r in rows), 'batches': batches, 'excluded': excluded})
    files = {str(p.relative_to(root)): digest(p.read_bytes()) for p in (root / 'frozen').rglob('*') if p.is_file()}
    files['selected_ids.json'] = digest((root / 'selected_ids.json').read_bytes())
    write_json(root / 'manifest.json', {'source': str(source), 'source_run_sha256': digest((source / 'run.json').read_bytes()),
        'config': config, 'tasks': rows, 'excluded': excluded, 'batches': batches,
        'tools': previous['tools'], 'solver_api': previous['solver_api'], 'implementation': implementation(), 'files': files,
        'scope': '105 original valid failures; fixed loop_isolation(false); one internals arm; two new localized repairs; fresh solver queries'})
    print('Prepared105 frozen failures; batch50=50,batch55=55', flush=True)


def stage_initial(root, shard, row, verifier, integrity):
    frozen = root / 'frozen/inputs' / row['id']
    folder = shard / 'inputs' / row['id']
    ready = folder / 'ready.json'
    if ready.exists():
        value = read_json(ready)
        for name, sha in value['files'].items():
            if digest((folder / name).read_bytes()) != sha:
                raise ValueError('Changed option-only verification input/artifact')
        for name in ('candidate.rs', 'original.rs'):
            if (folder / name).read_bytes() != (frozen / name).read_bytes():
                raise ValueError('Option-only input differs from frozen setting')
        return value['setting_only_success']
    for name in ('candidate.rs', 'original.rs'):
        write_text(folder / name, (frozen / name).read_text(encoding='utf-8'))
    write_text(folder / 'initial/candidate.rs', (folder / 'candidate.rs').read_text(encoding='utf-8'))
    check = integrity.validate(folder / 'original.rs', folder / 'initial/candidate.rs')
    result = verifier.verify(folder / 'initial/candidate.rs')
    write_json(folder / 'integrity.json', check)
    write_json(folder / 'verification.json', result)
    if not check['valid'] or result.get('error_type') == 'verifier_error':
        raise RuntimeError('Fixed-setting preservation/tool failure; inspect staged diagnostics, not counted as model failure')
    write_json(folder / 'editor-audit.json', local.audit_sites((folder / 'candidate.rs').read_text(encoding='utf-8'))[1])
    files = {str(p.relative_to(folder)): digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file() and not p.name.endswith('.tmp') and p.name != 'ready.json'}
    write_json(ready, {'files': files, 'setting_only_success': result['success'],
        'scope': 'new Verus check with false setting; no LLM proposal; no old SMT events reused'})
    return result['success']


def run_batch(root, batch):
    m = validate(root, batch)
    shard = root / batch
    config = dict(m['config'])
    for name, env in [('verus', 'VERUS_BIN'), ('z3', 'Z3_BIN'), ('lynette', 'LYNETTE_BIN')]:
        config[name] = os.environ.get(env, name)
    identity = collect(config)
    if m['tools'] != {n: tool_signature(identity[n]) for n in ('verus', 'z3', 'lynette')} or m['solver_api'] != identity['solver_api']:
        raise ValueError('Tool versions differ from the source run')
    runtime = {'manifest_sha256': digest((root / 'manifest.json').read_bytes()), 'versions': identity['versions'], 'gpu': identity['gpu'], 'batch': batch}
    if (shard / 'runtime.json').exists() and read_json(shard / 'runtime.json') != runtime:
        raise ValueError('Shard runtime/GPU class changed')
    write_json(shard / 'runtime.json', runtime)
    os.environ['VERUS_Z3_PATH'] = identity['z3']['path']
    verifier = ObligationVerifier(identity['verus']['path'], identity['z3']['path'], config['verification_timeout'])
    integrity = IntegrityValidator(identity['lynette']['path'])
    rows = {r['id']: r for r in m['tasks']}
    pending = []
    for key in m['batches'][batch]:
        if (shard / 'with_internals' / key / 'task.json').exists():
            continue
        try:
            if stage_initial(root, shard, rows[key], verifier, integrity):
                write_json(shard / 'with_internals' / key / 'task.json', {'id': key, 'success': True, 'status': 'setting_only_success', 'repairs': []})
                print(batch, key, 'verified by option alone', flush=True)
            else:
                pending.append(rows[key])
        except Exception as error:
            write_json(shard / 'errors' / (key + '.json'), {'phase': 'setting_check', 'error': str(error)})
            print(batch, key, 'setting check error:', error, flush=True)
    if not pending:
        return 0 if summarize(root, batch)['complete'] else 1
    started = time.perf_counter()
    try:
        inference = LocalVLLM(config)
    except Exception as error:
        write_json(shard / 'initialization-error.json', {'error': str(error), 'policy': 'fixed64k, no silent fallback'})
        raise
    inference.tokenizer.model_max_length = config['max_model_len']
    session = {'model_load_seconds': time.perf_counter() - started, 'provenance': identity}
    try:
        for row in pending:
            try:
                local.run_case(shard, 'with_internals', row, m['config'], inference, verifier, integrity)
            except Exception as error:
                write_json(shard / 'errors' / (row['id'] + '.json'), {'phase': 'repair', 'error': str(error)})
                print(batch, row['id'], 'repair error:', error, flush=True)
    finally:
        session['wall_seconds_including_model_load'] = time.perf_counter() - started
        write_json(shard / ('session-' + str(time.time_ns()) + '.json'), session)
        report = summarize(root, batch)
    return 0 if report['complete'] else 1


def summarize(root, batch=None):
    m = validate(root, batch)
    batches = [batch] if batch else list(m['batches'])
    rows, requests = [], []
    category_by_id = {r['id']: r.get('category', 'unknown') for r in m['tasks']}
    for part in batches:
        for key in m['batches'][part]:
            path = root / part / 'with_internals' / key / 'task.json'
            value = read_json(path) if path.exists() else None
            rows.append({'id': key, 'category': category_by_id[key], 'batch': part, 'result': value})
            requests.extend(read_json(p) for p in path.parent.glob('repair_*/request.json'))
    completed = [r['result'] for r in rows if r['result'] is not None]
    records = [a for t in completed for a in t['repairs']]
    setting = sum(t['status'] == 'setting_only_success' for t in completed)
    curve = {str(k): sum(t['status'] == 'setting_only_success' or any(r['success'] and r['repair'] <= k for r in t['repairs']) for t in completed) for k in (0, 1, 2)}
    report = {'expected': len(rows), 'completed': len(completed), 'complete': len(completed) == len(rows),
        'setting_only_successes': setting, 'model_repaired': sum(t['success'] and t['status'] != 'setting_only_success' for t in completed),
        'solved': sum(t['success'] for t in completed), 'solved_by_new_repairs': curve,
        'model_proposals': len(records), 'unchanged': sum(r['unchanged'] for r in records),
        'edit_error_reasons': dict(Counter(r['edit_error'] for r in records if r['edit_error'])),
        'integrity_statuses': dict(Counter(r['integrity_status'] for r in records)),
        'inference_seconds': sum(r['inference_seconds'] for r in records),
        'by_category': {c: {'selected': sum(r['category'] == c for r in rows),
            'setting_only': sum(r['category'] == c and r['result'] is not None and r['result']['status'] == 'setting_only_success' for r in rows),
            'model_repaired': sum(r['category'] == c and r['result'] is not None and r['result']['success'] and r['result']['status'] != 'setting_only_success' for r in rows)} for c in sorted(set(category_by_id.values()))},
        'proposal_statuses': dict(Counter(r['status'] for r in records)),
        'input_tokens': sum(r['input_tokens'] for r in records), 'output_tokens': sum(r['output_tokens'] for r in records),
        'truncated': sum(r['truncated'] for r in records), 'internals_exposed': sum(r['internals_exposed'] for r in records),
        'context_violations': sum(r['headroom_after_output_reserve'] < 0 for r in requests),
        'minimum_context_headroom': min((r['headroom_after_output_reserve'] for r in requests), default=None),
        'missing': [r['id'] for r in rows if r['result'] is None], 'cases': rows,
        'scope': m['scope'], 'partitions': {part: m['batches'][part] for part in batches}}
    destination = root / batch if batch else root
    write_json(destination / 'comparison.json', report)
    lines = ['# VerusBench: fixed loop_isolation(false), internals only', '',
        '| Completed | Option alone | Option + 1 repair | Option + 2 repairs | Model repairs only |', '|---|---|---|---|---|',
        f"| {report['completed']}/{report['expected']} | {curve['0']} | {curve['1']} | {curve['2']} | {report['model_repaired']} |", '',
        'Historical denominator:105 valid failures. Option-only success is NOT credited to model repair.',
        'At most2 new LLM repairs after the saved generation; no control arm. Fresh option-specific queries.',
        f"Complete: {report['complete']}; missing cases: {len(report['missing'])}"]
    lines += ['', '| Category | Selected | Option alone | Model repairs |', '|---|---|---|---|']
    for c, value in report['by_category'].items():
        lines.append(f"| {c} | {value['selected']} | {value['setting_only']} | {value['model_repaired']} |")
    write_text(destination / 'comparison.md', '\n'.join(lines))
    print(destination / 'comparison.md', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'compare'))
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--batch', choices=('batch50', 'batch55'))
    args = parser.parse_args()
    root = args.output.resolve()
    if args.command == 'run' and not args.batch:
        parser.error('run requires --batch batch50 or batch55')
    lock = root / args.batch if args.command == 'run' else root
    with run_lock(lock):
        if args.command == 'prepare':
            prepare(args.source, root)
            return 0
        if args.command == 'run':
            return run_batch(root, args.batch)
        summarize(root, args.batch)
        return 0

if __name__ == '__main__':
    raise SystemExit(main())
