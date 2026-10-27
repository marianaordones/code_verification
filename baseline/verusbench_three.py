"""Full VerusBench: shared first proposal, then three feedback conditions."""
import argparse
import json
import os
import shutil
import time
from itertools import combinations
from pathlib import Path

from .__main__ import run_lock
from .benchmark import load_tasks, CATEGORIES
from .feedback import ConventionalFeedbackProvider
from .inference import LocalVLLM
from .integrity import IntegrityValidator
from .obligation import ObligationVerifier
from .prompts import ROOT, build_messages
from .provenance import collect, file_hashes, tool_signature
from .runner import run_task
from .storage import digest, read_json, write_json, write_text

ARMS = ('no_internals', 'base24k', 'base24k_complement12k')
CONFIG = ROOT / 'configs/verusbench-qwen14b-three-arms.json'


def messages(code, feedback=None, version='v4', original=None):
    result = build_messages(code, feedback, 'v4', original=original)
    result[0]['content'] += '\n' + (ROOT / 'prompts/verusbench-three-solver-info.txt').read_text(encoding='utf-8')
    result[0]['content'] += '\n' + (ROOT / 'prompts/solver-needs/complement.txt').read_text(encoding='utf-8')
    return result


class Provider(ConventionalFeedbackProvider):
    build_messages = staticmethod(messages)

    def __init__(self, arm, shared):
        self.arm, self.shared = arm, shared

    def validate_prompt(self, prompt, inference, config):
        tokens = len(inference.tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True))
        headroom = config['max_model_len'] - config['max_tokens'] - tokens
        if headroom < 0:
            raise ValueError('Actual prompt exceeds context; no truncation')
        return {'prompt_tokens': tokens, 'headroom_after_output_reserve': headroom}

    def enrich(self, folder, current, conventional, original, inference, config):
        if self.arm == 'no_internals':
            return conventional
        from solver_needs_study.feedback import internals
        initial = folder.name == 'attempt_00'
        destination = self.shared / 'initial-feedback' if initial else folder
        if initial and not (destination / 'solver/report.json').exists():
            shutil.copytree(folder / 'solver', destination / 'solver', dirs_exist_ok=True)
        cfg = dict(config)
        if not initial and self.arm == 'base24k':
            cfg.pop('complement_token_budget')
        def builder(code, verification, action, context, payload, history, config=None, complement=None, advanced=None):
            extra = conventional
            if payload and payload.get('queries'):
                extra += '\n<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>'
            if complement:
                extra += '\n<complementary_internals>\n' + json.dumps(complement, ensure_ascii=False, indent=2) + '\n</complementary_internals>'
            return messages(code, extra, original=original)
        started = time.perf_counter()
        value = internals(destination, current, read_json(folder / 'verification.json'), {}, [],
                          inference.tokenizer, cfg, message_builder=builder)
        payload = value.get('internals')
        comp = value.get('complement') if self.arm == 'base24k_complement12k' else None
        prompt = builder(current, {}, {}, {}, payload, [], complement=comp)
        tokens = len(inference.tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True))
        if tokens + config['max_tokens'] > config['max_model_len']:
            raise ValueError('Actual repair prompt exceeds context; no truncation')
        write_json(folder / 'exposure.json', {'arm': self.arm, 'base': payload, 'complement': comp,
            'prompt_tokens': tokens, 'output_reserve': config['max_tokens'],
            'headroom': config['max_model_len'] - config['max_tokens'] - tokens,
            'scope': 'diagnostic replay, not original search', 'seconds': time.perf_counter() - started})
        # Runner passes this text through the exact same message builder.
        return conventional + (
            '\n<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>' if payload and payload.get('queries') else '') + (
            '\n<complementary_internals>\n' + json.dumps(comp, ensure_ascii=False, indent=2) + '\n</complementary_internals>' if comp else '')


def run_arm(task, arm, config, root, inference, verifier, integrity):
    shared = root / 'shared' / task['id']
    target = root / arm / task['id'] / 'attempt_00'
    if not (target / 'result.json').exists():
        shutil.copytree(shared / 'attempt_00', target, dirs_exist_ok=True)
    return run_task(task, config, root / arm, inference, verifier, integrity, Provider(arm, shared))


def compare(root):
    manifest = read_json(root / 'run.json')
    summaries, rows = {}, []
    for task in manifest['tasks']:
        key = task['id']
        row = {'id': key, 'category': task['category']}
        expected = root / 'shared' / key / 'attempt_00'
        valid = True
        for arm in ARMS:
            folder = root / arm / key
            row[arm] = read_json(folder / 'task.json') if (folder / 'task.json').exists() else None
            for name in ('request.json', 'response.json', 'candidate.rs', 'verification.json', 'integrity.json', 'result.json'):
                a, b = expected / name, folder / 'attempt_00' / name
                valid = valid and a.exists() and b.exists() and digest(a.read_bytes()) == digest(b.read_bytes())
        row['shared_first_valid'] = valid
        rows.append(row)
    for arm in ARMS:
        tasks = [r[arm] for r in rows if r[arm] is not None]
        attempts = [a for t in tasks for a in t['attempts']]
        requests = [read_json(p) for p in (root / arm).glob('*/attempt_*/request.json')]
        exposures = [read_json(p) for p in (root / arm).glob('*/attempt_*/exposure.json')]
        summaries[arm] = {'context_violations': sum(r['headroom_after_output_reserve'] < 0 for r in requests),
            'minimum_context_headroom': min((r['headroom_after_output_reserve'] for r in requests), default=None),
            'feedback_seconds': sum(e.get('seconds', 0) for e in exposures),
            'base_exposed_feedbacks': sum(bool(e.get('base')) for e in exposures),
            'complement_exposed_feedbacks': sum(bool(e.get('complement')) for e in exposures),
            'completed': len(tasks), 'expected': len(rows), 'solved': sum(t['success'] for t in tasks),
            'solved_by_proposal': {str(k): sum(t['first_success'] is not None and t['first_success'] < k for t in tasks) for k in (1, 2, 3)},
            'by_category': {c: sum(r['category'] == c and r[arm] is not None and r[arm]['success'] for r in rows) for c in CATEGORIES},
            'input_tokens': sum(a['input_tokens'] for a in attempts), 'output_tokens': sum(a['output_tokens'] for a in attempts),
            'truncated': sum(a['truncated'] for a in attempts), 'errors': {},
            'missing': [r['id'] for r in rows if r[arm] is None]}
        for a in attempts:
            label = str(a['error_type'])
            summaries[arm]['errors'][label] = summaries[arm]['errors'].get(label, 0) + 1
        write_json(root / arm / 'summary.json', summaries[arm])
    pairwise = {a + '_vs_' + b: {'a_only': [r['id'] for r in rows if r[a] and r[b] and r[a]['success'] and not r[b]['success']],
        'b_only': [r['id'] for r in rows if r[a] and r[b] and r[b]['success'] and not r[a]['success']]} for a, b in combinations(ARMS, 2)}
    report = {'summaries': summaries, 'paired': rows, 'pairwise': pairwise,
        'complete': all(not s['missing'] for s in summaries.values()), 'shared_first_valid': all(r['shared_first_valid'] for r in rows),
        'cost_scope': 'Arm totals include the same shared proposal for comparability; it was executed once. Do not sum these as physical cost.'}
    write_json(root / 'comparison.json', report)
    lines = ['# VerusBench: three feedback arms', '', '| Arm | Completed | Through 1 | Through 2 | Through 3 |', '|---|---|---|---|---|']
    for arm, s in summaries.items():
        curve = s['solved_by_proposal']
        lines.append(f"| {arm} | {s['completed']}/{s['expected']} | {curve['1']} | {curve['2']} | {curve['3']} |")
    lines += ['', '| Category | None | Base24k | Base24k+12k |', '|---|---|---|---|']
    for c in CATEGORIES:
        lines.append('| ' + c + ' | ' + ' | '.join(str(summaries[a]['by_category'][c]) for a in ARMS) + ' |')
    lines += ['', f"Complete: {report['complete']}; identical first proposals: {report['shared_first_valid']}", report['cost_scope']]
    write_text(root / 'comparison.md', '\n'.join(lines))
    print(root / 'comparison.md', flush=True)
    return report


def run(root, config_path):
    config = read_json(config_path)
    if (config['task_count'], config['max_repairs'], config['max_model_len'], config['max_tokens'], config['internals_token_budget'],
        config['complement_token_budget'], config['max_quantifiers'], config['max_instances_each']) != (150, 2, 65536, 4096, 24576, 12288, 50, 3):
        raise ValueError('Unexpected three-arm protocol')
    for name in ('verus', 'z3', 'lynette'):
        config[name] = os.environ.get({'verus': 'VERUS_BIN', 'z3': 'Z3_BIN', 'lynette': 'LYNETTE_BIN'}[name], config[name])
    tasks = sorted(load_tasks(ROOT / 'data/manifest.json'), key=lambda t: t['id'])
    if len(tasks) != 150 or {c: sum(t['category'] == c for t in tasks) for c in CATEGORIES} != CATEGORIES:
        raise ValueError('Expected all150 official tasks')
    provenance = collect(config)
    os.environ['VERUS_Z3_PATH'] = provenance['z3']['path']
    frozen_config = {**config, **{n: 'sha256:' + provenance[n]['sha256'] for n in ('verus', 'z3', 'lynette')}}
    sources = file_hashes([*(ROOT / 'solver_needs_study').glob('*.py'), *(ROOT / 'diagnostics').glob('*.py'),
        ROOT / 'prompts/verusbench-three-solver-info.txt', ROOT / 'repair_study/worker.py', ROOT / 'repair_study/relevance.py', ROOT / 'prompts/solver-needs/complement.txt', config_path])
    stable = {'config': frozen_config, 'tasks': [{k: v for k, v in t.items() if k != 'file'} for t in tasks],
        'tools': {n: tool_signature(provenance[n]) for n in ('verus', 'z3', 'lynette')},
        'sources': sources, 'provenance_sources': provenance['sources'], 'prompts': file_hashes((ROOT / 'prompts/v4').glob('*.txt')),
        'versions': provenance['versions'], 'solver_api': provenance['solver_api'], 'gpu': provenance['gpu']}
    fingerprint = digest(json.dumps(stable, sort_keys=True).encode())
    with run_lock(root):
        if (root / 'run.json').exists() and read_json(root / 'run.json')['fingerprint'] != fingerprint:
            raise ValueError('Code/config/tools/inputs changed; use a new output directory')
        write_json(root / 'run.json', {**stable, 'fingerprint': fingerprint, 'provenance': provenance})
        write_json(root / 'selected_ids.json', {'ids': [t['id'] for t in tasks]})
        inference = LocalVLLM(config)
        verifier = ObligationVerifier(provenance['verus']['path'], provenance['z3']['path'], config['verification_timeout'])
        integrity = IntegrityValidator(provenance['lynette']['path'])
        started = time.perf_counter()
        try:
            for index, task in enumerate(tasks):
                try:
                    shared_root = root / 'shared'
                    if not (shared_root / task['id'] / 'task.json').exists():
                        run_task(task, frozen_config, shared_root, inference, verifier, integrity, Provider('no_internals', shared_root / task['id']), max_proposals=1)
                    for arm in ARMS[index % 3:] + ARMS[:index % 3]:
                        run_arm(task, arm, frozen_config, root, inference, verifier, integrity)
                        print(arm, task['id'], flush=True)
                except Exception as error:
                    write_json(root / 'errors' / (task['id'] + '.json'), {'error': str(error), 'type': type(error).__name__})
                    print(task['id'], 'infrastructure error:', error, flush=True)
        finally:
            write_json(root / ('session-' + str(time.time_ns()) + '.json'), {'wall_seconds_after_model_load': time.perf_counter() - started})
            report = compare(root)
        return 0 if report['complete'] and report['shared_first_valid'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'compare'))
    parser.add_argument('--output', type=Path, default=Path('results/verusbench-qwen14b-three-arms/seed-20261018'))
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    return run(args.output.resolve(), args.config.resolve()) if args.command == 'run' else (compare(args.output.resolve()) and 0)

if __name__ == '__main__':
    raise SystemExit(main())
