import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil

from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json, write_text
from baseline.integrity import tokens
from safe_internals.validation import preservation
from safe_internals.pipeline import collect_events
from solver_needs_study.feedback import internals
from solver_needs_study.actions import EMPTY, parse_response, render
from solver_needs_study.data import cases, split_task
from solver_needs_study.download import source as download_source
from repair_study.regions_v2 import regions, apply_patch
from sft_eval.inference import Engine, adapter_identity
from sft_eval.__main__ import CONFIG, tool_hashes, verifier

ARMS = ('without_internals', 'with_internals')


def implementation():
    paths = [*Path(__file__).parent.glob('*.py'), *list((ROOT / 'sft_eval').glob('*.py')),
             ROOT / 'solver_needs_study/actions.py', ROOT / 'solver_needs_study/feedback.py',
             ROOT / 'repair_study/regions.py', ROOT / 'repair_study/regions_v2.py',
             ROOT / 'prompts/solver-needs/system.txt', ROOT / 'prompts/safe-internals.txt',
             ROOT / 'safe_internals/validation.py', ROOT / 'safe_internals/pipeline.py']
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}


def instruction(benchmark):
    # Keep internal interpretation guidance, without the full-file output instruction.
    guide = (ROOT / 'prompts/safe-internals.txt').read_text(encoding='utf-8').split('\n\n', 1)[1]
    if benchmark == 'solver-needs':
        base = (ROOT / 'prompts/solver-needs/system.txt').read_text(encoding='utf-8')
        base = base.replace('FOUR total proposals', 'THREE total proposals')
    else:
        base = ('Repair only one offered body proof region. Return exactly a JSON object with '
                'site_id and replacement, optionally inside a json fence. Example grammar: '
                '{"site_id":"R1","replacement":"proof { assert(EXPRESSION); }"}. '
                'Use a real offered site ID and a checked expression in scope, not this placeholder. '
                'For loop_invariants, replacement must be the complete invariant list beginning with invariant. '
                'For proof_block or insert_proof, replacement must be exactly one proof { ... } block. '
                'Existing annotations may be replaced; insertions precede safe statements or final expressions. '
                'Contracts and executable statements cannot change. No assume/admit/trusted bypasses. '
                'Only two localized repair proposals follow the saved shared first proposal, three TOTAL. '
                'Invalid JSON, empty or unchanged edits consume a proposal. An offered region is not a '
                'guarantee that every multi-region repair is expressible. Return the edit, not the whole file.')
    return base + '\n\n' + guide + '\nAn absent solver block may be withheld by design, not evidence that no events exist.'


def sites_for(code):
    try:
        sites = regions(code)
        return sites, {'status': 'available' if sites else 'no_safe_sites', 'count': len(sites)}
    except ValueError as error:
        return [], {'status': 'parser_error', 'count': 0, 'error': str(error)}


def prompt(benchmark, code, verification, action, rejection, payload=None):
    user = '<current_program>\n' + code + '\n</current_program>\n'
    user += '<verus_diagnostics>\n' + verification['stdout'] + '\n' + verification['stderr'] + '\n</verus_diagnostics>\n'
    if benchmark == 'solver-needs':
        from solver_needs_study.data import upstream
        _, laws = upstream()
        user += '<current_action>\n' + json.dumps(action) + '\n</current_action>\n'
        user += '<checked_law_catalogue>\n' + '\n'.join('LAW ' + k + '\n' + v for k, v in laws.LAWS.items()) + '\n</checked_law_catalogue>\n'
    else:
        sites, audit = sites_for(code)
        user += '<editable_sites>\n' + json.dumps(sites, ensure_ascii=False, indent=2) + '\n</editable_sites>\n'
        user += '<editor_scope>\n' + json.dumps(audit) + '\n</editor_scope>\n'
    if rejection:
        user += '<previous_edit_rejection>\n' + rejection + '\n</previous_edit_rejection>\n'
    if payload and payload.get('queries'):
        user += '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>\n'
    return [{'role': 'system', 'content': instruction(benchmark)}, {'role': 'user', 'content': user}]


def frozen_source(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('solver', 'internals'):
        if (source / name).exists():
            shutil.copytree(source / name, destination / name, dirs_exist_ok=True)
    for name in ('candidate.rs', 'verification.json', 'collection.json'):
        if (source / name).exists():
            shutil.copy2(source / name, destination / name)


def prepare(args):
    root, previous = args.output.resolve(), args.source.resolve()
    if root == previous or root in previous.parents or previous in root.parents:
        raise ValueError('Use separate source and destination studies')
    src = read_json(previous / 'manifest.json')
    identity = adapter_identity(src['adapter'])
    if identity != src['adapter_identity'] or tool_hashes() != src['tools']:
        raise ValueError('Use the same trained adapter and verifier binaries as the full-file evaluation')
    plan = {'benchmark': src['benchmark'], 'adapter': src['adapter'], 'adapter_identity': identity,
            'source': str(previous), 'source_manifest_sha256': digest((previous / 'manifest.json').read_bytes()),
            'config': CONFIG, 'implementation': implementation(), 'tools': tool_hashes(),
            'overlap_flagged_ids': src['overlap_flagged_ids'], 'tasks': []}
    if (root / 'manifest.json').exists():
        validate(root)
        return
    root.mkdir(parents=True, exist_ok=True)
    if plan['benchmark'] == 'solver-needs':
        download_source()
        rows = {r['id']: r for r in cases()}
    for item in src['tasks']:
        key = item['id']
        dest = root / 'inputs' / key
        if plan['benchmark'] == 'verusbench':
            shared = previous / 'shared' / key / 'proposal_01'
            result = read_json(shared / 'result.json')
            status = 'initial_success' if result['success'] else 'eligible' if result['accepted'] else 'initial_rejected'
            frozen_source(shared, dest)
            original = (previous / 'inputs' / key / 'candidate.rs').read_text(encoding='utf-8')
            write_text(dest / 'original.rs', original)
            write_json(dest / 'initial-result.json', result)
            sites, audit = sites_for((dest / 'candidate.rs').read_text(encoding='utf-8'))
            if status == 'eligible' and not sites:
                status = 'editor_unavailable'
            write_json(dest / 'editor-audit.json', audit)
            proposals = 2
        else:
            folder = previous / 'inputs' / key
            if digest((folder / 'candidate.rs').read_bytes()) != item['input_sha256']:
                raise ValueError('Frozen source changed: ' + key)
            task = split_task(rows[key])
            # Removed assertion/reference are deliberately not stored in the local task metadata.
            task = {k: task[k] for k in ('prefix', 'suffix', 'proof_context', 'line')}
            code = render(task, EMPTY)
            if tokens(code) != tokens((folder / 'candidate.rs').read_text(encoding='utf-8')):
                raise ValueError('Slot rendering changed stripped program: ' + key)
            frozen_source(folder, dest)
            write_text(dest / 'candidate.rs', code)
            write_text(dest / 'original.rs', code)
            write_json(dest / 'slot.json', task)
            status = 'initial_success' if read_json(dest / 'verification.json')['success'] else 'eligible'
            proposals = 3
        plan['tasks'].append({**item, 'status': status, 'localized_proposals': proposals})
        print('Prepared localized', key, status, flush=True)
    plan['files'] = {str(p.relative_to(root)): digest(p.read_bytes()) for p in (root / 'inputs').rglob('*') if p.is_file()}
    write_json(root / 'manifest.json', plan)


def validate(root):
    plan = read_json(root / 'manifest.json')
    if plan['implementation'] != implementation() or plan['tools'] != tool_hashes() or plan['adapter_identity'] != adapter_identity(plan['adapter']):
        raise ValueError('Code, tools or adapter changed; use a new output directory')
    for file, expected in plan['files'].items():
        if digest((root / file).read_bytes()) != expected:
            raise ValueError('Frozen local input changed: ' + file)
    return plan


def check(checker, benchmark, folder, code, action):
    write_text(folder / 'candidate.rs', code)
    if not (folder / 'verification.json').exists():
        value = checker.verify(folder / 'candidate.rs', nla=action['nla']) if benchmark == 'solver-needs' else checker.verify(folder / 'candidate.rs')
        if value['error_type'] == 'verifier_error':
            raise RuntimeError('Verifier infrastructure failure: ' + str(folder))
        write_json(folder / 'verification.json', value)
    return read_json(folder / 'verification.json')


def run(root):
    plan = validate(root)
    benchmark = plan['benchmark']
    engine, checker = Engine(plan['adapter']), verifier(benchmark)
    for i, task in enumerate(plan['tasks']):
        key = task['id']
        for arm in ARMS:
            output = root / arm / key
            if (output / 'task.json').exists():
                continue
            if task['status'] != 'eligible':
                write_json(output / 'task.json', {'id': key, 'status': task['status'], 'success': False, 'attempts': []})
                continue
            initial = root / 'inputs' / key
            current = (initial / 'candidate.rs').read_text(encoding='utf-8')
            original = (initial / 'original.rs').read_text(encoding='utf-8')
            verification = read_json(initial / 'verification.json')
            action, rejection, state_folder = dict(EMPTY), None, initial
            slot = read_json(initial / 'slot.json') if benchmark == 'solver-needs' else None
            attempts = []
            for n in range(1, task['localized_proposals'] + 1):
                folder = output / f'repair_{n:02d}'
                if (folder / 'result.json').exists():
                    result = read_json(folder / 'result.json')
                else:
                    payload = None
                    base = prompt(benchmark, current, verification, action, rejection)
                    base_tokens = len(engine.tokenizer.apply_chat_template(base, tokenize=True, add_generation_prompt=True))
                    if base_tokens + 4096 > 32768:
                        result = {'success': False, 'accepted': False, 'error': 'context_budget', 'edit_error': None}
                        write_json(folder / 'result.json', result)
                    else:
                        # Use a disposable packet folder per proposal: never modify frozen inputs,
                        # and ensure packet fitting includes this editor's current rejection/context.
                        if arm == 'with_internals':
                            packet = folder / 'packet'
                            frozen_source(state_folder, packet)
                            write_text(packet / 'candidate.rs', current)
                            collect_events(packet, verification, CONFIG)
                            def builder(code, v, a, context, p, history, **unused):
                                return prompt(benchmark, code, v, action, rejection, p)
                            try:
                                payload = internals(packet, current, verification, {}, [], engine.tokenizer, CONFIG,
                                    replay=False, message_builder=builder)['internals']
                            except ValueError as error:
                                if 'exceed context' not in str(error):
                                    raise
                                write_json(packet / 'omission.json', {'reason': str(error)})
                        request = prompt(benchmark, current, verification, action, rejection, payload)
                        count = len(engine.tokenizer.apply_chat_template(request, tokenize=True, add_generation_prompt=True))
                        if count + 4096 > 32768:
                            raise ValueError('Internal packet fitting failed; no truncation')
                        seed = 20261018 + i * 10 + n - 1 + (1 if benchmark == 'verusbench' else 0)
                        write_json(folder / 'request.json', {'messages': request, 'seed': seed, 'input_tokens': count,
                                                           'internals_exposed': bool(payload and payload.get('queries'))})
                        if not (folder / 'response.json').exists():
                            write_json(folder / 'response.json', engine.generate(request, seed))
                        response = read_json(folder / 'response.json')
                        proposed, changed, edit_error = dict(action), current, None
                        try:
                            if benchmark == 'solver-needs':
                                proposed = parse_response(response['text'])
                                changed = render(slot, proposed)
                                if tokens(changed) == tokens(current) and proposed['nla'] == action['nla']:
                                    raise ValueError('No effective proof/solver-setting change')
                            else:
                                offered, _ = sites_for(current)
                                changed, _ = apply_patch(current, response['text'], offered)
                        except (ValueError, KeyError, TypeError) as error:
                            edit_error = str(error)
                        gate = {'status': 'edit_error'}
                        if edit_error is None:
                            gate = (preservation(original, changed, folder, os.environ['LYNETTE_BIN']) if benchmark == 'verusbench'
                                    else {'status': 'valid', 'reason': 'fixed prefix/suffix, checked catalogue and validated action'})
                        write_json(folder / 'integrity.json', gate)
                        accepted = edit_error is None and gate['status'] == 'valid'
                        write_text(folder / 'candidate.rs', changed)
                        write_json(folder / 'action.json', proposed)
                        verified = check(checker, benchmark, folder, changed, proposed) if accepted else None
                        result = {'success': bool(verified and verified['success']), 'accepted': accepted,
                            'edit_error': edit_error, 'error': edit_error or ('integrity_' + gate['status'] if not accepted else verified['error_type']),
                            'rejection': edit_error or gate.get('reason', ''),
                            'integrity_status': gate['status'], 'unchanged': tokens(changed) == tokens(current) and proposed == action,
                            'exposed': bool(payload and payload.get('queries')), 'input_tokens': response['input_tokens'],
                            'output_tokens': response['output_tokens'], 'truncated': response['truncated']}
                        write_json(folder / 'result.json', result)
                attempts.append({'repair': n, 'overall_proposal': n + (1 if benchmark == 'verusbench' else 0), **result})
                if result['success']:
                    break
                if result['accepted']:
                    current = (folder / 'candidate.rs').read_text(encoding='utf-8')
                    verification, action, state_folder = read_json(folder / 'verification.json'), read_json(folder / 'action.json'), folder
                    rejection = None
                else:
                    rejection = result.get('rejection') or result['error']
            write_json(output / 'task.json', {'id': key, 'status': 'completed', 'success': any(a['success'] for a in attempts), 'attempts': attempts})
            print(arm, key, 'solved' if any(a['success'] for a in attempts) else 'failed', flush=True)
        if (i + 1) % 10 == 0 or i + 1 == len(plan['tasks']):
            report(root)


def report(root):
    plan = read_json(root / 'manifest.json')
    summaries, wins = {}, {}
    initial = {t['id'] for t in plan['tasks'] if t['status'] == 'initial_success'}
    for arm in ARMS:
        done = [read_json(root / arm / t['id'] / 'task.json') for t in plan['tasks'] if (root / arm / t['id'] / 'task.json').exists()]
        solved = {t['id'] for t in done if t['success']}
        wins[arm] = solved
        attempts = [a for t in done for a in t['attempts']]
        summaries[arm] = {'expected': len(plan['tasks']), 'completed': len(done), 'initial_successes': len(initial),
            'missing_ids': [t['id'] for t in plan['tasks'] if not (root / arm / t['id'] / 'task.json').exists()],
            'eligible_failed': sum(t['status'] == 'eligible' for t in plan['tasks']), 'repaired': len(solved),
            'through_proposal': {str(n): len(initial) + sum(any(a['success'] and a['overall_proposal'] <= n for a in t['attempts']) for t in done) for n in (1, 2, 3)},
            'statuses': dict(Counter(t['status'] for t in done)), 'errors': dict(Counter(a.get('error') for a in attempts)),
            'edit_errors': dict(Counter(a['edit_error'] for a in attempts if a.get('edit_error'))),
            'exposed_attempts': sum(a.get('exposed', False) for a in attempts),
            'truncated': sum(a.get('truncated', False) for a in attempts),
            'input_tokens': sum(a.get('input_tokens', 0) for a in attempts), 'output_tokens': sum(a.get('output_tokens', 0) for a in attempts),
            'by_category': {c: sum(t['id'] in solved | initial for t in plan['tasks'] if t['category'] == c) for c in sorted({t['category'] for t in plan['tasks']})},
            'unflagged_verified': len((solved | initial) - set(plan['overlap_flagged_ids'])),
            'unflagged_expected': len(plan['tasks']) - len(plan['overlap_flagged_ids'])}
    result = {'benchmark': plan['benchmark'], 'summaries': summaries,
        'complete': all(s['completed'] == s['expected'] for s in summaries.values()),
        'both_repaired': sorted(wins[ARMS[0]] & wins[ARMS[1]]),
        'only_with': sorted(wins[ARMS[1]] - wins[ARMS[0]]), 'only_without': sorted(wins[ARMS[0]] - wins[ARMS[1]]),
        'initial_statuses': dict(Counter(t['status'] for t in plan['tasks'])),
        'initial_status_ids': {status: [t['id'] for t in plan['tasks'] if t['status'] == status]
                              for status in sorted({t['status'] for t in plan['tasks']})},
        'scope': 'Trained adapter; localized repair; 3 total proposals. VerusBench includes reused shared full-file first proposal and two new edits. Solver Needs uses 3 JSON slot/settings actions. Editor/gate exclusions are separate from proof failure.'}
    write_json(root / 'comparison.json', result)
    lines = ['# SAFE-tuned localized: ' + plan['benchmark'], '', '| Arm | Completed | Through 1 | Through 2 | Through 3 |', '|---|---|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{s['expected']} | " + ' | '.join(str(s['through_proposal'][str(n)]) for n in (1, 2, 3)) + ' |')
    lines += ['', 'Initial statuses: ' + str(result['initial_statuses']), 'Complete: ' + str(result['complete']), result['scope']]
    write_text(root / 'comparison.md', '\n'.join(lines) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['prepare', 'run', 'report'])
    p.add_argument('--source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.command == 'report':
        report(args.output.resolve())
        return
    import fcntl
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'prepare':
            if args.source is None:
                p.error('--source required')
            prepare(args)
        else:
            run(args.output.resolve())


if __name__ == '__main__':
    main()
