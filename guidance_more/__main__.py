"""Build reference-derived proposals locally; validate and select new examples on Slurm."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
from zipfile import ZipFile

from baseline.integrity import tokens
from baseline.storage import read_json, write_json, write_text
from guidance_study.editor import apply, regions
from guidance_study.evaluate import prompt
from localized_sft.convert import sha


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in (root / 'tasks').rglob('*') if p.is_file()}


def build(archive, previous_subset, references, benchmark, output):
    if output.exists():
        raise ValueError('Use a new pool directory')
    excluded = {t['id'] for t in read_json(previous_subset / 'manifest.json')['tasks']}
    official = {t['id']: t for t in read_json(benchmark)['tasks']}
    tasks, audit = [], []
    with ZipFile(archive) as z:
        previous = json.loads(z.read('verusbench/manifest.json'))
        for task in previous['tasks']:
            key = task['id']
            if task['status'] != 'eligible' or key in excluded:
                continue
            if '/' in key or '\\' in key or key in ('.', '..'):
                raise ValueError('Unsafe task ID')
            prefix = f'verusbench/inputs/{key}/'
            for name in ('candidate.rs', 'original.rs', 'verification.json'):
                raw = z.read(prefix + name)
                if hashlib.sha256(raw).hexdigest() != previous['frozen_files']['inputs/' + key + '/' + name]:
                    raise ValueError('Frozen source hash mismatch: ' + key)
            code = z.read(prefix + 'candidate.rs').decode('utf-8')
            reference = references / task['category'] / 'verified' / Path(official[key]['path']).name
            if not reference.exists():
                audit.append({'id': key, 'reason': 'missing_official_reference'})
                continue
            try:
                offered = regions(code)
                before = [s for s in offered if s['kind'] == 'loop_invariants']
                reference_code = reference.read_text(encoding='utf-8')
                after = [s for s in regions(reference_code) if s['kind'] == 'loop_invariants']
                if not before or len(before) != len(after):
                    raise ValueError('Loop-list correspondence unavailable')
                edits = [{'site_id': a['id'], 'replacement': b['existing_text']}
                         for a, b in zip(before, after) if tokens(a['existing_text']) != tokens(b['existing_text'])]
                if not edits:
                    raise ValueError('No changed invariant lists')
                action = {'edits': edits}
                target = apply(code, action, offered)
            except ValueError as error:
                audit.append({'id': key, 'reason': str(error)})
                continue
            folder = output / 'tasks' / key
            decisions = [{'site_id': e['site_id'], 'action': 'loop_invariants'} for e in edits]
            write_text(folder / 'candidate.rs', code)
            write_text(folder / 'original.rs', z.read(prefix + 'original.rs').decode('utf-8'))
            write_json(folder / 'verification.json', json.loads(z.read(prefix + 'verification.json')))
            write_json(folder / 'editable-sites.json', offered)
            write_text(folder / 'reference/candidate.rs', target)
            write_json(folder / 'reference/action.json', action)
            write_json(folder / 'reference/decisions.json', decisions)
            write_json(folder / 'reference/provenance.json', {'official_source': str(reference),
                'official_source_sha256': sha(reference), 'status': 'unverified_reference_derived_proposal',
                'method': 'Transfer invariant lists in loop order only; preserve all other candidate code. '
                          'No copied main function, decreases clause, contract or solver option.'})
            tasks.append({'id': key, 'category': task['category'], 'decisions': decisions,
                          'reference_origin': 'official_invariant_lists', 'revalidation_required': True})
    if not tasks:
        raise ValueError('No additional candidates')
    write_json(output / 'manifest.json', {'schema': 'guidance-additional-provisional-v1',
        'source_archive_sha256': sha(archive), 'source_tools': previous['tools'], 'tasks': tasks,
        'files': inventory(output), 'excluded_previous_ids': sorted(excluded), 'audit': audit,
        'status': 'PROVISIONAL: no new target is certified; run validate before inference'})
    write_text(output / 'report.md', '# Additional provisional oracle pool\n\nCandidates: ' + str(len(tasks)) +
        '\n\nPrevious IDs excluded: ' + str(len(excluded)) +
        '\n\nReference-derived invariants only. Targets require cluster validation. No lemma cases are claimed.\n')
    print('Built', len(tasks), 'additional proposals, excluding', len(excluded), 'previous tasks.', flush=True)


def order(tasks, seed):
    rng, buckets = random.Random(seed), {}
    for task in sorted(tasks, key=lambda t: t['id']):
        buckets.setdefault(task['category'], []).append(task)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    result = []
    while any(buckets.values()):
        for category in sorted(buckets):
            if buckets[category]:
                result.append(buckets[category].pop())
    return result


def validate(pool, output, count, seed, tokenizer=None):
    import os
    from safe_internals.validation import preservation
    from sft_eval.__main__ import tool_hashes, verifier
    source = read_json(pool / 'manifest.json')
    if source['schema'] != 'guidance-additional-provisional-v1':
        raise ValueError('Expected a provisional additional-example pool')
    for name, expected in source['files'].items():
        if sha(pool / name) != expected:
            raise ValueError('Pool changed: ' + name)
    tools = tool_hashes()
    if tools != source['source_tools']:
        raise ValueError('Use the source VerusBench tool versions')
    cache = output.parent / (output.name + '-validation')
    plan = {'pool_manifest_sha256': sha(pool / 'manifest.json'), 'tools': tools, 'count': count, 'seed': seed,
            'preparation_code_sha256': sha(Path(__file__))}
    if (cache / 'plan.json').exists() and read_json(cache / 'plan.json') != plan:
        raise ValueError('Validation settings/code changed; use a new output')
    write_json(cache / 'plan.json', plan)
    if (output / 'manifest.json').exists():
        saved = read_json(output / 'manifest.json')
        if saved['validation_plan'] != plan:
            raise ValueError('Selection settings changed')
        for name, expected in saved['files'].items():
            if sha(output / name) != expected:
                raise ValueError('Selected subset changed: ' + name)
        print('Validated subset already complete:', output, flush=True)
        return
    if tokenizer is None:
        from safe_internals.pipeline import load_tokenizer
        tokenizer, _ = load_tokenizer()
    checker, selected, audit = verifier('verusbench'), [], []
    for task in order(source['tasks'], seed):
        key = task['id']
        if key in source['excluded_previous_ids']:
            raise ValueError('Repeated old task: ' + key)
        src, record = pool / 'tasks' / key, {'id': key}
        code = (src / 'candidate.rs').read_text(encoding='utf-8')
        original = (src / 'original.rs').read_text(encoding='utf-8')
        target = (src / 'reference/candidate.rs').read_text(encoding='utf-8')
        action = read_json(src / 'reference/action.json')
        offered = regions(code)
        if tokens(apply(code, action, offered)) != tokens(target):
            raise ValueError('Reference reconstruction mismatch: ' + key)
        request = prompt(code, '', offered, task['decisions'])
        answer = json.dumps(action, ensure_ascii=False)
        if len(tokenizer.encode(answer, add_special_tokens=False)) + 4 > 4096 or len(tokenizer.apply_chat_template(request, tokenize=True, add_generation_prompt=True)) + 4096 > 32768:
            record.update(selected=False, reason='reference_or_base_prompt_token_budget')
            audit.append(record)
            continue
        valid = True
        for label, content in [('input', code), ('reference', target)]:
            dest = cache / key / label
            if not (dest / 'verification.json').exists():
                write_text(dest / 'candidate.rs', content)
                value = checker.verify(dest / 'candidate.rs')
                if value['error_type'] == 'verifier_error':
                    raise RuntimeError('Verifier infrastructure failure: ' + key)
                write_json(dest / 'verification.json', value)
            value = read_json(dest / 'verification.json')
            if not (dest / 'integrity.json').exists() or read_json(dest / 'integrity.json')['status'] == 'checker_error':
                write_json(dest / 'integrity.json', preservation(original, content, dest, os.environ['LYNETTE_BIN']))
            gate = read_json(dest / 'integrity.json')
            if gate['status'] == 'checker_error':
                raise RuntimeError('Integrity checker infrastructure failure: ' + key)
            record[label] = {'success': value['success'], 'error_type': value['error_type'], 'integrity': gate['status']}
            valid &= value['success'] == (label == 'reference') and gate['status'] == 'valid'
        # Check the actual revalidated diagnostics, not an empty approximation.
        checked = read_json(cache / key / 'input/verification.json')
        request = prompt(code, checked.get('stdout', '') + '\n' + checked.get('stderr', ''), offered, task['decisions'])
        if len(tokenizer.apply_chat_template(request, tokenize=True, add_generation_prompt=True)) + 4096 > 32768:
            valid = False
            record['reason'] = 'diagnostic_prompt_token_budget'
        record['selected'] = bool(valid)
        audit.append(record)
        write_json(cache / 'audit.json', audit)
        print(key, 'selected' if valid else 'excluded', record, flush=True)
        if valid:
            selected.append(task)
        if len(selected) >= count:
            break
    if not selected:
        raise ValueError('No validated targets; inspect the validation audit')
    for task in selected:
        dest = output / 'tasks' / task['id']
        shutil.copytree(pool / 'tasks' / task['id'], dest, dirs_exist_ok=True)
        for label, relative in [('input', ''), ('reference', 'reference')]:
            for name in ('verification.json', 'integrity.json'):
                shutil.copy2(cache / task['id'] / label / name, dest / relative / name)
    actions = Counter(d['action'] for t in selected for d in t['decisions'])
    result = {'schema': 'verusbench-oracle-guidance-v1', 'validation_plan': plan,
        'requested': count, 'tasks': selected, 'source_tools': tools, 'files': inventory(output),
        'excluded_previous_ids': source['excluded_previous_ids'], 'actions': dict(actions), 'audit': audit,
        'reference_status': 'Validated on cluster: input fails, target verifies, both preserve original; reference actions reconstruct target.',
        'selection_bias': 'Reference-derived invariant-repairable diagnostic subset, not representative VerusBench rates.'}
    write_json(output / 'manifest.json', result)
    write_json(output / 'selected_ids.json', [t['id'] for t in selected])
    write_text(output / 'report.md', '# Additional validated oracle examples\n\nRequested: ' + str(count) +
        '\n\nSelected: ' + str(len(selected)) + '\n\nActions: ' + str(dict(actions)) +
        '\n\nMulti-region plans: ' + str(sum(len(t['decisions']) > 1 for t in selected)) +
        '\n\nPrevious seven IDs excluded. Selection is seeded category round-robin, with no LLM inference.\n\n' +
        result['selection_bias'] + '\n')
    print('Validated', len(selected), '/', count, 'additional examples:', output, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--archive', type=Path, required=True)
    b.add_argument('--previous', type=Path, default=Path('data/verusbench-guidance-v1'))
    b.add_argument('--references', type=Path, default=Path('references/verus-proof-synthesis/benchmarks/Verus-Bench'))
    b.add_argument('--benchmark', type=Path, default=Path('data/manifest.json'))
    b.add_argument('--output', type=Path, default=Path('data/verusbench-guidance-more-pool-v1'))
    v = sub.add_parser('validate')
    v.add_argument('--pool', type=Path, default=Path('data/verusbench-guidance-more-pool-v1'))
    v.add_argument('--output', type=Path, default=Path('data/verusbench-guidance-more30-v1'))
    v.add_argument('--count', type=int, default=30)
    v.add_argument('--seed', type=int, default=20261018)
    args = p.parse_args()
    if args.command == 'build':
        build(args.archive, args.previous, args.references, args.benchmark, args.output)
    else:
        if args.count < 1:
            p.error('--count must be positive')
        import fcntl
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with (args.output.parent / (args.output.name + '.lock')).open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            validate(args.pool, args.output, args.count, args.seed)


if __name__ == '__main__':
    main()
