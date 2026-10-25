"""Fixed original VerusBench inputs, paired Claude proof completion, no Qwen candidates."""
import argparse
from collections import Counter
import importlib.metadata
import json
import os
from pathlib import Path
import random
import re
import shutil
import sys

from baseline.__main__ import run_lock
from baseline.benchmark import load_tasks
from baseline.integrity import IntegrityValidator, lexical_check, tokens
from baseline.obligation import ObligationVerifier
from baseline.prompts import ROOT
from baseline.provenance import command, file_hashes, tool_identity, tool_signature
from baseline.storage import digest, read_json, write_json, write_text
from diagnostics.z3_internals import api_identity
from repair_study.feedback import build_payload
from repair_study.relevance import source_context
from solver_needs_study.claude_code import ClaudeCode, preflight
from solver_needs_study.__main__ import load_tokenizer

ARMS = ('with_internals', 'without_internals')
CONFIG = ROOT / 'configs/verusbench-claude5.json'
SELECTION = ROOT / 'configs/verusbench-claude5-selection.json'


def config(path=CONFIG):
    value = read_json(path)
    if value['model'] not in ('claude-opus-5-5', 'claude-sonnet-5-5') or (value['effort'], value['max_attempts']) != ('low', 3) or value['count'] not in (5, 20):
        raise ValueError('Expected Opus/Sonnet 5.5, Low, three proposals and 5 or 20 programs')
    return value


def selection_path(config_path=CONFIG):
    return ROOT / config(config_path).get('selection_file', str(SELECTION.relative_to(ROOT)))


def select(tasks, seed, count=5, excluded_ids=(), screen_originals=False):
    """Round-robin categories, shuffle ID-sorted pools, never inspect outcomes."""
    rng = random.Random(seed)
    if screen_originals:
        tasks = [t for t in tasks if lexical_check(Path(t['file']).read_text(encoding='utf-8'),
                    Path(t['file']).read_text(encoding='utf-8'))[0]]
    pools = {}
    for category in sorted({t['category'] for t in tasks}):
        pools[category] = sorted([t for t in tasks if t['category'] == category and t['id'] not in excluded_ids], key=lambda t: t['id'])
        rng.shuffle(pools[category])
    chosen = []
    seen = {digest(Path(t['file']).read_bytes()) for t in tasks if t['id'] in excluded_ids}
    while len(chosen) < count:
        progress = False
        for pool in pools.values():
            while pool:
                row = pool.pop()
                sha = digest(Path(row['file']).read_bytes())
                if sha not in seen:
                    chosen.append(row)
                    seen.add(sha)
                    progress = True
                    break
            if len(chosen) == count:
                break
        if not progress:
            raise ValueError('Not enough distinct original programs')
    return chosen


def implementation(config_path=CONFIG):
    return file_hashes([*Path(__file__).parent.glob('*.py'), config_path, selection_path(config_path),
        ROOT / 'prompts/v4/system.txt', ROOT / 'prompts/verusbench-claude/solver-info.txt', *ROOT.glob('prompts/repair-study/*.txt'),
        *ROOT.glob('baseline/*.py'), *ROOT.glob('diagnostics/*.py'),
        *ROOT.glob('repair_study/*.py'), ROOT / 'solver_needs_study/claude_code.py',
        ROOT / 'solver_needs_study/__main__.py'])


def tools():
    values = {k: tool_identity(os.environ[e]) for k, e in
              [('verus', 'VB_VERUS_BIN'), ('z3', 'VB_Z3_BIN'), ('lynette', 'VB_LYNETTE_BIN')]}
    for key in ('verus', 'z3'):
        values[key]['version'] = command([values[key]['path'], '--version'])
    if '33269ac' not in str(values['verus']['version']) or '4.12.5' not in str(values['z3']['version']):
        raise ValueError('Use the benchmark-compatible Verus 33269ac and Z3 4.12.5, not the solver-needs toolchain')
    values['solver_api'] = api_identity()
    return values


def identity(values):
    return {k: tool_signature(v) for k, v in values.items()}


def verify_tools(values, cfg):
    return (ObligationVerifier(values['verus']['path'], values['z3']['path'], cfg['verification_timeout']),
            IntegrityValidator(values['lynette']['path']))


def messages(original, current, checked, integrity, payload, history):
    system = (ROOT / 'prompts/v4/system.txt').read_text(encoding='utf-8')
    system += '\n' + (ROOT / 'prompts/verusbench-claude/solver-info.txt').read_text(encoding='utf-8')
    user = ('Complete the proof annotations of this original unverified VerusBench program.\n'
            '<original_program>\n' + original + '\n</original_program>\n'
            '<current_candidate>\n' + current + '\n</current_candidate>\n'
            '<verus_diagnostics>\n' + checked['stdout'] + '\n' + checked['stderr'] + '\n</verus_diagnostics>\n'
            '<integrity_diagnostics>\n' + json.dumps(integrity) + '\n</integrity_diagnostics>\n'
            '<source_failure_context>\n' + json.dumps(source_context(current, checked)) + '\n</source_failure_context>\n'
            '<attempt_history>\n' + json.dumps(history) + '\n</attempt_history>\n')
    if payload is not None:
        user += '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>\n'
    user += 'Return the complete annotated Verus source. Preserve the original implementation and contracts.'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def extract_source(text):
    text = text.strip().replace('\r\n', '\n')
    fences = list(re.finditer(r'^[ \t]*(?:`{3,}|~{3,})[^\n]*$', text, re.MULTILINE))
    if not fences:
        return text, 'direct_source'
    if len(fences) != 2 or fences[0].group().strip() not in ('```rust', '```verus', '```rs', '```') or fences[1].group().strip() != '```':
        raise ValueError('Expected direct source or exactly one Rust/Verus code fence')
    return text[fences[0].end():fences[1].start()].strip(), 'single_source_fence'


def validate(root):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation(ROOT / manifest.get('config_file', str(CONFIG.relative_to(ROOT)))):
        raise ValueError('Code changed; use a new study directory')
    for name, sha in manifest['files'].items():
        if digest((root / name).read_bytes()) != sha:
            raise ValueError('Frozen input changed: ' + name)
    return manifest


def prepare(root, config_path=CONFIG, source_study=None):
    if (root / 'manifest.json').exists():
        manifest = validate(root)
        if manifest['config'] != config(config_path):
            raise ValueError('Prepared study has a different model/configuration')
        return
    cfg, runtime = config(config_path), tools()
    if source_study is not None:
        return import_inputs(root, source_study, cfg, runtime, config_path)
    frozen_selection = read_json(selection_path(config_path))
    tasks = select(load_tasks(ROOT / 'data/manifest.json'), cfg['selection_seed'], cfg['count'], frozen_selection.get('excluded_ids', []), cfg.get('screen_originals', False))
    selection = [{k: t[k] for k in ('id', 'category', 'path', 'sha256')} for t in tasks]
    if frozen_selection['tasks'] != selection:
        raise ValueError('Selection differs from the fixed program inventory')
    plan = {'config': cfg, 'config_file': str(config_path.relative_to(ROOT)), 'selection': selection, 'implementation': implementation(config_path), 'tools': identity(runtime)}
    if (root / 'preparation.json').exists() and read_json(root / 'preparation.json') != plan:
        raise ValueError('Preparation changed; use a new directory')
    write_json(root / 'preparation.json', plan)
    # Same pinned Qwen tokenizer for feedback selection, never its weights.
    tokenizer = load_tokenizer({'provider': 'claude_code'})
    verifier, guard = verify_tools(runtime, cfg)
    for task in tasks:
        folder = root / 'inputs' / task['id']
        if (folder / 'ready.json').exists():
            continue
        original = Path(task['file']).read_text(encoding='utf-8')
        write_text(folder / 'original.rs', original)
        checked = verifier.verify(folder / 'original.rs')
        write_json(folder / 'verification.json', checked)
        integrity = guard.validate(folder / 'original.rs', folder / 'original.rs')
        write_json(folder / 'integrity.json', integrity)
        if checked['error_type'] == 'verifier_error' or not integrity['valid']:
            raise RuntimeError('Initial verifier/integrity error for ' + task['id'])
        # Reuse the existing ranked, outcome-concordant replay builder. Its fit
        # policy covers both old contracts conservatively; actual prompts checked too.
        payload = build_payload(folder, original, original, checked, integrity, tokenizer, cfg)
        write_json(folder / 'ready.json', {'initially_verified': checked['success']})
        print('Prepared', task['id'], 'initially_verified=', checked['success'], flush=True)
    files = {str(p.relative_to(root)): digest(p.read_bytes()) for p in (root / 'inputs').rglob('*') if p.is_file()}
    write_json(root / 'manifest.json', {**plan, 'files': files})


def import_inputs(root, source, cfg, runtime, config_path):
    source = source.resolve()
    if root == source or root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError('Use separate source and destination studies')
    old = read_json(source / 'manifest.json')
    for name in ('prompts/v4/system.txt', 'prompts/verusbench-claude/solver-info.txt'):
        if old['implementation'].get(name) != digest((ROOT / name).read_bytes()):
            raise ValueError('Prompt differs from the source Opus study: ' + name)
    if old['selection'] != read_json(selection_path(config_path))['tasks'] or old['tools'] != identity(runtime):
        raise ValueError('Source selection/toolchain differs')
    if {k: v for k, v in old['config'].items() if k != 'model'} != {k: v for k, v in cfg.items() if k != 'model'}:
        raise ValueError('Only model may differ when reusing frozen inputs')
    for name, sha in old['files'].items():
        if digest((source / name).read_bytes()) != sha:
            raise ValueError('Frozen source input changed: ' + name)
    if (root / 'inputs').exists():
        raise ValueError('Destination inputs already exist; inspect incomplete preparation')
    shutil.copytree(source / 'inputs', root / 'inputs')
    manifest = {'config': cfg, 'config_file': str(config_path.relative_to(ROOT)),
                'selection': old['selection'], 'tools': identity(runtime),
                'implementation': implementation(config_path), 'files': old['files'],
                'input_source_study': str(source), 'input_source_manifest_sha256': digest((source / 'manifest.json').read_bytes())}
    write_json(root / 'manifest.json', manifest)
    print('Reused frozen inputs, diagnostics and internals from', source, flush=True)


def run_case(root, arm, task, cfg, inference, verifier, guard):
    frozen = root / 'inputs' / task['id']
    original = (frozen / 'original.rs').read_text(encoding='utf-8')
    current = original
    checked, integrity = read_json(frozen / 'verification.json'), read_json(frozen / 'integrity.json')
    payload = read_json(frozen / 'payload.json')
    history, records = [], []
    if not checked['success']:
        for index in range(1, 4):
            folder = root / arm / task['id'] / f'attempt_{index:02}'
            if (folder / 'result.json').exists():
                record = read_json(folder / 'result.json')
            else:
                exposed = payload if arm == ARMS[0] else None
                prompt = messages(original, current, checked, integrity, exposed, history)
                if len(inference.tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True)) + cfg['max_tokens'] > cfg['max_model_len']:
                    raise ValueError('Prompt does not fit; no source truncation permitted')
                common = messages(original, current, checked, integrity, None, history)
                request = {'messages': prompt, 'candidate_sha256': digest(current.encode()),
                           'common_messages_sha256': digest(json.dumps(common, sort_keys=True).encode()),
                           'config': cfg, 'seed': None, 'internals_exposed': bool(exposed and exposed['availability'] == 'available')}
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
                    proposed, form = extract_source(response['text'])
                    if not proposed or tokens(proposed) == tokens(current):
                        raise ValueError('Empty/unchanged proposal')
                except ValueError as exception:
                    proposed, error = current, str(exception)
                write_text(folder / 'candidate.rs', proposed)
                check = guard.validate(frozen / 'original.rs', folder / 'candidate.rs')
                write_json(folder / 'integrity.json', check)
                if check.get('status') == 'checker_error':
                    raise RuntimeError('Integrity checker infrastructure failure')
                result = verifier.verify(folder / 'candidate.rs')
                write_json(folder / 'verification.json', result)
                if result['error_type'] == 'verifier_error':
                    raise RuntimeError('Verifier infrastructure failure')
                record = {'attempt': index, 'success': bool(result['success'] and check['valid'] and error is None),
                          'edit_error': error, 'integrity_valid': check['valid'], 'error_type': result['error_type'],
                          'extraction': form, 'internals_exposed': request['internals_exposed']}
                write_json(folder / 'result.json', record)
            records.append(record)
            if record['success']:
                break
            current = (folder / 'candidate.rs').read_text(encoding='utf-8')
            checked, integrity = read_json(folder / 'verification.json'), read_json(folder / 'integrity.json')
            history.append(record)
            if index < 3 and arm == ARMS[0]:
                if (folder / 'payload.json').exists():
                    payload = read_json(folder / 'payload.json')
                else:
                    payload = build_payload(folder, original, current, checked, integrity, inference.tokenizer, cfg, json.dumps(history))
    summary = {'id': task['id'], 'initially_verified': read_json(frozen / 'verification.json')['success'],
               'success': any(r['success'] for r in records), 'attempts': records}
    write_json(root / arm / task['id'] / 'task.json', summary)
    print(arm, task['id'], 'success=', summary['success'], flush=True)


def compare(root):
    manifest = validate(root)
    summaries, paired = {}, []
    for task in manifest['selection']:
        row = {'id': task['id'], 'category': task['category']}
        requests = []
        for arm in ARMS:
            folder = root / arm / task['id']
            row[arm] = read_json(folder / 'task.json') if (folder / 'task.json').exists() else None
            path = folder / 'attempt_01/request.json'
            requests.append(read_json(path) if path.exists() else None)
        row['first_pair_valid'] = (requests[0]['common_messages_sha256'] == requests[1]['common_messages_sha256'] and
                                  requests[0]['candidate_sha256'] == requests[1]['candidate_sha256'] and
                                  requests[0]['config'] == requests[1]['config'] and not requests[1]['internals_exposed']) if all(requests) else None
        paired.append(row)
    for arm in ARMS:
        done = [r[arm] for r in paired if r[arm] is not None]
        summaries[arm] = {'completed': len(done), 'solved': sum(t['success'] for t in done),
                          'initially_verified': sum(t['initially_verified'] for t in done),
                          'attempts': sum(len(t['attempts']) for t in done),
                          'solved_by_attempt': {str(k): sum(any(a['success'] and a['attempt'] <= k for a in t['attempts']) for t in done) for k in (1, 2, 3)}}
    expected = len(manifest['selection'])
    report = {'summaries': summaries, 'paired': paired, 'expected': expected,
              'complete': all(s['completed'] == expected for s in summaries.values()),
              'scope': manifest['config']['scope']}
    report['first_pairs_valid'] = all(r['first_pair_valid'] is True for r in paired
        if not read_json(root / 'inputs' / r['id'] / 'verification.json')['success'])
    report['with_only'] = [r['id'] for r in paired if r[ARMS[0]] and r[ARMS[1]] and r[ARMS[0]]['success'] and not r[ARMS[1]]['success']]
    report['without_only'] = [r['id'] for r in paired if r[ARMS[0]] and r[ARMS[1]] and r[ARMS[1]]['success'] and not r[ARMS[0]]['success']]
    write_json(root / 'comparison.json', report)
    lines = [f"# VerusBench: {manifest['config']['model']} / Low / three total proposals per arm", '',
             '| Arm | Completed | Solved | Attempts | Initially verified |', '|---|---|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{expected} | {s['solved']} | {s['attempts']} | {s['initially_verified']} |")
    lines += ['', 'Original unverified programs, not frozen Qwen failures. Whole-file generation; acceptance requires Verus and Lynette.',
              f"Complete: {report['complete']}; initial pairs valid: {report['first_pairs_valid']}",
              'See comparison.json for per-task outcomes and initial pair checks.']
    write_text(root / 'comparison.md', '\n'.join(lines))
    return report


def run(root):
    manifest, runtime = validate(root), tools()
    if identity(runtime) != manifest['tools']:
        raise ValueError('Toolchain changed')
    cfg = manifest['config']
    provenance = {'cli': preflight(), 'python': sys.version,
                  'versions': {p: importlib.metadata.version(p) for p in ('transformers', 'tokenizers', 'z3-solver')}}
    if (root / 'runtime.json').exists() and read_json(root / 'runtime.json') != provenance:
        raise ValueError('CLI/runtime changed; use a new study directory')
    write_json(root / 'runtime.json', provenance)
    inference = ClaudeCode(load_tokenizer({'provider': 'claude_code'}))
    verifier, guard = verify_tools(runtime, cfg)
    try:
        for index, task in enumerate(manifest['selection']):
            for arm in (ARMS if index % 2 == 0 else ARMS[::-1]):
                if not (root / arm / task['id'] / 'task.json').exists():
                    run_case(root, arm, task, cfg, inference, verifier, guard)
    finally:
        compare(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'compare'))
    parser.add_argument('--study', type=Path, default=ROOT / 'results/verusbench-claude5-low-v2')
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--from-study', type=Path, help='Reuse frozen original inputs/diagnostics, never model responses')
    args = parser.parse_args()
    root = args.study.resolve()
    with run_lock(root):
        if args.command == 'prepare':
            prepare(root, args.config.resolve(), args.from_study)
        else:
            {'run': run, 'compare': compare}[args.command](root)


if __name__ == '__main__':
    main()
