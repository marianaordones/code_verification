"""Prepare once, run full/local repair jobs separately, compare paired outcomes."""
import argparse
from collections import Counter
import importlib.metadata
import json
import os
from pathlib import Path
import random
import sys
import time

from baseline.__main__ import run_lock
from baseline.benchmark import load_tasks
from baseline.inference import LocalVLLM, extract_code, model_identity
from baseline.integrity import IntegrityValidator, tokens
from baseline.obligation import ObligationVerifier
from baseline.prompts import ROOT
from baseline.provenance import collect, file_hashes, tool_identity, tool_signature, command
from baseline.storage import digest, read_json, write_json, write_text
from diagnostics.z3_internals import api_identity
from .feedback import build_payload, messages, PROMPTS
from .regions import regions, apply_patch
from .relevance import qids


def configuration():
    config = read_json(ROOT / 'configs/repair-study-48k.json')
    model_identity(config)
    if (config['max_model_len'] != 49152 or config['internals_token_budget'] != 24576
            or config['max_tokens'] != 4096 or config['max_repairs'] != 2):
        raise ValueError('Unexpected declared study budget')
    return config


def implementation():
    return file_hashes([*(ROOT / 'repair_study').glob('*.py'), *PROMPTS.glob('*.txt'),
                        ROOT / 'configs/repair-study-48k.json',
                        ROOT / 'prompts/v4/system.txt', *(ROOT / 'baseline').glob('*.py'),
                        ROOT / 'diagnostics/z3_probe.py', ROOT / 'diagnostics/z3_internals.py'])


def tools():
    result = {name: tool_identity(os.environ[env]) for name, env in (
        ('verus', 'VERUS_BIN'), ('z3', 'Z3_BIN'), ('lynette', 'LYNETTE_BIN'))}
    if '33269ac' not in str(command([result['verus']['path'], '--version'])):
        raise ValueError('Study requires the benchmark-compatible Verus build')
    result['solver_api'] = api_identity()
    return result


def validate_bundle(root):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation():
        raise ValueError('Study code/prompts changed; use a new study directory')
    for name, expected in manifest['files'].items():
        path = root / name
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError('Frozen study file changed: ' + name)
    return manifest


def select_candidates(source, count):
    official = {t['id']: t for t in load_tasks(ROOT / 'data/manifest.json')}
    pools = {key: [] for key in ('omitted_source_events', 'arithmetic', 'other_smt', 'compilation')}
    for task_id, task in sorted(official.items()):
        folder = source / task_id / 'attempt_00'
        if not (folder / 'result.json').exists():
            continue
        result, check = read_json(folder / 'result.json'), read_json(folder / 'integrity.json')
        if result['success'] or not check['valid']:
            continue
        code = (folder / 'candidate.rs').read_text(encoding='utf-8')
        try:
            if not regions(code):
                continue
        except ValueError:
            continue
        raw = folder / 'internals/replay/instantiations.jsonl'
        raw_has_source = raw.exists() and any(
            any(q.startswith('user_candidate') for q in qids(json.loads(line)['quantifier_smt']))
            for line in raw.read_text(encoding='utf-8').splitlines() if line.strip())
        payload_file = folder / 'internals/payload.json'
        old = read_json(payload_file) if payload_file.exists() else {}
        selected_has_source = any(any(qid.startswith('user_candidate') for qid in qids(q['quantifier_smt']))
                                  for q in old.get('quantifiers', []))
        if raw_has_source and not selected_has_source:
            pool = 'omitted_source_events'
        elif 'arithmetic' in (old.get('reason_unknown') or ''):
            pool = 'arithmetic'
        elif result.get('error_type') == 'compilation':
            pool = 'compilation'
        else:
            pool = 'other_smt'
        pools[pool].append({'id': task_id, 'category': task['category'], 'original': task['file'],
                            'source_folder': str(folder), 'selection_stratum': pool})
    rng = random.Random(20261018)
    for pool in pools.values():
        rng.shuffle(pool)
    selected = []
    while any(pools.values()) and (count == 0 or len(selected) < count):
        for pool in pools.values():
            if pool and (count == 0 or len(selected) < count):
                selected.append(pool.pop())
    if count and len(selected) != count:
        raise ValueError(f'Only {len(selected)} eligible initial failed candidates; requested {count}')
    return selected


def prepare(args):
    root, source = args.study.resolve(), args.source_run.resolve()
    if source == root or source in root.parents or root in source.parents:
        raise ValueError('Use a separate study directory outside the original run')
    if (root / 'manifest.json').exists():
        manifest = validate_bundle(root)
        if manifest['source_run'] != str(source) or manifest['requested_count'] != args.count:
            raise ValueError('Prepared study has a different source/count')
        print('Shared frozen inputs already prepared:', root)
        return
    config = configuration()
    source_metadata = read_json(source / 'run.json')
    if model_identity(source_metadata['config']) != model_identity(config):
        raise ValueError('Source candidates must use the same pinned Coder model')
    identities = tools()
    selected = select_candidates(source, args.count)
    selection = [{**t, 'candidate_sha256': digest((Path(t['source_folder']) / 'candidate.rs').read_bytes()),
                  'original_sha256': digest(Path(t['original']).read_bytes())} for t in selected]
    plan = {'source_run': str(source), 'requested_count': args.count, 'selection': selection,
            'implementation': implementation(), 'tool_hashes': {k: tool_signature(v) for k, v in identities.items()}}
    if (root / 'preparation.json').exists() and read_json(root / 'preparation.json') != plan:
        raise ValueError('Preparation inputs changed; use a new directory')
    write_json(root / 'preparation.json', plan)
    from transformers import AutoTokenizer
    if importlib.metadata.version('transformers') != '4.51.3':
        raise ValueError('Use the existing pinned transformers runtime')
    model, revision = model_identity(config)
    model_dir = ROOT / '.cluster/models' / model.split('/')[-1] / revision
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    tokenizer.model_max_length = 10**12
    verifier = ObligationVerifier(identities['verus']['path'], identities['z3']['path'], 120)
    integrity = IntegrityValidator(identities['lynette']['path'])
    cases = []
    for task in selection:
        folder = root / 'inputs' / task['id']
        if not (folder / 'ready.json').exists():
            start = time.perf_counter()
            code = (Path(task['source_folder']) / 'candidate.rs').read_text(encoding='utf-8')
            original = Path(task['original']).read_text(encoding='utf-8')
            write_text(folder / 'candidate.rs', code)
            write_text(folder / 'original.rs', original)
            verification = verifier.verify(folder / 'candidate.rs')
            check = integrity.validate(folder / 'original.rs', folder / 'candidate.rs')
            write_json(folder / 'verification.json', verification)
            write_json(folder / 'integrity.json', check)
            if verification['success'] or not check['valid']:
                raise ValueError(task['id'] + ': frozen candidate no longer eligible after revalidation')
            payload = build_payload(folder, original, code, verification, check, tokenizer, config)
            write_json(folder / 'ready.json', {'seconds': time.perf_counter() - start,
                       'payload_sha256': digest((folder / 'payload.json').read_bytes())})
        cases.append({k: task[k] for k in ('id', 'category', 'selection_stratum')})
        print('Prepared', task['id'], flush=True)
    files = {str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted((root / 'inputs').rglob('*')) if p.is_file()}
    manifest = {**plan, 'cases': cases, 'config': config, 'files': files,
                'scope': 'repair-only pilot; all selected initial candidates failed and passed integrity'}
    write_json(root / 'manifest.json', manifest)
    print('Prepared shared study:', root / 'manifest.json', flush=True)


def run(args):
    root = args.study.resolve()
    manifest = validate_bundle(root)
    config = manifest['config']
    current_tools = tools()
    if {k: tool_signature(v) for k, v in current_tools.items()} != manifest['tool_hashes']:
        raise ValueError('Prepared inputs and repair jobs must use identical tool binaries/API')
    output = root / args.mode
    runtime_config = dict(config, verus=current_tools['verus']['path'], z3=current_tools['z3']['path'],
                          lynette=current_tools['lynette']['path'])
    provenance = collect(runtime_config)
    fingerprint = digest(json.dumps({'manifest': digest((root / 'manifest.json').read_bytes()),
                         'mode': args.mode, 'versions': provenance['versions'],
                         'dependencies': provenance['dependency_lock_sha256']}, sort_keys=True).encode())
    with run_lock(output):
        if (output / 'run.json').exists() and read_json(output / 'run.json')['fingerprint'] != fingerprint:
            raise ValueError('Run changed; use a new study directory')
        write_json(output / 'run.json', {'fingerprint': fingerprint, 'mode': args.mode, 'provenance': provenance,
                   'config': config, 'manifest_sha256': digest((root / 'manifest.json').read_bytes())})
        start = time.perf_counter()
        inference = LocalVLLM(config)
        verifier = ObligationVerifier(current_tools['verus']['path'], current_tools['z3']['path'], 120)
        integrity = IntegrityValidator(current_tools['lynette']['path'])
        session = {'model_load_seconds': time.perf_counter() - start}
        session_path = output / f'session-{time.time_ns()}.json'
        write_json(session_path, session)
        errors = 0
        for task in manifest['cases']:
            try:
                run_case(root, output, task['id'], args.mode, config, inference, verifier, integrity)
            except Exception as error:
                errors += 1
                write_json(output / task['id'] / 'error.json', {'error': str(error), 'type': type(error).__name__})
                print(task['id'], 'infrastructure error:', error, flush=True)
        session['wall_seconds'] = time.perf_counter() - start
        write_json(session_path, session)
        summarize(root, args.mode)
        return 1 if errors else 0


def run_case(root, output, task_id, mode, config, inference, verifier, integrity):
    frozen = root / 'inputs' / task_id
    original = (frozen / 'original.rs').read_text(encoding='utf-8')
    current = (frozen / 'candidate.rs').read_text(encoding='utf-8')
    verification, check = read_json(frozen / 'verification.json'), read_json(frozen / 'integrity.json')
    payload = read_json(frozen / 'payload.json')
    progress, records = '', []
    for index in range(1, 3):
        folder = output / task_id / f'repair_{index:02}'
        if (folder / 'result.json').exists():
            record = read_json(folder / 'result.json')
        else:
            start = time.perf_counter()
            request = {'messages': messages(mode, original, current, verification, check, payload, progress),
                       'seed': config['seed'] + index, 'parameters': config,
                       'candidate_sha256': digest(current.encode()),
                       'payload_sha256': digest(json.dumps(payload, sort_keys=True).encode())}
            try:
                offered = regions(current)
            except ValueError:
                offered = []
            request['offered_sites'] = offered if mode == 'local' else None
            ids = inference.tokenizer.apply_chat_template(request['messages'], tokenize=True, add_generation_prompt=True)
            if len(ids) + config['max_tokens'] > config['max_model_len']:
                raise ValueError('Prompt does not fit; no automatic truncation')
            if (folder / 'request.json').exists() and read_json(folder / 'request.json') != request:
                raise ValueError('Saved request changed')
            write_json(folder / 'request.json', request)
            write_json(folder / 'payload-used.json', payload)
            if (folder / 'response.json').exists():
                response = read_json(folder / 'response.json')
            else:
                response = inference.generate(request['messages'], config, request['seed'])
                write_json(folder / 'response.json', response)
            write_text(folder / 'response.txt', response['text'])
            write_text(folder / 'rendered_prompt.txt', response['rendered_prompt'])
            invalid_edit, region_id = None, None
            if mode == 'full':
                code = extract_code(response['text'], False)
            else:
                try:
                    code, region_id = apply_patch(current, response['text'], offered)
                except (ValueError, KeyError, TypeError) as error:
                    invalid_edit = str(error)
                    code = current  # Counts as a failed attempt, never as a hidden retry.
            try:
                unchanged = tokens(code) == tokens(current)
            except ValueError:
                unchanged = code == current
            write_text(folder / 'candidate.rs', code)
            verification_new = verifier.verify(folder / 'candidate.rs')
            check_new = integrity.validate(frozen / 'original.rs', folder / 'candidate.rs')
            write_json(folder / 'verification.json', verification_new)
            write_json(folder / 'integrity.json', check_new)
            record = {'repair': index, 'success': verification_new['success'] and check_new['valid'] and invalid_edit is None,
                      'unchanged': unchanged, 'edit_error': invalid_edit, 'region_id': region_id,
                      'editable_site_count': len(offered) if mode == 'local' else None,
                      'before_error_type': verification.get('error_type'),
                      'error_type': verification_new['error_type'], 'integrity_valid': check_new['valid'],
                      'input_tokens': response['input_tokens'], 'output_tokens': response['output_tokens'],
                      'truncated': response['truncated'], 'inference_seconds': response['inference_seconds'],
                      'processing_seconds': time.perf_counter() - start,
                      'payload_sha256': request['payload_sha256']}
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
        if index < 2:
            # A fresh, branch-specific replay is legitimate after the shared first repair.
            if (folder / 'payload.json').exists():
                payload = read_json(folder / 'payload.json')
            else:
                start = time.perf_counter()
                payload = build_payload(folder, original, current, verification, check,
                                        inference.tokenizer, config, progress)
                record['feedback_seconds'] = time.perf_counter() - start
                write_json(folder / 'result.json', record)
    result = {'id': task_id, 'success': any(r['success'] for r in records), 'repairs': records}
    write_json(output / task_id / 'task.json', result)
    print(mode, task_id, 'success' if result['success'] else 'failed', flush=True)
    return result


def summarize(root, mode):
    manifest = read_json(root / 'manifest.json')
    results = [read_json(root / mode / t['id'] / 'task.json') for t in manifest['cases']
               if (root / mode / t['id'] / 'task.json').exists()]
    attempts = [a for t in results for a in t['repairs']]
    sessions = [read_json(p) for p in (root / mode).glob('session-*.json')]
    payloads = [read_json(root / mode / t['id'] / f"repair_{a['repair']:02}" / 'payload-used.json')
                for t in results for a in t['repairs']]
    summary = {'mode': mode, 'expected_cases': len(manifest['cases']), 'completed_cases': len(results),
               'solved': sum(t['success'] for t in results),
               'success_after_repairs': {str(k): sum(any(a['success'] and a['repair'] <= k for a in t['repairs'])
                                                    for t in results) for k in (1, 2)},
               'attempts': len(attempts), 'unchanged': sum(a['unchanged'] for a in attempts),
               'invalid_local_edits': sum(a['edit_error'] is not None for a in attempts),
               'no_editable_sites': sum(a.get('editable_site_count') == 0 for a in attempts),
               'compilation_or_syntax_attempts': sum(a['error_type'] in ('compilation', 'syntax') for a in attempts),
               'transitions': dict(Counter(str(a.get('before_error_type')) + ' -> ' + str(a['error_type']) for a in attempts)),
               'errors': dict(Counter(a['error_type'] for a in attempts)),
               'integrity_rejections': sum(not a['integrity_valid'] for a in attempts),
               'input_tokens': sum(a['input_tokens'] for a in attempts),
               'output_tokens': sum(a['output_tokens'] for a in attempts),
               'inference_seconds': sum(a['inference_seconds'] for a in attempts),
               'model_load_seconds': sum(s['model_load_seconds'] for s in sessions),
               'interrupted_sessions': sum('wall_seconds' not in s for s in sessions),
               'processing_seconds': sum(a['processing_seconds'] + a.get('feedback_seconds', 0) for a in attempts),
               'internals': {'feedbacks': len(payloads),
                   'available': sum(p.get('availability') == 'available' for p in payloads),
                   'with_candidate_groups': sum(any(q['selection_category'].startswith('candidate') for q in p.get('quantifiers', [])) for p in payloads),
                   'group_categories': dict(Counter(q['selection_category'] for p in payloads for q in p.get('quantifiers', [])))},
               'missing_cases': [t['id'] for t in manifest['cases'] if not (root / mode / t['id'] / 'task.json').exists()]}
    write_json(root / mode / 'summary.json', summary)
    return summary


def compare(args):
    root = args.study.resolve()
    manifest = validate_bundle(root)
    summaries = {mode: summarize(root, mode) for mode in ('full', 'local')}
    rows = []
    for task in manifest['cases']:
        row = {'id': task['id']}
        hashes = []
        for mode in ('full', 'local'):
            path = root / mode / task['id'] / 'task.json'
            row[mode] = read_json(path)['success'] if path.exists() else None
            request = root / mode / task['id'] / 'repair_01/request.json'
            hashes.append(read_json(request)['payload_sha256'] if request.exists() else None)
        row['first_payload_identical'] = hashes[0] == hashes[1] if all(hashes) else None
        rows.append(row)
    report = {'summaries': summaries, 'paired': rows,
              'shared_preparation_seconds': sum(read_json(root / 'inputs' / t['id'] / 'ready.json')['seconds']
                                                for t in manifest['cases']),
              'first_payload_check_passed': (all(r['first_payload_identical'] is not False for r in rows)
                                            if any(r['first_payload_identical'] is not None for r in rows) else None),
              'full_only': [r['id'] for r in rows if r['full'] is True and r['local'] is False],
              'local_only': [r['id'] for r in rows if r['local'] is True and r['full'] is False],
              'scope': 'repair-only comparison on frozen failed candidates; not full VerusBench success rates'}
    write_json(root / 'comparison.json', report)
    text = ['# Paired repair study', '', '| Mode | Completed | Solved | Unchanged attempts | Invalid local edits |', '|---|---|---|---|---|']
    for mode, s in summaries.items():
        text.append(f"| {mode} | {s['completed_cases']}/{s['expected_cases']} | {s['solved']} | {s['unchanged']} | {s['invalid_local_edits']} |")
    text += ['', report['scope'], 'See comparison.json for paired IDs, missing cases, and first-payload equality.']
    write_text(root / 'comparison.md', '\n'.join(text))
    print(root / 'comparison.md')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run', 'compare'])
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--source-run', type=Path)
    parser.add_argument('--count', type=int, default=30, help='0 = all eligible initial candidates')
    parser.add_argument('--mode', choices=['full', 'local'])
    args = parser.parse_args()
    if args.count < 0:
        parser.error('count must be nonnegative')
    if args.command == 'prepare':
        if args.source_run is None:
            parser.error('prepare requires --source-run')
        with run_lock(args.study.resolve()):
            prepare(args)
    elif args.command == 'run':
        if args.mode is None:
            parser.error('run requires --mode')
        return run(args)
    else:
        compare(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
