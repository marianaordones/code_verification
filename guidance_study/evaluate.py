"""No-internals paired oracle diagnostic. All proposals edit the same frozen candidate."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path

from baseline.inference import MODEL_CODER, REVISION_CODER, prepare_model
from baseline.integrity import tokens
from baseline.storage import read_json, write_json, write_text
from localized_sft.convert import sha
from localized_sft.editor import EditError
from safe_internals.validation import preservation
from sft_eval.__main__ import tool_hashes, verifier
from sft_eval.inference import Engine as AdapterEngine, adapter_identity
from .editor import ACTIONS, apply, regions

ROOT = Path(__file__).resolve().parents[1]
ARMS = ('without_guidance', 'with_guidance')


def implementation():
    files = [*Path(__file__).parent.glob('*.py'), *list((ROOT / 'localized_sft').glob('*.py')),
             ROOT / 'sft_eval/inference.py', ROOT / 'sft_eval/__main__.py',
             ROOT / 'safe_internals/validation.py', ROOT / 'repair_study/regions.py',
             ROOT / 'repair_study/regions_v2.py', ROOT / 'baseline/integrity.py']
    return {str(p.relative_to(ROOT)): sha(p) for p in files}


def model_identity(adapter):
    return {'model': MODEL_CODER, 'revision': REVISION_CODER,
            'adapter': str(adapter.resolve()) if adapter else None,
            'adapter_identity': adapter_identity(adapter) if adapter else None}


def prompt(code, diagnostics, sites, decisions=None, previous=None):
    system = ('Repair the Verus proof without changing executable code or original contracts. '
        'Return only JSON {"edits":[{"site_id":"R1","replacement":"..."}]}. '
        'Use only offered sites; multiple distinct non-overlapping edits may be applied atomically. '
        'For loop_invariants return the complete desired invariant list (including old invariants that must remain), '
        'or an empty string to remove it. For proof_block return a complete proof { ... } block or remove it. '
        'For insert_proof insert proof statements/assertions or one proof block. '
        'For lemma_definitions insert only new proof fn definitions with unique names; calls may be inserted '
        'in proof sites. No assume/admit, trusted attributes, executable mutation, imports or changed specifications. '
        'The three action families are loop_invariants, assertions_and_proof, and lemmas; they may overlap. '
        'Parenthesize casts before < comparisons. Every proposal edits the SAME frozen input, '
        'not the previous failed file. Previous proposals are feedback only. '
        'If oracle guidance is present, it identifies sites/actions in one verified reference repair, '
        'not its formulas or necessarily the only valid repair. Treat it as advice; other offered sites remain legal. '
        'No SMT internals are provided in either arm.')
    user = '<current_program>\n```rust\n' + code + '\n```\n</current_program>\n'
    user += '<verus_diagnostics>\n' + diagnostics + '\n</verus_diagnostics>\n'
    user += '<editable_sites>\n' + json.dumps(sites, indent=2) + '\n</editable_sites>\n'
    if previous:
        user += '<previous_proposal_feedback>\n' + json.dumps(previous, ensure_ascii=False) + '\n</previous_proposal_feedback>\n'
    if decisions is not None:
        user += '<oracle_repair_guidance>\n' + json.dumps(decisions, indent=2) + '\n</oracle_repair_guidance>\n'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


class Engine(AdapterEngine):
    def __init__(self, adapter=None):
        self.has_adapter = adapter is not None
        if adapter:
            super().__init__(adapter)
        else:
            from vllm import LLM
            local = prepare_model(MODEL_CODER, REVISION_CODER)
            self.engine = LLM(model=local, tokenizer=local, dtype='bfloat16', tensor_parallel_size=1,
                max_model_len=32768, max_num_seqs=1, gpu_memory_utilization=.90, enforce_eager=True,
                enable_chunked_prefill=True, max_num_batched_tokens=2048,
                seed=20261018, generation_config='vllm')
            self.tokenizer, self.request = self.engine.get_tokenizer(), None

    def generate(self, messages, seed):
        value = super().generate(messages, seed)
        value['adapter_applied'] = self.has_adapter
        return value


def diagnostics(value):
    return value.get('stdout', '') + '\n' + value.get('stderr', '')


def prepare(args):
    root, dataset = args.output.resolve(), args.dataset.resolve()
    if root == dataset or root in dataset.parents or dataset in root.parents:
        raise ValueError('Use separate dataset and evaluation directories')
    source = read_json(dataset / 'manifest.json')
    for name, expected in source['files'].items():
        if sha(dataset / name) != expected:
            raise ValueError('Subset changed: ' + name)
    identity = model_identity(args.adapter)
    plan = {'dataset': str(dataset), 'dataset_manifest_sha256': sha(dataset / 'manifest.json'),
        'model': identity, 'implementation': implementation(), 'tools': tool_hashes(),
        'tasks': source['tasks'], 'proposals': args.proposals, 'max_model_len': 32768, 'max_tokens': 4096,
        'internals': 'none in both arms', 'seed': 20261018,
        'scope': 'Oracle action/location diagnostic on success-selected saved failures. '
                 'All proposals start from the same frozen input; no autonomous selector and no full-benchmark claim.'}
    if plan['tools'] != source['source_tools']:
        raise ValueError('Use the archived VerusBench tool versions')
    path = root / 'manifest.json'
    if path.exists():
        if read_json(path) != plan:
            raise ValueError('Evaluation settings changed; use a new output directory')
        return
    root.mkdir(parents=True, exist_ok=True)
    checker = verifier('verusbench')
    for task in plan['tasks']:
        key = task['id']
        src = dataset / 'tasks' / key
        dest = root / 'validation' / key
        code = (src / 'candidate.rs').read_text(encoding='utf-8')
        original = (src / 'original.rs').read_text(encoding='utf-8')
        target = (src / 'reference/candidate.rs').read_text(encoding='utf-8')
        action = read_json(src / 'reference/action.json')
        if tokens(apply(code, action)) != tokens(target):
            raise ValueError('Reference not representable: ' + key)
        for label, content in [('input', code), ('reference', target)]:
            folder = dest / label
            write_text(folder / 'candidate.rs', content)
            value = checker.verify(folder / 'candidate.rs')
            gate = preservation(original, content, folder, os.environ['LYNETTE_BIN'])
            write_json(folder / 'verification.json', value)
            write_json(folder / 'integrity.json', gate)
            if value['error_type'] == 'verifier_error' or gate['status'] != 'valid' or value['success'] != (label == 'reference'):
                raise ValueError('Input/reference revalidation failed: ' + key + '/' + label)
        print('Revalidated', key, flush=True)
    write_json(path, plan)


def validate(root):
    plan = read_json(root / 'manifest.json')
    if plan['implementation'] != implementation() or plan['tools'] != tool_hashes():
        raise ValueError('Code/tools changed; use a new study directory')
    adapter = Path(plan['model']['adapter']) if plan['model']['adapter'] else None
    if plan['model'] != model_identity(adapter):
        raise ValueError('Model/adapter changed')
    dataset = Path(plan['dataset'])
    if sha(dataset / 'manifest.json') != plan['dataset_manifest_sha256']:
        raise ValueError('Subset manifest changed')
    for name, expected in read_json(dataset / 'manifest.json')['files'].items():
        if sha(dataset / name) != expected:
            raise ValueError('Subset file changed: ' + name)
    return plan


def run(root):
    plan = validate(root)
    dataset = Path(plan['dataset'])
    adapter = Path(plan['model']['adapter']) if plan['model']['adapter'] else None
    engine, checker = Engine(adapter), verifier('verusbench')
    for i, task in enumerate(plan['tasks']):
        src = dataset / 'tasks' / task['id']
        code = (src / 'candidate.rs').read_text(encoding='utf-8')
        original = (src / 'original.rs').read_text(encoding='utf-8')
        initial = read_json(root / 'validation' / task['id'] / 'input/verification.json')
        sites = regions(code)
        for arm in ARMS:
            dest = root / arm / task['id']
            if (dest / 'task.json').exists():
                continue
            history, attempts = [], []
            for n in range(1, plan['proposals'] + 1):
                folder = dest / f'proposal_{n:02d}'
                if (folder / 'result.json').exists():
                    result = read_json(folder / 'result.json')
                else:
                    request = prompt(code, diagnostics(initial), sites,
                        task['decisions'] if arm == 'with_guidance' else None, history or None)
                    size = len(engine.tokenizer.apply_chat_template(request, tokenize=True, add_generation_prompt=True))
                    seed = plan['seed'] + i * 10 + n - 1
                    if size + plan['max_tokens'] > plan['max_model_len']:
                        result = {'success': False, 'category': 'context_budget', 'error': 'Prompt exceeds output reservation'}
                    else:
                        write_json(folder / 'request.json', {'messages': request, 'seed': seed, 'input_tokens': size})
                        if not (folder / 'response.json').exists():
                            write_json(folder / 'response.json', engine.generate(request, seed))
                        response = read_json(folder / 'response.json')
                        result = {'success': False, 'category': None, 'error': None,
                            'input_tokens': response['input_tokens'], 'output_tokens': response['output_tokens'],
                            'truncated': response['truncated'], 'inference_seconds': response['inference_seconds']}
                        try:
                            changed = apply(code, response['text'], sites)
                        except ValueError as error:
                            result.update(category=getattr(error, 'category', 'editor_error'), error=str(error))
                        else:
                            write_text(folder / 'candidate.rs', changed)
                            gate = preservation(original, changed, folder, os.environ['LYNETTE_BIN'])
                            write_json(folder / 'integrity.json', gate)
                            if gate['status'] != 'valid':
                                result.update(category='integrity_' + gate['status'], error=gate.get('reason', str(gate)))
                            else:
                                value = checker.verify(folder / 'candidate.rs')
                                write_json(folder / 'verification.json', value)
                                if value['error_type'] == 'verifier_error':
                                    raise RuntimeError('Verifier infrastructure failure; resume after fixing infrastructure')
                                result.update(success=value['success'], category='success' if value['success'] else value['error_type'],
                                    error=None if value['success'] else diagnostics(value), verification_seconds=value.get('seconds'))
                        result['previous_response'] = response['text']
                    write_json(folder / 'result.json', result)
                attempts.append({'proposal': n, **{k: v for k, v in result.items() if k != 'previous_response'}})
                if result['success']:
                    break
                history.append({'response': result.get('previous_response'), 'category': result['category'], 'error': result.get('error')})
            write_json(dest / 'task.json', {'id': task['id'], 'success': any(a['success'] for a in attempts), 'attempts': attempts})
            print(arm, task['id'], 'solved' if any(a['success'] for a in attempts) else 'failed', flush=True)
        report(root)


def report(root):
    plan = read_json(root / 'manifest.json')
    summaries, solved = {}, {}
    for arm in ARMS:
        rows = [read_json(root / arm / t['id'] / 'task.json') for t in plan['tasks'] if (root / arm / t['id'] / 'task.json').exists()]
        attempts = [a for r in rows for a in r['attempts']]
        solved[arm] = {r['id'] for r in rows if r['success']}
        summaries[arm] = {'expected': len(plan['tasks']), 'completed': len(rows), 'solved': len(solved[arm]),
            'through_proposal': {str(n): sum(any(a['success'] and a['proposal'] <= n for a in r['attempts']) for r in rows) for n in range(1, plan['proposals'] + 1)},
            'errors': dict(Counter(a['category'] for a in attempts)),
            'input_tokens': sum(a.get('input_tokens', 0) for a in attempts), 'output_tokens': sum(a.get('output_tokens', 0) for a in attempts),
            'inference_seconds': sum(a.get('inference_seconds', 0) for a in attempts)}
    result = {'scope': plan['scope'], 'model': plan['model'], 'summaries': summaries,
        'both': sorted(solved[ARMS[0]] & solved[ARMS[1]]), 'only_guided': sorted(solved[ARMS[1]] - solved[ARMS[0]]),
        'only_control': sorted(solved[ARMS[0]] - solved[ARMS[1]]),
        'complete': all(s['completed'] == s['expected'] for s in summaries.values())}
    write_json(root / 'comparison.json', result)
    lines = ['# Oracle action/location diagnostic', '', plan['scope'], '', '| Arm | Completed | Solved |', '|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{s['expected']} | {s['solved']} |")
    lines += ['', 'No solver internals in either arm. Reference code/replacements are never sent to the model.']
    write_text(root / 'comparison.md', '\n'.join(lines) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'run', 'report'])
    p.add_argument('--dataset', type=Path, default=Path('data/verusbench-guidance-v1'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--adapter', type=Path, help='Omit for the unfine-tuned base instruct model')
    p.add_argument('--proposals', type=int, choices=[1, 2, 3], default=3)
    args = p.parse_args()
    if args.command == 'report':
        report(args.output.resolve())
        return
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
