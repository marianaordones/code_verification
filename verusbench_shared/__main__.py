import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

from baseline.integrity import tokens
from baseline.provenance import file_hashes
from baseline.storage import digest, read_json, write_json, write_text
from repair_study.feedback import build_payload
from solver_needs_study.claude_code import ClaudeCode, preflight
from solver_needs_study.__main__ import load_tokenizer
from verusbench_study import __main__ as vb

ROOT = vb.ROOT
CONFIG = ROOT / 'configs/verusbench-shared20.json'
DEFAULT = ROOT / 'results/verusbench-shared20-sonnet-low-v1'


def implementation():
    return {**vb.implementation(CONFIG), **file_hashes(Path(__file__).parent.glob('*.py'))}


def validate(root):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation():
        raise ValueError('Frozen implementation changed; use a new study')
    for name, sha in manifest['files'].items():
        if digest((root / name).read_bytes()) != sha:
            raise ValueError('Frozen input changed: ' + name)
    return manifest


def prepare(root):
    if (root / 'manifest.json').exists():
        validate(root)
        return
    # Existing preparation is reused without altering the previous runner.
    vb.prepare(root, CONFIG)
    manifest = read_json(root / 'manifest.json')
    manifest['implementation'] = implementation()
    manifest['protocol'] = 'one shared proposal without internals; failed candidates fork for proposals 2 and 3'
    write_json(root / 'manifest.json', manifest)


def attempt(folder, index, original_path, current, checked, integrity, payload, history,
            cfg, inference, verifier, guard, shared_sha=None):
    if (folder / 'result.json').exists():
        return read_json(folder / 'result.json')
    original = original_path.read_text(encoding='utf-8')
    prompt = vb.messages(original, current, checked, integrity, payload, history)
    if len(inference.tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True)) + cfg['max_tokens'] > cfg['max_model_len']:
        raise ValueError('Prompt too large; no truncation permitted')
    common = vb.messages(original, current, checked, integrity, None, history)
    request = {'messages': prompt, 'candidate_sha256': digest(current.encode()),
               'common_messages_sha256': digest(json.dumps(common, sort_keys=True).encode()),
               'shared_start_sha256': shared_sha, 'config': cfg, 'seed': None,
               'internals_exposed': bool(payload and payload['availability'] == 'available')}
    if (folder / 'request.json').exists() and read_json(folder / 'request.json') != request:
        raise ValueError('Pending request changed')
    write_json(folder / 'request.json', request)
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
    known_lexerror = (check.get('status') == 'checker_error' and not check.get('timed_out') and
                     check.get('returncode') == 101 and 'LexError' in check.get('stderr', '') and
                     'Result::unwrap()' in check.get('stderr', ''))
    if check.get('status') == 'checker_error' and not known_lexerror:
        raise RuntimeError('Unknown integrity checker failure; no automatic retry')
    result = verifier.verify(folder / 'candidate.rs')
    write_json(folder / 'verification.json', result)
    if result['error_type'] == 'verifier_error':
        raise RuntimeError('Verifier infrastructure failure')
    if known_lexerror:
        if result['success']:
            raise RuntimeError('Verus success with Lynette LexError; inspect manually')
        write_json(folder / 'integrity-before-recovery.json', check)
        check = {**check, 'valid': False, 'status': 'unparseable',
                 'recovery': 'known input LexError; Verus also rejected source'}
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
                      inference.tokenizer, cfg, json.dumps(history))
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
                        checked, integrity, inference.tokenizer, cfg, json.dumps(history))
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
            'repaired': sum(t['success'] for t in done), 'attempts': sum(len(t['attempts']) for t in done)}
    report = {'shared_first_successes': first_successes, 'initially_verified': initial,
        'shared_first_completed': sum(r['first'] is not None for r in rows), 'paired': rows,
        'summaries': summaries, 'complete': all(r['first'] is not None for r in rows) and
             all(s['completed'] == len(failures) for s in summaries.values()),
        'fork_checks_passed': all(r['fork_valid'] is True for r in failures)}
    write_json(root / 'comparison.json', report)
    lines = ['# Sonnet Low: shared first proposal, then paired repair', '',
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
