"""Paired multi-edit REPAIR-ONLY evaluation on frozen prior failed candidates."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path

from baseline.integrity import tokens
from baseline.storage import read_json, write_json, write_text
from localized_sft.convert import sha
from localized_sft.editor import FORMAT, EditError, apply, regions
from localized_sft.prompt import ROOT, messages
from safe_internals.pipeline import collect_events
from safe_internals.validation import preservation
from sft_eval.__main__ import CONFIG, tool_hashes, verifier, implementation as base_implementation
from sft_eval.inference import Engine, adapter_identity
from sft_local_eval.__main__ import frozen_source
from solver_needs_study.feedback import internals

ARMS = ('without_internals', 'with_internals')


def implementation():
    paths = [*Path(__file__).parent.glob('*.py'), ROOT / 'prompts/safe-multiedit.txt',
             ROOT / 'repair_study/regions.py', ROOT / 'repair_study/regions_v2.py',
             ROOT / 'solver_needs_study/actions.py', ROOT / 'sft_local_eval/__main__.py']
    return {**base_implementation(), **{str(p.relative_to(ROOT)): sha(p) for p in paths}}


def validate(root):
    plan = read_json(root / 'manifest.json')
    if plan['implementation'] != implementation() or plan['tools'] != tool_hashes():
        raise ValueError('Code/prompts/tools changed: use a new study directory')
    if plan['adapter_identity'] != adapter_identity(plan['adapter']):
        raise ValueError('Adapter changed')
    for name, expected in plan['frozen_files'].items():
        if sha(root / name) != expected:
            raise ValueError('Frozen source changed: ' + name)
    return plan


def prepare(args):
    root, source = args.output.resolve(), args.source.resolve()
    if root == source or root in source.parents or source in root.parents:
        raise ValueError('Use separate study directories')
    if (root / 'manifest.json').exists():
        saved = validate(root)
        if saved['source'] != str(source) or saved['adapter'] != str(args.adapter.resolve()):
            raise ValueError('Preparation arguments changed')
        return
    if root.exists() and any(p.name != '.lock' for p in root.iterdir()):
        raise ValueError('Incomplete output directory; preserve it and choose a new directory')
    previous = read_json(source / 'manifest.json')
    for name, expected in previous.get('files', previous.get('frozen_files', {})).items():
        if sha(source / name) != expected:
            raise ValueError('Source input differs from its saved manifest: ' + name)
    identity = adapter_identity(args.adapter)
    training = identity['provenance']['dataset_manifest']
    if training.get('response_format') != FORMAT:
        raise ValueError('Adapter was not trained with this multi-edit format')
    for name, expected in training['implementation'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Training/editor format drift: ' + name)
    if tool_hashes() != previous['tools']:
        raise ValueError('Use the same verifier/tool versions as the frozen source')
    plan = {'benchmark': args.benchmark, 'adapter': str(args.adapter.resolve()),
        'adapter_identity': identity, 'source': str(source), 'source_manifest_sha256': sha(source / 'manifest.json'),
        'implementation': implementation(), 'tools': tool_hashes(), 'config': CONFIG, 'tasks': [],
        'response_format': FORMAT, 'proposals': 3,
        'scope': 'REPAIR ONLY: three multi-edit proposals on frozen failures from a previous model. '
                 'Prior successes/rejections excluded, not credited to this adapter. '
                 'Both datasets use the same editor; no Solver Needs law catalogue or NLA toggle.'}
    if previous['benchmark'] != args.benchmark:
        raise ValueError('Source benchmark mismatch')
    for item in previous['tasks']:
        key = item['id']
        source_folder = source / 'inputs' / key
        if 'status' in item:  # Previously prepared localized study.
            status = item['status']
        elif args.benchmark == 'verusbench':
            source_folder = source / 'shared' / key / 'proposal_01'
            result = read_json(source_folder / 'result.json')
            status = 'initial_success' if result['success'] else 'eligible' if result['accepted'] else 'initial_rejected'
        else:
            status = 'initial_success' if read_json(source_folder / 'verification.json')['success'] else 'eligible'
        dest = root / 'inputs' / key
        frozen_source(source_folder, dest)
        code = (dest / 'candidate.rs').read_text(encoding='utf-8')
        original_path = source / 'inputs' / key / ('original.rs' if 'status' in item else 'candidate.rs')
        original = original_path.read_text(encoding='utf-8')
        write_text(dest / 'original.rs', original)
        # Old editor limitations are retried under the new editor, without restoring rejected programs.
        if status == 'editor_unavailable':
            status = 'eligible'
        if (dest / 'verification.json').exists() and read_json(dest / 'verification.json')['success']:
            status = 'initial_success'
        if status == 'eligible':
            if not (dest / 'verification.json').exists():
                raise ValueError('Eligible source lacks verification evidence: ' + key)
            try:
                offered = regions(code)
                status = 'eligible' if offered else 'editor_unavailable'
                write_json(dest / 'editor-audit.json', {'status': status, 'sites': offered})
            except ValueError as error:
                status = 'editor_unparseable'
                write_json(dest / 'editor-audit.json', {'status': status, 'reason': str(error)})
        plan['tasks'].append({'id': key, 'category': item['category'], 'status': status})
        print('Prepared', key, status, flush=True)
    plan['frozen_files'] = {str(p.relative_to(root)): sha(p) for p in (root / 'inputs').rglob('*') if p.is_file()}
    write_json(root / 'manifest.json', plan)


def diagnostic(value):
    return str(value.get('stdout', '')) + '\n' + str(value.get('stderr', ''))


def run(root):
    plan = validate(root)
    if not any(t['status'] == 'eligible' for t in plan['tasks']):
        report(root)
        return
    engine, checker = Engine(plan['adapter']), verifier(plan['benchmark'])
    for i, task in enumerate(plan['tasks']):
        key = task['id']
        if task['status'] != 'eligible':
            continue
        for arm in ARMS:
            output = root / arm / key
            if (output / 'task.json').exists():
                continue
            initial = root / 'inputs' / key
            current = (initial / 'candidate.rs').read_text(encoding='utf-8')
            original = (initial / 'original.rs').read_text(encoding='utf-8')
            verification = read_json(initial / 'verification.json')
            state, rejection, attempts = initial, None, []
            for n in range(1, 4):
                folder = output / f'proposal_{n:02d}'
                if (folder / 'result.json').exists():
                    result = read_json(folder / 'result.json')
                else:
                    payload = None
                    try:
                        offered = regions(current)
                        if not offered:
                            raise EditError('editor_unavailable', 'No offered regions')
                    except ValueError as error:
                        write_json(folder / 'result.json', {'success': False, 'accepted': False,
                            'category': 'editor_unavailable', 'error': str(error)})
                        attempts.append({'proposal': n, **read_json(folder / 'result.json')})
                        break
                    base = messages(current, diagnostic(verification), rejection=rejection, offered=offered)
                    count = len(engine.tokenizer.apply_chat_template(base, tokenize=True, add_generation_prompt=True))
                    if count + 4096 > 32768:
                        result = {'success': False, 'accepted': False, 'category': 'context_budget', 'error': 'Base prompt exceeds reservation'}
                    else:
                        if arm == 'with_internals':
                            packet = folder / 'packet'
                            frozen_source(state, packet)
                            write_text(packet / 'candidate.rs', current)
                            collect_events(packet, verification, CONFIG)
                            def builder(code, v, a, context, p, history, **unused):
                                return messages(code, diagnostic(v), p, rejection, offered)
                            try:
                                payload = internals(packet, current, verification, {}, [], engine.tokenizer,
                                    CONFIG, replay=False, message_builder=builder)['internals']
                            except ValueError as error:
                                if 'exceed context' not in str(error):
                                    raise
                                write_json(packet / 'omission.json', {'reason': str(error)})
                        request = messages(current, diagnostic(verification), payload, rejection, offered)
                        count = len(engine.tokenizer.apply_chat_template(request, tokenize=True, add_generation_prompt=True))
                        if count + 4096 > 32768:
                            raise ValueError('Packet budget violation; no truncation')
                        seed = 20261018 + i * 10 + n - 1
                        write_json(folder / 'request.json', {'messages': request, 'seed': seed,
                            'input_tokens': count, 'internals_exposed': bool(payload and payload.get('queries'))})
                        if not (folder / 'response.json').exists():
                            write_json(folder / 'response.json', engine.generate(request, seed))
                        response = read_json(folder / 'response.json')
                        result = {'success': False, 'accepted': False, 'category': None, 'error': None,
                            'input_tokens': response['input_tokens'], 'output_tokens': response['output_tokens'],
                            'truncated': response['truncated'], 'exposed': bool(payload and payload.get('queries'))}
                        try:
                            changed = apply(current, response['text'], offered)
                        except ValueError as error:
                            result.update(category=getattr(error, 'category', 'editor_error'), error=str(error))
                        else:
                            write_text(folder / 'candidate.rs', changed)
                            gate = preservation(original, changed, folder, os.environ['LYNETTE_BIN'])
                            write_json(folder / 'integrity.json', gate)
                            if gate['status'] != 'valid':
                                # invalid, unparseable and checker_error are never merged.
                                result.update(category='integrity_' + gate['status'], error=gate.get('reason') or str(gate))
                            else:
                                value = checker.verify(folder / 'candidate.rs')
                                write_json(folder / 'verification.json', value)
                                if value['error_type'] == 'verifier_error':
                                    raise RuntimeError('Verifier infrastructure failure; resume this directory after fixing tools')
                                result.update(accepted=True, success=bool(value['success']),
                                    category='success' if value['success'] else value['error_type'],
                                    error=None if value['success'] else diagnostic(value))
                        result['unchanged'] = result['category'] == 'no_effect'
                    write_json(folder / 'result.json', result)
                attempts.append({'proposal': n, **result})
                if result['success']:
                    break
                if result['accepted']:
                    current = (folder / 'candidate.rs').read_text(encoding='utf-8')
                    verification, state, rejection = read_json(folder / 'verification.json'), folder, None
                else:
                    rejection = str(result.get('category')) + ': ' + str(result.get('error'))
            write_json(output / 'task.json', {'id': key, 'success': any(a['success'] for a in attempts), 'attempts': attempts})
            print(arm, key, 'solved' if any(a['success'] for a in attempts) else 'failed', flush=True)
        if (i + 1) % 10 == 0:
            report(root)
    report(root)


def report(root):
    plan = read_json(root / 'manifest.json')  # Saved-record reporting does not reject current-code drift.
    eligible = [t for t in plan['tasks'] if t['status'] == 'eligible']
    summaries, solved = {}, {}
    for arm in ARMS:
        done = [read_json(root / arm / t['id'] / 'task.json') for t in eligible if (root / arm / t['id'] / 'task.json').exists()]
        attempts = [a for row in done for a in row['attempts']]
        solved[arm] = {row['id'] for row in done if row['success']}
        summaries[arm] = {'expected': len(eligible), 'completed': len(done), 'solved': len(solved[arm]),
            'through_proposal': {str(n): sum(any(a['success'] and a['proposal'] <= n for a in row['attempts']) for row in done) for n in (1, 2, 3)},
            'categories': dict(Counter(a['category'] for a in attempts)),
            'by_category': {c: sum(t['id'] in solved[arm] for t in eligible if t['category'] == c)
                            for c in sorted({t['category'] for t in eligible})},
            'missing': [t['id'] for t in eligible if not (root / arm / t['id'] / 'task.json').exists()],
            'input_tokens': sum(a.get('input_tokens', 0) for a in attempts),
            'output_tokens': sum(a.get('output_tokens', 0) for a in attempts),
            'truncated': sum(a.get('truncated', False) for a in attempts),
            'exposed_attempts': sum(a.get('exposed', False) for a in attempts)}
    result = {'scope': plan['scope'], 'benchmark': plan['benchmark'], 'summaries': summaries,
        'initial_statuses': dict(Counter(t['status'] for t in plan['tasks'])),
        'excluded_ids': {status: [t['id'] for t in plan['tasks'] if t['status'] == status]
                         for status in sorted({t['status'] for t in plan['tasks']}) if status != 'eligible'},
        'complete': all(s['completed'] == s['expected'] for s in summaries.values()),
        'both': sorted(solved[ARMS[0]] & solved[ARMS[1]]),
        'only_with': sorted(solved[ARMS[1]] - solved[ARMS[0]]),
        'only_without': sorted(solved[ARMS[0]] - solved[ARMS[1]])}
    write_json(root / 'comparison.json', result)
    lines = ['# SAFE multi-edit: ' + plan['benchmark'], '', plan['scope'], '',
             '| Arm | Completed eligible | Through 1 | Through 2 | Through 3 |', '|---|---|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{s['expected']} | " + ' | '.join(str(s['through_proposal'][str(n)]) for n in (1, 2, 3)) + ' |')
    lines += ['', 'Initial statuses: ' + str(result['initial_statuses']), 'Complete: ' + str(result['complete'])]
    write_text(root / 'comparison.md', '\n'.join(lines) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'run', 'report'])
    p.add_argument('--benchmark', choices=['verusbench', 'solver-needs'])
    p.add_argument('--source', type=Path)
    p.add_argument('--adapter', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.command == 'report':
        report(args.output.resolve())
        return
    if args.command == 'prepare' and any(x is None for x in (args.source, args.adapter, args.benchmark)):
        p.error('prepare requires --source, --adapter and --benchmark')
    import fcntl
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'prepare':
            prepare(args)
        else:
            run(args.output.resolve())


if __name__ == '__main__':
    main()
