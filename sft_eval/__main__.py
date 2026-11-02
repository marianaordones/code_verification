"""Two feedback arms, full Verus files, three proposals; no fine-tuning here."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

from baseline.benchmark import load_tasks
from baseline.inference import extract_code
from baseline.storage import digest, read_json, write_json, write_text
from baseline.provenance import tool_identity, tool_signature
from baseline.prompts import ROOT
from safe_internals.pipeline import PilotVerifier, collect_events, message_builder, visible_messages
from safe_internals.validation import preservation
from solver_needs_study.feedback import internals
from solver_needs_study.verify import StudyVerifier
from .inference import adapter_identity, Engine

ARMS = ('without_internals', 'with_internals')
CONFIG = {'max_model_len': 32768, 'max_tokens': 4096, 'internals_token_budget': 24576,
          'max_quantifiers': 50, 'max_instances_each': 3, 'max_queries': 3,
          'normalize_statistics': True, 'raw_instances_per_group': 8,
          'replay_wall_seconds': 20, 'replay_memory_mb': 2048}


def implementation():
    files = [*Path(__file__).parent.glob('*.py'), ROOT / 'prompts/safe-internals.txt',
             ROOT / 'safe_internals/pipeline.py', ROOT / 'safe_internals/validation.py',
             ROOT / 'safe_internals/verify.py', ROOT / 'solver_needs_study/feedback.py',
             ROOT / 'solver_needs_study/verify.py', ROOT / 'repair_study/worker.py',
             ROOT / 'repair_study/relevance.py', ROOT / 'baseline/integrity.py',
             ROOT / 'baseline/obligation.py', ROOT / 'diagnostics/z3_probe.py']
    files.append(ROOT / 'scripts/safe_sft_data.py')
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in files}


def system(benchmark):
    text = (ROOT / 'prompts/safe-internals.txt').read_text(encoding='utf-8')
    task = ('Complete the proof annotations in this VerusBench program.' if benchmark == 'verusbench' else
            'Repair this previously verified Verus program from which an essential assertion was removed. '
            'You are not given the removed assertion or the task label. Possible gaps include a missing '
            'collection identity, a quantified fact needing a useful concrete term or witness, nonlinear '
            'arithmetic needing a checked nonlinear_arith proof, or recursive unfolding needing reveal_with_fuel. '
            'These are possibilities, not a diagnosis. Add only checked proof code; no assumption of a missing law.')
    return task + '\n\n' + text + '\nInternals may be withheld by the evaluation design; an absent block is not evidence that the solver observed no events.'


def messages(code, verification, instruction, payload=None, rejection=None):
    result = visible_messages(code, verification, instruction, payload)
    if rejection:
        result[-1]['content'] += '\n<previous_edit_rejection>\n' + rejection + '\n</previous_edit_rejection>\n'
    return result


def tool_hashes():
    return {name: tool_signature(tool_identity(os.environ[env])) for name, env in
            [('verus', 'VERUS_BIN'), ('z3', 'Z3_BIN'), ('lynette', 'LYNETTE_BIN')]}


def verifier(benchmark):
    if benchmark == 'solver-needs':
        return StudyVerifier(os.environ['VERUS_BIN'], os.environ['Z3_BIN'], 120)
    return PilotVerifier(os.environ['VERUS_BIN'], os.environ['Z3_BIN'], 120, 4096)


def verify_cached(checker, folder, code):
    write_text(folder / 'candidate.rs', code)
    if not (folder / 'verification.json').exists():
        value = checker.verify(folder / 'candidate.rs')
        if value['error_type'] == 'verifier_error':
            raise RuntimeError('Verifier infrastructure error; inspect ' + str(folder))
        write_json(folder / 'verification.json', value)
    return read_json(folder / 'verification.json')


def prepare(args):
    from transformers import AutoTokenizer
    from baseline.inference import prepare_model, MODEL_CODER, REVISION_CODER
    root = args.output.resolve()
    identity = adapter_identity(args.adapter)
    training = read_json(args.training_data / 'manifest.json')
    if training != identity['provenance']['dataset_manifest']:
        raise ValueError('Training data does not match adapter provenance')
    for file, expected in training['files_sha256'].items():
        if digest((args.training_data / file).read_bytes()) != expected:
            raise ValueError('Training export changed: ' + file)
    source_rows = read_json(args.safe_dataset)
    if digest(args.safe_dataset.read_bytes()) != training['dataset_sha256']:
        raise ValueError('SAFE source changed')
    tasks = []
    if args.benchmark == 'verusbench':
        for row in load_tasks(ROOT / 'data/manifest.json'):
            tasks.append({'id': row['id'], 'category': row['category'],
                          'code': Path(row['file']).read_text(encoding='utf-8')})
    else:
        from solver_needs_study.download import source
        from solver_needs_study.data import cases, split_task
        source()
        for row in cases():
            parts = split_task(row)
            tasks.append({'id': row['id'], 'category': row['paper_label'],
                          'code': parts['prefix'] + '\n/* proof repair location */\n' + parts['suffix']})
    plan = {'benchmark': args.benchmark, 'adapter': str(args.adapter.resolve()), 'adapter_identity': identity,
            'implementation': implementation(), 'tools': tool_hashes(), 'config': CONFIG,
            'system_prompt': system(args.benchmark), 'proposals': 3,
            'first_proposal_shared': args.benchmark == 'verusbench',
            'tasks': [{'id': t['id'], 'category': t['category'], 'input_sha256': digest(t['code'].encode())} for t in tasks]}
    root.mkdir(parents=True, exist_ok=True)
    if (root / 'preparation.json').exists() and read_json(root / 'preparation.json') != plan:
        raise ValueError('Preparation changed; use a new output directory')
    write_json(root / 'preparation.json', plan)
    # Screen actual training rows, not the validation split, against each input.
    overlap_path = root / 'training-overlap.json'
    if not overlap_path.exists():
        from scripts.safe_sft_data import overlap
        actual = [json.loads(line) for line in (args.training_data / 'train.jsonl').read_text(encoding='utf-8').splitlines()]
        indices = [int(row['id'].split('-')[1]) for row in actual]
        for task in tasks:
            write_text(root / 'inputs' / task['id'] / 'candidate.rs', task['code'])
        benchmark_path = root / 'overlap-inputs.json'
        write_json(benchmark_path, {'tasks': [{'id': t['id'], 'path': f"inputs/{t['id']}/candidate.rs"} for t in tasks]})
        audit = overlap([source_rows[i] for i in indices], benchmark_path)
        for hit in audit['hits']:
            hit['id'] = f"safe-{indices[int(hit['id'].split('-')[1])]:05d}"
        audit['scope'] += ' Actual training IDs only; flags are not proof of identity; no renamed-variant guarantee.'
        write_json(overlap_path, audit)
    flagged = {h['benchmark'] for h in read_json(overlap_path)['hits']}
    tokenizer = AutoTokenizer.from_pretrained(prepare_model(MODEL_CODER, REVISION_CODER))
    checker = verifier(args.benchmark)
    config = {**CONFIG, 'system_prompt_text': plan['system_prompt']}
    for task in tasks:
        folder = root / 'inputs' / task['id']
        if (folder / 'ready.json').exists():
            continue
        value = verify_cached(checker, folder, task['code'])
        base_gate = preservation(task['code'], task['code'], folder / 'baseline-integrity', os.environ['LYNETTE_BIN'])
        write_json(folder / 'baseline-integrity.json', base_gate)
        # Both arms share the same frozen initial verification and raw events.
        if args.benchmark == 'solver-needs' and not value['success']:
            pack(folder, task['code'], value, tokenizer, config, plan['system_prompt'], None)
        write_json(folder / 'ready.json', {'initial_success': value['success'],
            'baseline_integrity_status': base_gate['status'], 'training_overlap_flag': task['id'] in flagged})
        print('Prepared', task['id'], flush=True)
    plan['overlap_flagged_ids'] = sorted(flagged)
    plan['files'] = {str(p.relative_to(root)): digest(p.read_bytes()) for p in (root / 'inputs').rglob('*') if p.is_file()}
    plan['overlap_sha256'] = digest(overlap_path.read_bytes())
    write_json(root / 'manifest.json', plan)
    print('Prepared evaluation:', root)


def validate(root):
    plan = read_json(root / 'manifest.json')
    if plan['implementation'] != implementation():
        raise ValueError('Evaluation code/prompts changed; use another output directory')
    if plan['adapter_identity'] != adapter_identity(plan['adapter']) or plan['tools'] != tool_hashes():
        raise ValueError('Adapter or native tools changed')
    if digest((root / 'training-overlap.json').read_bytes()) != plan['overlap_sha256']:
        raise ValueError('Training overlap audit changed')
    for file, expected in plan['files'].items():
        if digest((root / file).read_bytes()) != expected:
            raise ValueError('Frozen input changed: ' + file)
    return plan


def pack(folder, code, verification, tokenizer, config, instruction, rejection):
    if verification['success']:
        return None
    collect_events(folder, verification, config)
    def builder(code, verification, action, context, payload, history, **kwargs):
        return messages(code, verification, instruction, payload, rejection)
    try:
        return internals(folder, code, verification, {}, [], tokenizer, config, replay=False,
                         message_builder=builder)['internals']
    except ValueError as error:
        if 'exceed context' not in str(error):
            raise
        write_json(folder / 'packet-omission.json', {'reason': str(error), 'availability': 'unavailable_context_budget'})
        return None


def proposal(folder, initial, current, verification, payload, rejection, seed, engine, checker, instruction):
    if (folder / 'result.json').exists():
        return read_json(folder / 'result.json')
    request = messages(current, verification, instruction, payload, rejection)
    count = len(engine.tokenizer.apply_chat_template(request, tokenize=True, add_generation_prompt=True))
    if count + 4096 > 32768:
        result = {'success': False, 'accepted': False, 'error': 'context_budget', 'input_tokens': count}
        write_json(folder / 'result.json', result)
        return result
    write_json(folder / 'request.json', {'messages': request, 'seed': seed, 'input_tokens': count,
                                       'adapter_applied': True})
    if not (folder / 'response.json').exists():
        write_json(folder / 'response.json', engine.generate(request, seed))
    response = read_json(folder / 'response.json')
    code = extract_code(response['text'], False)
    write_text(folder / 'candidate.rs', code)
    gate = preservation(initial, code, folder, os.environ['LYNETTE_BIN'])
    write_json(folder / 'integrity.json', gate)
    accepted = gate['status'] == 'valid'
    result = {'success': False, 'accepted': accepted, 'integrity_status': gate['status'],
              'rejection': gate.get('reason', ''), 'unchanged': code.strip() == current.strip(),
              'input_tokens': response['input_tokens'], 'output_tokens': response['output_tokens'],
              'truncated': response['truncated'], 'exposed': bool(payload and payload.get('queries'))}
    if accepted:
        checked = verify_cached(checker, folder, code)
        result.update(success=checked['success'], error=checked['error_type'])
    else:
        result['error'] = 'integrity_' + gate['status']
    write_json(folder / 'result.json', result)
    return result


def run(root):
    plan = validate(root)
    config = {**CONFIG, 'system_prompt_text': plan['system_prompt']}
    engine = Engine(plan['adapter'])
    checker = verifier(plan['benchmark'])
    for index, task in enumerate(plan['tasks']):
        key = task['id']
        initial_folder = root / 'inputs' / key
        initial = (initial_folder / 'candidate.rs').read_text(encoding='utf-8')
        initial_check = read_json(initial_folder / 'verification.json')
        shared = None
        if plan['first_proposal_shared'] and not initial_check['success']:
            shared_folder = root / 'shared' / key / 'proposal_01'
            shared = proposal(shared_folder, initial, initial, initial_check, None, None,
                              20261018 + index * 10, engine, checker, plan['system_prompt'])
        for arm in ARMS:
            destination = root / arm / key
            if (destination / 'task.json').exists():
                continue
            state, checked, state_folder, rejection = initial, initial_check, initial_folder, None
            results = []
            for attempt in range(1, 4):
                if checked['success']:
                    break
                if attempt == 1 and shared is not None:
                    folder, result = shared_folder, shared
                else:
                    folder = destination / f'proposal_{attempt:02d}'
                    payload = None
                    if arm == 'with_internals':
                        payload = pack(state_folder, state, checked, engine.tokenizer, config,
                                       plan['system_prompt'], rejection)
                    result = proposal(folder, initial, state, checked, payload, rejection,
                        20261018 + index * 10 + attempt - 1, engine, checker, plan['system_prompt'])
                results.append({'proposal': attempt, 'path': str(folder.relative_to(root)), **result})
                if result['accepted']:
                    state = (folder / 'candidate.rs').read_text(encoding='utf-8')
                    checked = read_json(folder / 'verification.json')
                    state_folder, rejection = folder, None
                else:
                    rejection = result.get('rejection') or result['error']
            write_json(destination / 'task.json', {'id': key, 'initial_success': initial_check['success'],
                'success': bool(results and results[-1]['success']), 'attempts': results})
            print(arm, key, 'solved' if results and results[-1]['success'] else 'failed', flush=True)
        if (index + 1) % 10 == 0 or index + 1 == len(plan['tasks']):
            report(root)


def report(root):
    plan = read_json(root / 'manifest.json')
    baseline_valid = {task['id'] for task in plan['tasks']
        if (root / 'inputs' / task['id'] / 'ready.json').exists()
        and read_json(root / 'inputs' / task['id'] / 'ready.json').get('baseline_integrity_status') == 'valid'}
    summaries, solved_sets = {}, {}
    for arm in ARMS:
        done, missing = [], []
        for task in plan['tasks']:
            path = root / arm / task['id'] / 'task.json'
            if path.exists():
                done.append(read_json(path))
            else:
                missing.append(task['id'])
        solved = {r['id'] for r in done if r['success']}
        solved_sets[arm] = solved
        attempts = [a for r in done for a in r['attempts']]
        initially = {r['id'] for r in done if r['initial_success']}
        curves = {str(n): sum(r['initial_success'] or any(a['success'] and a['proposal'] <= n for a in r['attempts']) for r in done) for n in (1, 2, 3)}
        summaries[arm] = {'expected': len(plan['tasks']), 'completed': len(done), 'missing': missing,
            'initially_verified': len(initially), 'repaired': len(solved), 'through_proposal': curves,
            'total_verified': len(solved | initially), 'attempts': len(attempts),
            'errors': dict(Counter(a.get('error') for a in attempts)),
            'unchanged': sum(a.get('unchanged', False) for a in attempts),
            'truncated': sum(a.get('truncated', False) for a in attempts),
            'exposed_attempts': sum(a.get('exposed', False) for a in attempts),
            'input_tokens': sum(a.get('input_tokens', 0) for a in attempts),
            'output_tokens': sum(a.get('output_tokens', 0) for a in attempts),
            'by_category': {category: sum(t['id'] in solved | initially for t in plan['tasks'] if t['category'] == category)
                            for category in sorted({t['category'] for t in plan['tasks']})},
            'unflagged_total_verified': len((solved | initially) - set(plan['overlap_flagged_ids'])),
            'unflagged_expected': len(plan['tasks']) - len(plan['overlap_flagged_ids']),
            'baseline_gate_valid_expected': len(baseline_valid),
            'baseline_gate_valid_verified': len((solved | initially) & baseline_valid)}
    result = {'benchmark': plan['benchmark'], 'summaries': summaries,
        'baseline_integrity': dict(Counter(read_json(root / 'inputs' / task['id'] / 'ready.json').get('baseline_integrity_status', 'not_recorded')
                                          for task in plan['tasks'] if (root / 'inputs' / task['id'] / 'ready.json').exists())),
        'both_repaired': sorted(solved_sets[ARMS[0]] & solved_sets[ARMS[1]]),
        'only_with': sorted(solved_sets[ARMS[1]] - solved_sets[ARMS[0]]),
        'only_without': sorted(solved_sets[ARMS[0]] - solved_sets[ARMS[1]]),
        'overlap_flagged_ids': plan['overlap_flagged_ids'],
        'complete': all(not s['missing'] for s in summaries.values()),
        'first_proposal_shared': plan['first_proposal_shared'],
        'scope': 'Fine-tuned model in both arms; full-file output; three proposals. Shared proposals counted in both arm totals but executed once. Overlap flags are screening, not proof of contamination or independence.'}
    write_json(root / 'comparison.json', result)
    lines = ['# SAFE-tuned model: ' + plan['benchmark'], '', '| Arm | Completed | Through 1 | Through 2 | Through 3 |', '|---|---|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{s['expected']} | " + ' | '.join(str(s['through_proposal'][str(n)]) for n in (1, 2, 3)) + ' |')
    lines += ['', f"Complete: {result['complete']}. Training-overlap flags: {len(plan['overlap_flagged_ids'])}.",
              f"Original-input preservation audit: {result['baseline_integrity']}. Failures identify gate/parser limitations, not proof impossibility.",
              'Curves include initially verified inputs; these are reported separately and are not model repairs.', result['scope']]
    write_text(root / 'comparison.md', '\n'.join(lines) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'run', 'report'])
    p.add_argument('--benchmark', choices=['verusbench', 'solver-needs'])
    p.add_argument('--adapter', type=Path, default=ROOT / 'results/safe-sft-a100-v1/adapter')
    p.add_argument('--training-data', type=Path, default=ROOT / 'data/safe/sft-enriched-v1')
    p.add_argument('--safe-dataset', type=Path, default=ROOT / 'data/safe/sft_safe_25k.json')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    # One writer per study; locks release on interruption. Reporting reads saved state only.
    if args.command == 'report':
        report(args.output.resolve())
        return
    import fcntl
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'prepare':
            if args.benchmark is None:
                p.error('--benchmark required for prepare')
            prepare(args)
        else:
            run(args.output.resolve())


if __name__ == '__main__':
    main()
