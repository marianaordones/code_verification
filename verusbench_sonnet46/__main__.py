import argparse
import importlib.metadata
import json
import re
from pathlib import Path
import sys

from baseline.integrity import tokens
from baseline.provenance import file_hashes
from baseline.storage import digest, read_json, write_json, write_text
from .feedback import build_payload
from solver_needs_study.claude_code import ClaudeCode, preflight
from solver_needs_study.__main__ import load_tokenizer
from verusbench_study import __main__ as vb

ROOT = vb.ROOT
CONFIG = ROOT / 'configs/verusbench-sonnet46-50.json'
DEFAULT = ROOT / 'results/verusbench-sonnet46-low-shared50-14k-50x3-v1'
SELECTION = ROOT / 'configs/verusbench-sonnet46-50-selection.json'
PROMPT = ROOT / 'prompts/verusbench-sonnet46/solver-info.txt'


def configuration():
    cfg = read_json(CONFIG)
    expected = {'model': 'claude-sonnet-4-6', 'effort': 'low', 'count': 50,
        'max_attempts': 3, 'max_queries': 1, 'max_quantifiers': 50, 'max_instances_each': 3,
        'internals_token_budget': 14336, 'max_model_len': 49152, 'max_tokens': 4096,
        'seed': None, 'temperature': None}
    if any(cfg.get(k) != v for k, v in expected.items()):
        raise ValueError('Expected Sonnet 4.6 Low, 50 inputs, shared first + two repairs, 14k/50x3')
    return cfg


def selected_tasks():
    from baseline.benchmark import load_tasks, BENCHMARK_COMMIT
    selection = read_json(SELECTION)
    if selection['benchmark_commit'] != BENCHMARK_COMMIT or len(selection['ids']) != 50 or len(set(selection['ids'])) != 50:
        raise ValueError('Expected exact 50-ID VerusBench selection')
    inventory = {t['id']: t for t in load_tasks(ROOT / 'data/manifest.json')}
    tasks = [inventory[i] for i in selection['ids']]
    actual = [{k: t[k] for k in ('id', 'category', 'path', 'sha256')} for t in tasks]
    if actual != selection['tasks']:
        raise ValueError('User selection or original source hashes changed')
    return tasks


def messages(original, current, checked, integrity, payload, history):
    prompt = vb.messages(original, current, checked, integrity, payload, history)
    prompt[0]['content'] = (ROOT / 'prompts/v4/system.txt').read_text(encoding='utf-8') + '\n' + PROMPT.read_text(encoding='utf-8')
    return prompt


def exposure(payload, tokenizer):
    groups = (payload or {}).get('quantifiers', [])
    sizes = [len(g['instances']) for g in groups]
    block = '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>'
    return {'availability': (payload or {}).get('availability', 'withheld'),
        'groups': len(groups), 'instances': sum(sizes), 'max_instances_in_group': max(sizes, default=0),
        'internals_qwen_tokens': len(tokenizer.encode(block, add_special_tokens=False)) if payload else 0}


def known_input_parse_error(check):
    error = check.get('stderr', '')
    return (check.get('status') == 'checker_error' and not check.get('timed_out') and
        ((check.get('returncode') == 101 and 'LexError' in error and 'Result::unwrap()' in error) or
         (check.get('returncode') == 1 and re.search(r'\bSyn unable to parse file\b', error, re.IGNORECASE) is not None)))


def implementation():
    return file_hashes([*Path(__file__).parent.glob('*.py'), CONFIG, SELECTION, PROMPT,
        ROOT / 'prompts/v4/system.txt', ROOT / 'prompts/verusbench-claude/solver-info.txt',
        *ROOT.glob('baseline/*.py'), *ROOT.glob('diagnostics/*.py'),
        ROOT / 'repair_study/worker.py', ROOT / 'repair_study/relevance.py',
        ROOT / 'solver_needs_study/claude_code.py', ROOT / 'solver_needs_study/__main__.py',
        ROOT / 'verusbench_study/__main__.py'])


def validate(root):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation() or manifest['config'] != configuration():
        raise ValueError('Frozen implementation changed; use a new study')
    for name, sha in manifest['files'].items():
        if digest((root / name).read_bytes()) != sha:
            raise ValueError('Frozen input changed: ' + name)
    return manifest


def prepare(root):
    if (root / 'manifest.json').exists():
        validate(root)
        return
    cfg, runtime = configuration(), vb.tools()
    tasks = selected_tasks()
    plan = {'config': cfg, 'selection': read_json(SELECTION)['tasks'],
            'implementation': implementation(), 'tools': vb.identity(runtime)}
    if (root / 'preparation.json').exists() and read_json(root / 'preparation.json') != plan:
        raise ValueError('Preparation changed; use a new directory')
    write_json(root / 'preparation.json', plan)
    verifier, guard = vb.verify_tools(runtime, cfg)
    for task in tasks:
        folder = root / 'inputs' / task['id']
        if (folder / 'ready.json').exists():
            continue
        write_text(folder / 'original.rs', Path(task['file']).read_text(encoding='utf-8'))
        checked = verifier.verify(folder / 'original.rs')
        integrity = guard.validate(folder / 'original.rs', folder / 'original.rs')
        write_json(folder / 'verification.json', checked)
        write_json(folder / 'integrity.json', integrity)
        if checked['error_type'] == 'verifier_error' or not integrity['valid']:
            raise RuntimeError('Original tool/integrity failure for ' + task['id'] + '; no silent replacement')
        write_json(folder / 'ready.json', {'initially_verified': checked['success']})
        print('Prepared', task['id'], 'initially_verified=', checked['success'], flush=True)
    files = {str(p.relative_to(root)): digest(p.read_bytes()) for p in (root / 'inputs').rglob('*') if p.is_file()}
    write_json(root / 'manifest.json', {**plan, 'files': files})


def attempt(folder, index, original_path, current, checked, integrity, payload, history,
            cfg, inference, verifier, guard, shared_sha=None):
    if (folder / 'result.json').exists():
        return read_json(folder / 'result.json')
    packet = exposure(payload, inference.tokenizer)
    if (packet['internals_qwen_tokens'] > cfg['internals_token_budget'] or
            packet['groups'] > cfg['max_quantifiers'] or packet['max_instances_in_group'] > cfg['max_instances_each']):
        raise ValueError('Saved feedback exceeds the frozen packet limits')
    original = original_path.read_text(encoding='utf-8')
    prompt = messages(original, current, checked, integrity, payload, history)
    if len(inference.tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True)) + cfg['max_tokens'] > cfg['max_model_len']:
        raise ValueError('Prompt too large; no truncation permitted')
    common = messages(original, current, checked, integrity, None, history)
    request = {'messages': prompt, 'candidate_sha256': digest(current.encode()),
               'common_messages_sha256': digest(json.dumps(common, sort_keys=True).encode()),
               'shared_start_sha256': shared_sha, 'config': cfg, 'seed': None,
               'internals_exposed': bool(payload and payload['availability'] == 'available')}
    if (folder / 'request.json').exists() and read_json(folder / 'request.json') != request:
        raise ValueError('Pending request changed')
    write_json(folder / 'request.json', request)
    write_json(folder / 'exposure.json', packet)
    if (folder / 'response.json').exists():
        response = read_json(folder / 'response.json')
    else:
        response = inference.generate_at(prompt, cfg, folder)
        write_json(folder / 'response.json', response)
    error, form = None, None
    try:
        proposed, form = vb.extract_source(response['text'])
        if not proposed or tokens(proposed) == tokens(current):
            raise ValueError('Empty/unchanged proposal')
    except ValueError as exception:
        proposed, error = current, str(exception)
    write_text(folder / 'candidate.rs', proposed)
    check = guard.validate(original_path, folder / 'candidate.rs')
    write_json(folder / 'integrity.json', check)
    known_lexerror = known_input_parse_error(check)
    if check.get('status') == 'checker_error' and not known_lexerror:
        raise RuntimeError('Unknown integrity checker failure; no automatic retry')
    result = verifier.verify(folder / 'candidate.rs')
    write_json(folder / 'verification.json', result)
    if result['error_type'] == 'verifier_error':
        raise RuntimeError('Verifier infrastructure failure')
    if known_lexerror:
        if result['success'] or result['error_type'] != 'compilation':
            raise RuntimeError('Lynette parse error without a Verus compilation error; inspect manually')
        write_json(folder / 'integrity-before-recovery.json', check)
        check = {**check, 'valid': False, 'status': 'unparseable',
                 'recovery': 'known input LexError/Syn parse error; Verus also rejected malformed source'}
        write_json(folder / 'integrity.json', check)
    record = {'attempt': index, 'success': bool(result['success'] and check['valid'] and error is None),
              'edit_error': error, 'integrity_valid': check['valid'], 'error_type': result['error_type'],
              'extraction': form, 'internals_exposed': request['internals_exposed']}
    write_json(folder / 'result.json', record)
    return record


def state(folder):
    return ((folder / 'candidate.rs').read_text(encoding='utf-8'),
            read_json(folder / 'verification.json'), read_json(folder / 'integrity.json'))


def run_task(root, task, cfg, inference, verifier, guard, order):
    frozen = root / 'inputs' / task['id']
    original_path = frozen / 'original.rs'
    checked, integrity = read_json(frozen / 'verification.json'), read_json(frozen / 'integrity.json')
    common = root / 'shared' / task['id'] / 'attempt_01'
    if checked['success']:
        write_json(root / 'shared' / task['id'] / 'task.json', {'initially_verified': True, 'success': False})
        return
    first = attempt(common, 1, original_path, original_path.read_text(encoding='utf-8'),
                    checked, integrity, None, [], cfg, inference, verifier, guard)
    write_json(root / 'shared' / task['id'] / 'task.json', {'initially_verified': False, 'success': first['success']})
    if first['success']:
        return
    current, checked, integrity = state(common)
    history = [first]
    if not (common / 'payload.json').exists():
        build_payload(common, original_path.read_text(encoding='utf-8'), current, checked, integrity,
                      inference.tokenizer, cfg, json.dumps(history), prompt_builder=messages)
    # Freeze all fork inputs, including the one original model response.
    files = {name: digest((common / name).read_bytes()) for name in
             ('request.json', 'response.json', 'candidate.rs', 'verification.json', 'integrity.json', 'result.json', 'payload.json')}
    checkpoint = common / 'shared-state.json'
    if checkpoint.exists() and read_json(checkpoint) != files:
        raise ValueError('Shared first proposal changed')
    write_json(checkpoint, files)
    shared_sha = digest(checkpoint.read_bytes())
    for arm in order:
        output = root / arm / task['id']
        if (output / 'task.json').exists():
            continue
        current, checked, integrity = state(common)
        history, records = [first], []
        payload = read_json(common / 'payload.json') if arm == vb.ARMS[0] else None
        for index in (2, 3):
            folder = output / f'attempt_{index:02}'
            record = attempt(folder, index, original_path, current, checked, integrity, payload,
                             history, cfg, inference, verifier, guard, shared_sha)
            records.append(record)
            if record['success']:
                break
            current, checked, integrity = state(folder)
            history.append(record)
            if index == 2 and arm == vb.ARMS[0]:
                if (folder / 'payload.json').exists():
                    payload = read_json(folder / 'payload.json')
                else:
                    payload = build_payload(folder, original_path.read_text(encoding='utf-8'), current,
                        checked, integrity, inference.tokenizer, cfg, json.dumps(history), prompt_builder=messages)
        write_json(output / 'task.json', {'success': any(r['success'] for r in records), 'attempts': records,
                                         'shared_start_sha256': shared_sha})
        print(arm, task['id'], 'repaired=', any(r['success'] for r in records), flush=True)


def compare(root):
    manifest = validate(root)
    rows = []
    for task in manifest['selection']:
        common = root / 'shared' / task['id']
        first = read_json(common / 'task.json') if (common / 'task.json').exists() else None
        row = {'id': task['id'], 'first': first}
        requests = []
        for arm in vb.ARMS:
            folder = root / arm / task['id']
            row[arm] = read_json(folder / 'task.json') if (folder / 'task.json').exists() else None
            path = folder / 'attempt_02/request.json'
            requests.append(read_json(path) if path.exists() else None)
        row['fork_valid'] = None
        if all(requests):
            a, b = requests
            row['fork_valid'] = (a['candidate_sha256'] == b['candidate_sha256'] and
                a['common_messages_sha256'] == b['common_messages_sha256'] and
                a['shared_start_sha256'] == b['shared_start_sha256'] and not b['internals_exposed'] and
                a['config'] == b['config'])
        rows.append(row)
    failures = [r for r in rows if r['first'] and not r['first']['initially_verified'] and not r['first']['success']]
    initial = sum(bool(r['first'] and r['first']['initially_verified']) for r in rows)
    first_successes = sum(bool(r['first'] and r['first']['success']) for r in rows)
    summaries = {}
    for arm in vb.ARMS:
        done = [r[arm] for r in failures if r[arm] is not None]
        summaries[arm] = {'repair_denominator_so_far': len(failures), 'completed': len(done),
            'repaired_at_2': sum(any(a['success'] and a['attempt'] == 2 for a in t['attempts']) for t in done),
            'repaired_at_3': sum(any(a['success'] and a['attempt'] == 3 for a in t['attempts']) for t in done),
            'repaired': sum(t['success'] for t in done), 'attempts': sum(len(t['attempts']) for t in done),
            'exposed_attempts': sum(a['internals_exposed'] for t in done for a in t['attempts'])}
    report = {'shared_first_successes': first_successes, 'initially_verified': initial,
        'shared_first_completed': sum(r['first'] is not None for r in rows), 'paired': rows,
        'summaries': summaries, 'complete': all(r['first'] is not None for r in rows) and
             all(s['completed'] == len(failures) for s in summaries.values()),
        'fork_checks_passed': all(r['fork_valid'] is True for r in failures)}
    write_json(root / 'comparison.json', report)
    report['with_only'] = [r['id'] for r in failures if r[vb.ARMS[0]] and r[vb.ARMS[1]] and r[vb.ARMS[0]]['success'] and not r[vb.ARMS[1]]['success']]
    report['without_only'] = [r['id'] for r in failures if r[vb.ARMS[0]] and r[vb.ARMS[1]] and r[vb.ARMS[1]]['success'] and not r[vb.ARMS[0]]['success']]
    write_json(root / 'comparison.json', report)
    lines = ['# Sonnet 4.6 Low: shared first proposal, then paired repair (14k, 50x3)', '',
             f'Selected: {len(rows)}; initially verified: {initial}; shared first successes: {first_successes}.',
             f'Failed shared candidates available for repair: {len(failures)}.', '',
             '| Arm | Completed repairs | Success at proposal 2 | Success at proposal 3 | Total repaired |',
             '|---|---|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{len(failures)} | {s['repaired_at_2']} | {s['repaired_at_3']} | {s['repaired']} |")
    lines += ['', f"Complete: {report['complete']}; fork checks passed: {report['fork_checks_passed']}",
              'First-proposal successes are common and are not credited as repairs to either arm.']
    write_text(root / 'comparison.md', '\n'.join(lines))
    return report


def run(root):
    manifest, runtime = validate(root), vb.tools()
    if vb.identity(runtime) != manifest['tools']:
        raise ValueError('Toolchain changed')
    provenance = {'cli': preflight(), 'python': sys.version, 'versions': {p: importlib.metadata.version(p)
                  for p in ('transformers', 'tokenizers', 'z3-solver')}}
    if (root / 'runtime.json').exists() and read_json(root / 'runtime.json') != provenance:
        raise ValueError('Runtime changed')
    write_json(root / 'runtime.json', provenance)
    inference = ClaudeCode(load_tokenizer({'provider': 'claude_code'}))
    verifier, guard = vb.verify_tools(runtime, manifest['config'])
    try:
        for index, task in enumerate(manifest['selection']):
            run_task(root, task, manifest['config'], inference, verifier, guard,
                     vb.ARMS if index % 2 == 0 else vb.ARMS[::-1])
    finally:
        compare(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'compare'))
    parser.add_argument('--study', type=Path, default=DEFAULT)
    args = parser.parse_args()
    root = args.study.resolve()
    with vb.run_lock(root):
        {'prepare': prepare, 'run': run, 'compare': compare}[args.command](root)


if __name__ == '__main__':
    main()
