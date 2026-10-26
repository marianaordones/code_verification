import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys

from baseline.__main__ import run_lock
from baseline.integrity import tokens
from baseline.prompts import ROOT
from baseline.provenance import command, file_hashes, tool_identity, tool_signature
from baseline.storage import digest, read_json, write_json, write_text
from diagnostics.z3_internals import api_identity
from solver_needs_study.actions import EMPTY, RESPONSE_POLICY, parse_response, render
from solver_needs_study import feedback
from solver_needs_study.data import selected_cases, split_task
from solver_needs_study.download import source, VERUS_VERSION
from solver_needs_study.verify import StudyVerifier
from solver_needs_study.claude_code import ClaudeCode, preflight

CONFIG = ROOT / 'configs/missing-opus48-shared20.json'
PROMPT = ROOT / 'prompts/missing-opus48/system.txt'
SELECTION = ROOT / 'configs/missing-opus48-pilot20.json'
USER100 = ROOT / 'configs/missing-opus48-user100.json'
DEFAULT = ROOT / 'results/missing-opus48-low-shared20-50x3-v1'
ARMS = feedback.ARMS


def configuration():
    cfg = read_json(CONFIG)
    expected = {'model': 'claude-opus-4-8', 'effort': 'low', 'max_attempts': 3,
                'max_queries': 1, 'max_quantifiers': 50, 'max_instances_each': 3,
                'internals_token_budget': 12288, 'max_model_len': 49152, 'max_tokens': 4096,
                'seed': None, 'temperature': None}
    if any(cfg.get(k) != v for k, v in expected.items()):
        raise ValueError('Unexpected frozen Opus 4.8 / Low / 1 query / 50x3 pilot settings')
    selected, supplied = read_json(SELECTION), read_json(USER100)
    if len(supplied['ids']) != 100 or len(set(supplied['ids'])) != 100 or selected['ids'] != supplied['ids'][:20]:
        raise ValueError('Expected first 20 of the exact fixed 100 IDs')
    if selected['source_sha256'] != digest(USER100.read_bytes()):
        raise ValueError('User list changed')
    cfg['system_prompt_text'] = PROMPT.read_text(encoding='utf-8')
    return cfg


def implementation():
    return file_hashes([*Path(__file__).parent.glob('*.py'), CONFIG, PROMPT, SELECTION, USER100,
        *ROOT.glob('baseline/*.py'), *ROOT.glob('diagnostics/*.py'),
        ROOT / 'solver_needs_study/actions.py', ROOT / 'solver_needs_study/data.py',
        ROOT / 'solver_needs_study/download.py', ROOT / 'solver_needs_study/verify.py',
        ROOT / 'solver_needs_study/feedback.py', ROOT / 'solver_needs_study/claude_code.py',
        ROOT / 'repair_study/worker.py', ROOT / 'repair_study/relevance.py'])


def tokenizer():
    from transformers import AutoTokenizer
    from baseline.inference import MODEL_CODER, REVISION_CODER
    if importlib.metadata.version('transformers') != '4.51.3':
        raise ValueError('Use the pinned CPU tokenizer dependencies')
    value = AutoTokenizer.from_pretrained(MODEL_CODER, revision=REVISION_CODER)
    value.model_max_length = 10**12
    return value


def tools():
    value = {k: tool_identity(os.environ[e]) for k, e in
             [('verus', 'VERUS_BIN'), ('z3', 'Z3_BIN')]}
    for k in value:
        value[k]['version'] = command([value[k]['path'], '--version'])
    if VERUS_VERSION not in str(value['verus']['version']) or '4.12.5' not in str(value['z3']['version']):
        raise ValueError('Use the solver-needs Verus/Z3 bundle, not the older VerusBench bundle')
    value['solver_api'] = api_identity()
    return value


def signature(value):
    return {k: tool_signature(v) for k, v in value.items()}


def verifier(value, cfg):
    return StudyVerifier(value['verus']['path'], value['z3']['path'], cfg['verification_timeout'])


def validate(root):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation() or manifest['config'] != configuration():
        raise ValueError('Frozen code/config changed; use a new study')
    for name, sha in manifest['files'].items():
        if digest((root / name).read_bytes()) != sha:
            raise ValueError('Frozen input changed: ' + name)
    return manifest


def prepare(root):
    if (root / 'manifest.json').exists():
        validate(root)
        return
    source()
    cfg, identities = configuration(), tools()
    cases = selected_cases(20, SELECTION)
    plan = {'config': cfg, 'cases': [{k: c[k] for k in ('id', 'paper_label', 'source_path')} for c in cases],
            'implementation': implementation(), 'tools': signature(identities)}
    if (root / 'preparation.json').exists() and read_json(root / 'preparation.json') != plan:
        raise ValueError('Preparation changed; use a new directory')
    write_json(root / 'preparation.json', plan)
    checked_by = verifier(identities, cfg)
    for case in cases:
        folder = root / 'inputs' / case['id']
        if (folder / 'ready.json').exists():
            continue
        task = split_task(case)
        write_json(root / 'private' / (case['id'] + '.json'), case)
        write_json(folder / 'task.json', {k: v for k, v in task.items() if k != 'reference'})
        write_text(folder / 'candidate.rs', render(task, EMPTY))
        result = checked_by.verify(folder / 'candidate.rs')
        write_json(folder / 'verification.json', result)
        if result['error_type'] == 'verifier_error':
            raise RuntimeError('Initial verifier infrastructure failure: ' + case['id'])
        write_json(folder / 'ready.json', {'initially_verified': result['success'],
                   'published_validation_used': True, 'original_placebo_restoration_not_rerun': True})
        print('Prepared', case['id'], 'initially_verified=', result['success'], flush=True)
    files = {str(p.relative_to(root)): digest(p.read_bytes()) for p in (root / 'inputs').rglob('*') if p.is_file()}
    write_json(root / 'manifest.json', {**plan, 'files': files})


def messages(code, checked, action, context, payload, history, cfg):
    return feedback.messages(code, checked, action, context, payload, history, config=cfg)


def build_feedback(folder, code, checked, action, history, token, cfg):
    value = feedback.internals(folder, code, checked, action, history, token, cfg)
    value['policy'] = 'first up to ONE SAT/UNKNOWN query; concordant diagnostic replay; 50 groups x 3 instances; Qwen-token budget'
    write_json(folder / 'feedback.json', value)
    return value


def exposure(payload, token):
    queries = (payload or {}).get('queries', [])
    groups = [g for q in queries for g in q['quantifiers']]
    sizes = [len(g['instances']) for g in groups]
    return {'queries': len(queries), 'groups': len(groups), 'instances': sum(sizes),
            'max_instances_in_group': max(sizes, default=0),
            'internals_qwen_tokens': len(token.encode(json.dumps(payload, ensure_ascii=False, indent=2),
                add_special_tokens=False)) if payload else 0}


def attempt(folder, index, task, code, checked, action, context, payload, history,
            cfg, inference, check, shared_sha=None):
    if (folder / 'result.json').exists():
        return read_json(folder / 'result.json')
    if not feedback.fits(code, checked, action, context, payload, history, inference.tokenizer, cfg):
        raise ValueError('Prompt too large; source/diagnostics are never truncated')
    prompt = messages(code, checked, action, context, payload, history, cfg)
    common = messages(code, checked, action, context, None, history, cfg)
    request = {'messages': prompt, 'candidate_sha256': digest(code.encode()),
               'common_messages_sha256': digest(json.dumps(common, sort_keys=True).encode()),
               'shared_start_sha256': shared_sha, 'config': cfg, 'seed': None,
               'internals_exposed': bool(payload and payload['queries'])}
    if (folder / 'request.json').exists() and read_json(folder / 'request.json') != request:
        raise ValueError('Pending request changed')
    write_json(folder / 'request.json', request)
    write_json(folder / 'exposure.json', exposure(payload, inference.tokenizer))
    if (folder / 'response.json').exists():
        response = read_json(folder / 'response.json')
    else:
        response = inference.generate_at(prompt, cfg, folder)
        write_json(folder / 'response.json', response)
    proposed, new_code, error = action, code, None
    info = {'policy': RESPONSE_POLICY}
    try:
        proposed = parse_response(response['text'], metadata=info)
        new_code = render(task, proposed)
        if tokens(new_code) == tokens(code) and proposed['nla'] == action['nla']:
            raise ValueError('No effective proof/solver-setting change')
    except (ValueError, KeyError, TypeError) as exception:
        proposed, new_code, error = action, code, str(exception)
    write_json(folder / 'response-format.json', info)
    write_json(folder / 'action.json', proposed)
    write_text(folder / 'candidate.rs', new_code)
    result = check.verify(folder / 'candidate.rs', nla=proposed['nla'])
    write_json(folder / 'verification.json', result)
    if result['error_type'] == 'verifier_error':
        raise RuntimeError('Verifier infrastructure failure; response preserved')
    record = {'attempt': index, 'success': result['success'] and error is None,
              'edit_error': error, 'error_type': result['error_type'], 'action': proposed,
              'internals_exposed': request['internals_exposed']}
    write_json(folder / 'result.json', record)
    return record


def state(folder):
    return ((folder / 'candidate.rs').read_text(encoding='utf-8'),
            read_json(folder / 'verification.json'), read_json(folder / 'action.json'))


def run_case(root, case, cfg, inference, check, order):
    initial = root / 'inputs' / case['id']
    task = read_json(initial / 'task.json')
    code = (initial / 'candidate.rs').read_text(encoding='utf-8')
    checked = read_json(initial / 'verification.json')
    shared = root / 'shared' / case['id'] / 'attempt_01'
    if checked['success']:
        write_json(shared.parent / 'task.json', {'initially_verified': True, 'success': False})
        return
    context = feedback.control_feedback(code, checked)['context']
    first = attempt(shared, 1, task, code, checked, dict(EMPTY), context, None, [], cfg, inference, check)
    write_json(shared.parent / 'task.json', {'initially_verified': False, 'success': first['success']})
    if first['success']:
        print('shared', case['id'], 'success on first proposal', flush=True)
        return
    code, checked, action = state(shared)
    initial_history = [first]
    pack = build_feedback(shared, code, checked, action, initial_history, inference.tokenizer, cfg)
    files = {name: digest((shared / name).read_bytes()) for name in
             ('request.json', 'response.json', 'candidate.rs', 'verification.json', 'action.json', 'result.json', 'feedback.json')}
    checkpoint = shared / 'shared-state.json'
    if checkpoint.exists() and read_json(checkpoint) != files:
        raise ValueError('Shared candidate/diagnostics/settings changed')
    write_json(checkpoint, files)
    shared_sha = digest(checkpoint.read_bytes())
    for arm in order:
        output = root / arm / case['id']
        if (output / 'task.json').exists():
            continue
        code, checked, action = state(shared)
        history, records = list(initial_history), []
        current_pack = pack if arm == ARMS[0] else feedback.control_feedback(code, checked)
        for index in (2, 3):
            folder = output / f'attempt_{index:02}'
            payload = current_pack.get('internals') if arm == ARMS[0] else None
            record = attempt(folder, index, task, code, checked, action, current_pack['context'],
                             payload, history, cfg, inference, check, shared_sha)
            records.append(record)
            if record['success']:
                break
            code, checked, action = state(folder)
            history.append(record)
            if index == 2:
                current_pack = build_feedback(folder, code, checked, action, history, inference.tokenizer, cfg) if arm == ARMS[0] else feedback.control_feedback(code, checked)
        write_json(output / 'task.json', {'success': any(r['success'] for r in records),
                    'attempts': records, 'shared_start_sha256': shared_sha})
        print(arm, case['id'], 'repaired=', any(r['success'] for r in records), flush=True)


def compare(root):
    manifest = validate(root)
    rows = []
    for case in manifest['cases']:
        common = root / 'shared' / case['id']
        first = read_json(common / 'task.json') if (common / 'task.json').exists() else None
        row = {'id': case['id'], 'first': first}
        requests = []
        for arm in ARMS:
            path = root / arm / case['id'] / 'task.json'
            row[arm] = read_json(path) if path.exists() else None
            path = path.parent / 'attempt_02/request.json'
            requests.append(read_json(path) if path.exists() else None)
        row['fork_valid'] = None
        if all(requests):
            a, b = requests
            row['fork_valid'] = (all(a[k] == b[k] for k in ('candidate_sha256', 'common_messages_sha256',
                 'shared_start_sha256', 'config')) and not b['internals_exposed'])
        rows.append(row)
    failed = [r for r in rows if r['first'] and not r['first']['initially_verified'] and not r['first']['success']]
    summaries = {}
    for arm in ARMS:
        done = [r[arm] for r in failed if r[arm] is not None]
        summaries[arm] = {'completed': len(done), 'repair_denominator_so_far': len(failed),
            'repaired_at_2': sum(any(a['success'] and a['attempt'] == 2 for a in t['attempts']) for t in done),
            'repaired_at_3': sum(any(a['success'] and a['attempt'] == 3 for a in t['attempts']) for t in done),
            'repaired': sum(t['success'] for t in done), 'attempts': sum(len(t['attempts']) for t in done),
            'exposed_attempts': sum(a['internals_exposed'] for t in done for a in t['attempts'])}
    report = {'selected': len(rows), 'initially_verified': sum(bool(r['first'] and r['first']['initially_verified']) for r in rows),
        'shared_first_successes': sum(bool(r['first'] and r['first']['success']) for r in rows),
        'shared_first_completed': sum(r['first'] is not None for r in rows), 'paired': rows, 'summaries': summaries,
        'complete': all(r['first'] is not None for r in rows) and all(s['completed'] == len(failed) for s in summaries.values()),
        'fork_checks_passed': all(r['fork_valid'] is True for r in failed)}
    write_json(root / 'comparison.json', report)
    lines = ['# Missing assertions: Opus 4.8 Low, shared first proposal, 50x3 caps', '',
        f"Selected: {len(rows)}; shared first completed: {report['shared_first_completed']}; initially verified: {report['initially_verified']}; shared first successes: {report['shared_first_successes']}.",
        f'Common failed candidates available for repair: {len(failed)}.', '',
        '| Arm | Completed repairs | Success at 2 | Success at 3 | Total repaired | Exposed attempts |',
        '|---|---|---|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{len(failed)} | {s['repaired_at_2']} | {s['repaired_at_3']} | {s['repaired']} | {s['exposed_attempts']} |")
    lines += ['', f"Complete: {report['complete']}; fork checks passed: {report['fork_checks_passed']}",
              'Initial shared successes are not credited as repairs. Actual packet sizes are in exposure.json.']
    write_text(root / 'comparison.md', '\n'.join(lines))
    return report


def run(root):
    manifest, runtime = validate(root), tools()
    if signature(runtime) != manifest['tools']:
        raise ValueError('Toolchain changed')
    provenance = {'cli': preflight(), 'python': sys.version, 'versions': {p: importlib.metadata.version(p)
                  for p in ('transformers', 'tokenizers', 'huggingface-hub', 'z3-solver')}}
    if (root / 'runtime.json').exists() and read_json(root / 'runtime.json') != provenance:
        raise ValueError('Runtime/CLI changed')
    write_json(root / 'runtime.json', provenance)
    inference = ClaudeCode(tokenizer())
    check = verifier(runtime, manifest['config'])
    try:
        for index, case in enumerate(manifest['cases']):
            run_case(root, case, manifest['config'], inference, check, ARMS if index % 2 == 0 else ARMS[::-1])
    finally:
        compare(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'compare'))
    parser.add_argument('--study', type=Path, default=DEFAULT)
    args = parser.parse_args()
    with run_lock(args.study.resolve()):
        {'prepare': prepare, 'run': run, 'compare': compare}[args.command](args.study.resolve())


if __name__ == '__main__':
    main()
