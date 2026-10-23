"""Localized repair ablation on the frozen candidates of a previous paired study."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

from baseline.__main__ import run_lock
from baseline.inference import LocalVLLM
from baseline.integrity import IntegrityValidator, tokens
from baseline.obligation import ObligationVerifier
from baseline.prompts import ROOT
from baseline.provenance import collect, file_hashes, tool_signature
from baseline.storage import digest, read_json, write_json, write_text
from repair_study.__main__ import configuration, tools, summarize as basic_summary
from repair_study.regions import apply_patch, regions
from .feedback import ARMS, exposed_payload, fit_payload, messages, next_payload


def implementation():
    return file_hashes([
        *(ROOT / 'local_ablation').glob('*.py'), *(ROOT / 'repair_study').glob('*.py'),
        *(ROOT / 'baseline').glob('*.py'), *(ROOT / 'prompts/repair-study').glob('*.txt'),
        ROOT / 'prompts/local-ablation/common.txt', ROOT / 'prompts/v4/system.txt',
        ROOT / 'configs/repair-study-48k.json', ROOT / 'diagnostics/z3_probe.py',
        ROOT / 'diagnostics/z3_internals.py'])


def validate(root):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation():
        raise ValueError('Ablation code/prompts changed; use another output directory')
    for name, expected in manifest['files'].items():
        if digest((root / name).read_bytes()) != expected:
            raise ValueError('Frozen input changed: ' + name)
    return manifest


def prepare(args):
    root, source = args.study.resolve(), args.source_study.resolve()
    if source == root or source in root.parents or root in source.parents:
        raise ValueError('Output must be separate from the previous study')
    if (root / 'manifest.json').exists():
        manifest = validate(root)
        if manifest['source_study'] != str(source):
            raise ValueError('Output already uses another source')
        print('Frozen ablation already prepared:', root)
        return
    previous = read_json(source / 'manifest.json')
    if previous['config'] != configuration():
        raise ValueError('Source must use the existing pinned repair-study-48k configuration')
    if not previous['cases']:
        raise ValueError('Source has no frozen candidates')
    config = dict(previous['config'], experiment='localized-internals-ablation-48k',
                  task_count=len(previous['cases']))
    plan = {'source_study': str(source), 'source_manifest_sha256': digest((source / 'manifest.json').read_bytes()),
            'cases': previous['cases'], 'tool_hashes': previous['tool_hashes'],
            'config': config, 'implementation': implementation()}
    if (root / 'preparation.json').exists() and read_json(root / 'preparation.json') != plan:
        raise ValueError('Preparation changed; use another output directory')
    write_json(root / 'preparation.json', plan)
    files = {}
    for task in previous['cases']:
        task_id = task['id']
        if Path(task_id).name != task_id or task_id in ('.', '..'):
            raise ValueError('Invalid task ID')
        # No later successful repairs are imported. Only the shared initial inputs.
        for name in ('candidate.rs', 'original.rs', 'verification.json', 'integrity.json', 'payload.json'):
            rel = f'inputs/{task_id}/{name}'
            data = (source / rel).read_bytes()
            if digest(data) != previous['files'].get(rel):
                raise ValueError('Previous frozen file failed its hash: ' + rel)
            destination = root / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            files[rel] = digest(data)
        folder = root / 'inputs' / task_id
        if read_json(folder / 'verification.json')['success'] or not read_json(folder / 'integrity.json')['valid']:
            raise ValueError('Source candidate is not a valid failed candidate: ' + task_id)
    write_json(root / 'manifest.json', {**plan, 'files': files,
        'scope': 'same frozen initial failed candidates; localized repair in both arms; optional solver data only'})
    print('Prepared', len(previous['cases']), 'frozen pairs:', root, flush=True)


def run_case(root, arm, task_id, config, inference, verifier, integrity):
    frozen = root / 'inputs' / task_id
    original = (frozen / 'original.rs').read_text(encoding='utf-8')
    current = (frozen / 'candidate.rs').read_text(encoding='utf-8')
    verification, check = read_json(frozen / 'verification.json'), read_json(frozen / 'integrity.json')
    payload = exposed_payload(arm, read_json(frozen / 'payload.json'))
    progress, records = '', []
    for index in range(1, config['max_repairs'] + 1):
        folder = root / arm / task_id / f'repair_{index:02}'
        if (folder / 'result.json').exists():
            record = read_json(folder / 'result.json')
        else:
            started = time.perf_counter()
            payload = fit_payload(payload, original, current, verification, check, inference.tokenizer, config, progress)
            prompt = messages(original, current, verification, check, payload, progress)
            common = messages(original, current, verification, check,
                              exposed_payload('without_internals', payload), progress)
            try:
                sites = regions(current)
            except ValueError:
                sites = []
            request = {'messages': prompt, 'seed': config['seed'] + index, 'parameters': config,
                       'candidate_sha256': digest(current.encode()), 'offered_sites': sites,
                       'payload_sha256': digest(json.dumps(payload, sort_keys=True).encode()),
                       'common_messages_sha256': digest(json.dumps(common, sort_keys=True).encode()),
                       'internals_exposed': payload['availability'] == 'available'}
            if (folder / 'request.json').exists() and read_json(folder / 'request.json') != request:
                raise ValueError('Saved request changed')
            write_json(folder / 'request.json', request)
            write_json(folder / 'payload-used.json', payload)
            if (folder / 'response.json').exists():
                response = read_json(folder / 'response.json')
            else:
                response = inference.generate(prompt, config, request['seed'])
                write_json(folder / 'response.json', response)
            write_text(folder / 'response.txt', response['text'])
            write_text(folder / 'rendered_prompt.txt', response['rendered_prompt'])
            edit_error, region_id = None, None
            try:
                code, region_id = apply_patch(current, response['text'], sites)
            except (ValueError, KeyError, TypeError) as error:
                code, edit_error = current, str(error)
            try:
                unchanged = tokens(code) == tokens(current)
            except ValueError:
                unchanged = code == current
            write_text(folder / 'candidate.rs', code)
            verified = verifier.verify(folder / 'candidate.rs')
            checked = integrity.validate(frozen / 'original.rs', folder / 'candidate.rs')
            write_json(folder / 'verification.json', verified)
            write_json(folder / 'integrity.json', checked)
            record = {'repair': index, 'success': verified['success'] and checked['valid'] and edit_error is None,
                      'unchanged': unchanged, 'edit_error': edit_error, 'region_id': region_id,
                      'editable_site_count': len(sites), 'before_error_type': verification.get('error_type'),
                      'error_type': verified['error_type'], 'integrity_valid': checked['valid'],
                      'input_tokens': response['input_tokens'], 'output_tokens': response['output_tokens'],
                      'truncated': response['truncated'], 'inference_seconds': response['inference_seconds'],
                      'processing_seconds': time.perf_counter() - started,
                      'payload_sha256': request['payload_sha256'], 'internals_exposed': request['internals_exposed']}
            write_json(folder / 'result.json', record)
        records.append(record)
        if record['success']:
            break
        current = (folder / 'candidate.rs').read_text(encoding='utf-8')
        verification, check = read_json(folder / 'verification.json'), read_json(folder / 'integrity.json')
        progress = ('Previous response made no effective token change. Make a concrete permitted proof change.'
                    if record['unchanged'] else 'Previous change failed; address the current diagnostics.')
        if record['edit_error']:
            progress += ' Invalid localized edit: ' + record['edit_error']
        if index < config['max_repairs']:
            started = time.perf_counter()
            cached = (folder / 'next-feedback.json').exists()
            payload = next_payload(arm, folder, original, current, verification, check,
                                   inference.tokenizer, config, progress)
            if not cached:
                record['feedback_seconds'] = time.perf_counter() - started
                write_json(folder / 'result.json', record)
    result = {'id': task_id, 'success': any(r['success'] for r in records), 'repairs': records}
    write_json(root / arm / task_id / 'task.json', result)
    print(arm, task_id, 'success' if result['success'] else 'failed', flush=True)
    return result


def summarize(root, arm):
    result = basic_summary(root, arm)
    # The engine/session is shared, not loaded separately for either arm.
    result.pop('model_load_seconds', None)
    result.pop('interrupted_sessions', None)
    rows = [read_json(p) for p in (root / arm).glob('*/repair_*/result.json')]
    result['edit_error_reasons'] = dict(Counter(r['edit_error'] for r in rows if r['edit_error']))
    result['internals']['withheld_by_design'] = len(rows) if arm == 'without_internals' else 0
    write_json(root / arm / 'summary.json', result)
    return result


def compare(root):
    manifest = validate(root)
    summaries = {arm: summarize(root, arm) for arm in ARMS}
    rows = []
    for task in manifest['cases']:
        frozen = root / 'inputs' / task['id']
        initial = read_json(frozen / 'payload.json')
        row = {'id': task['id'], 'category': task['category'],
               'initial_internals_available': initial['availability'] == 'available'}
        requests = []
        for arm in ARMS:
            folder = root / arm / task['id']
            row[arm] = read_json(folder / 'task.json')['success'] if (folder / 'task.json').exists() else None
            path = folder / 'repair_01/request.json'
            requests.append(read_json(path) if path.exists() else None)
        row['first_pair_valid'] = None
        row['first_prompts_identical'] = None
        if all(requests):
            a, b = requests
            row['first_pair_valid'] = (a['candidate_sha256'] == b['candidate_sha256'] == digest((frozen / 'candidate.rs').read_bytes())
                and a['seed'] == b['seed'] == manifest['config']['seed'] + 1
                and a['common_messages_sha256'] == b['common_messages_sha256']
                and a['parameters'] == b['parameters'] and a['offered_sites'] == b['offered_sites']
                and not b['internals_exposed'])
            row['first_prompts_identical'] = a['messages'] == b['messages']
        rows.append(row)
    strata = {}
    for available in (True, False):
        group = [r for r in rows if r['initial_internals_available'] == available]
        strata['initial_internals_available' if available else 'initial_internals_unavailable'] = {
            'expected': len(group),
            **{arm: sum(r[arm] is True for r in group) for arm in ARMS},
            'completed_pairs': sum(all(r[a] is not None for a in ARMS) for r in group)}
    sessions = [read_json(p) for p in root.glob('session-*.json')]
    report = {'summaries': summaries, 'paired': rows, 'strata': strata,
              'complete': all(s['completed_cases'] == s['expected_cases'] for s in summaries.values()),
              'first_pair_check_passed': all(r['first_pair_valid'] is True for r in rows),
              'with_only': [r['id'] for r in rows if r[ARMS[0]] is True and r[ARMS[1]] is False],
              'without_only': [r['id'] for r in rows if r[ARMS[1]] is True and r[ARMS[0]] is False],
              'shared_model_load_seconds': sum(s['model_load_seconds'] for s in sessions),
              'sessions': sessions,
              'scope': 'localized repair in both arms on the same saved failures; not a full 150-task generation run'}
    write_json(root / 'comparison.json', report)
    lines = ['# Localized repair: internals ablation', '',
             '| Arm | Completed | Solved | Unchanged | Edit errors |', '|---|---|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed_cases']}/{s['expected_cases']} | {s['solved']} | {s['unchanged']} | {s['invalid_local_edits']} |")
    lines += ['', '| Initial solver data | Candidates | With internals solved | Without internals solved |', '|---|---|---|---|']
    for name, s in strata.items():
        lines.append(f"| {name} | {s['expected']} | {s[ARMS[0]]} | {s[ARMS[1]]} |")
    lines += ['', f"Complete: {report['complete']}; initial pairs valid: {report['first_pair_check_passed']}",
              'Missing cases remain visible in summaries. Shared session/loading costs are not charged twice.',
              report['scope']]
    write_text(root / 'comparison.md', '\n'.join(lines))
    print(root / 'comparison.md', flush=True)
    return report


def run(args):
    root = args.study.resolve()
    manifest = validate(root)
    current_tools = tools()
    if {k: tool_signature(v) for k, v in current_tools.items()} != manifest['tool_hashes']:
        raise ValueError('Use the same Verus/Z3/Lynette binaries and solver API as the frozen study')
    config = manifest['config']
    runtime = dict(config, **{k: current_tools[k]['path'] for k in ('verus', 'z3', 'lynette')})
    provenance = collect(runtime)
    fingerprint = digest(json.dumps({'manifest': digest((root / 'manifest.json').read_bytes()),
        'versions': provenance['versions'], 'dependencies': provenance['dependency_lock_sha256'],
        'gpu_class': provenance['gpu']['name']}, sort_keys=True).encode())
    if (root / 'run.json').exists() and read_json(root / 'run.json')['fingerprint'] != fingerprint:
        raise ValueError('Runtime or GPU class changed; resume on the same GPU class or use another output directory')
    write_json(root / 'run.json', {'fingerprint': fingerprint, 'config': config,
        'design': 'one model; paired arms on same GPU; arm order alternates by task', 'provenance': provenance})
    pending = [(i, t) for i, t in enumerate(manifest['cases'])
               if any(not (root / a / t['id'] / 'task.json').exists() for a in ARMS)]
    if not pending:
        compare(root)
        return 0
    started = time.perf_counter()
    inference = LocalVLLM(config)
    session = {'model_load_seconds': time.perf_counter() - started,
               'gpu': provenance['gpu'], 'gpu_uuid': provenance.get('gpu_uuid')}
    session_path = root / f'session-{time.time_ns()}.json'
    write_json(session_path, session)
    verifier = ObligationVerifier(current_tools['verus']['path'], current_tools['z3']['path'], config['verification_timeout'])
    integrity = IntegrityValidator(current_tools['lynette']['path'])
    try:
        for index, task in pending:
            for arm in (ARMS if index % 2 == 0 else ARMS[::-1]):
                if (root / arm / task['id'] / 'task.json').exists():
                    continue
                try:
                    run_case(root, arm, task['id'], config, inference, verifier, integrity)
                except Exception as error:
                    write_json(root / arm / task['id'] / 'error.json', {'type': type(error).__name__, 'error': str(error)})
                    print(arm, task['id'], 'infrastructure error:', error, flush=True)
    finally:
        session['wall_seconds'] = time.perf_counter() - started
        write_json(session_path, session)
        report = compare(root)
    return 0 if report['complete'] and report['first_pair_check_passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'compare'))
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--source-study', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare' and args.source_study is None:
        parser.error('prepare requires --source-study')
    with run_lock(args.study.resolve()):
        if args.command == 'prepare':
            prepare(args)
        elif args.command == 'run':
            return run(args)
        else:
            compare(args.study.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
