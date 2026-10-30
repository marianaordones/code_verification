"""Paired localized repairs of the saved shared VerusBench initial candidates."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import time

from .__main__ import run_lock
from .benchmark import load_tasks, CATEGORIES
from .inference import LocalVLLM, extract_code
from .integrity import IntegrityValidator, tokens
from .obligation import ObligationVerifier
from .prompts import ROOT
from .provenance import collect, file_hashes, tool_signature
from .storage import digest, read_json, write_json, write_text
from repair_study.regions_v2 import regions, apply_patch
from repair_study.relevance import source_context

ARMS = ('without_internals', 'with_internals')


def implementation():
    return file_hashes([*(ROOT / 'baseline').glob('*.py'), *(ROOT / 'solver_needs_study').glob('*.py'),
        *(ROOT / 'repair_study').glob('*.py'), *(ROOT / 'diagnostics').glob('*.py'),
        ROOT / 'prompts/v4/system.txt', ROOT / 'prompts/repair-study/local.txt',
        ROOT / 'prompts/verusbench-three-solver-info.txt',
        ROOT / 'prompts/verusbench-local-v2.txt'])


def validate(root):
    m = read_json(root / 'manifest.json')
    if m['implementation'] != implementation():
        raise ValueError('Code/prompts changed after preparation; use a new study directory')
    for path, expected in m['files'].items():
        if digest((root / path).read_bytes()) != expected:
            raise ValueError('Frozen input changed: ' + path)
    return m


def audit_sites(code):
    try:
        sites = regions(code)
        return sites, {'status': 'available' if sites else 'no_safe_sites',
            'site_count': len(sites), 'kinds': dict(Counter(s['kind'] for s in sites)),
            'scope': 'one region per response; no completeness claim; no support for arbitrary new lemma definitions or contract edits'}
    except ValueError as error:
        return [], {'status': 'region_parser_error', 'site_count': 0, 'error': str(error)}


def prepare(source, root):
    source, root = source.resolve(), root.resolve()
    if source == root or source in root.parents or root in source.parents:
        raise ValueError('Source and output must be separate directories')
    if (root / 'manifest.json').exists():
        m = validate(root)
        if m['source'] != str(source):
            raise ValueError('Another source already frozen')
        return
    previous = read_json(source / 'run.json')
    config = {**previous['config'], 'experiment': 'verusbench-local-v2-base24k-four-proposals', 'max_repairs': 3, 'max_attempts': 4, 'editor_version': 2,
              'internals_token_budget': 24576, 'max_quantifiers': 50, 'max_instances_each': 3,
              'max_queries': 3, 'replay_max_instances': 5, 'collect_inventory': False}
    config.pop('complement_token_budget', None)
    if (config['max_model_len'], config['max_tokens'], config['seed']) != (65536, 4096, 20261018):
        raise ValueError('Expected the completed64k three-arm VerusBench study')
    tasks = {t['id']: t for t in load_tasks(ROOT / 'data/manifest.json')}
    if len(tasks) != 150 or set(tasks) != {t['id'] for t in previous['tasks']}:
        raise ValueError('Expected exactly the same150 official tasks')
    rows = []
    for old in previous['tasks']:
        task = tasks[old['id']]
        if old['sha256'] != task['sha256']:
            raise ValueError('Original task hash differs: ' + task['id'])
        initial = source / 'shared' / task['id'] / 'attempt_00'
        request, response = read_json(initial / 'request.json'), read_json(initial / 'response.json')
        candidate = (initial / 'candidate.rs').read_text(encoding='utf-8')
        if request['input_sha256'] != task['sha256'] or candidate != extract_code(response['text'], config['enable_thinking']):
            raise ValueError('Saved shared candidate/request mismatch: ' + task['id'])
        verification, check, record = [read_json(initial / name) for name in ('verification.json', 'integrity.json', 'result.json')]
        if record['success'] != bool(verification['success'] and check['valid']):
            raise ValueError('Inconsistent saved initial success')
        sites, audit = audit_sites(candidate)
        status = ('initial_success' if record['success'] else ('initial_unparseable' if check.get('status') == 'unparseable' else
                   'initial_forbidden_change' if check.get('status') == 'invalid' else 'initial_integrity_error') if not check['valid'] else
                  'initial_verus_pass_integrity_conflict' if verification['success'] else
                  'eligible' if sites else 'editor_unavailable')
        folder = root / 'inputs' / task['id']
        shutil.copytree(initial, folder / 'initial', dirs_exist_ok=True)
        write_text(folder / 'candidate.rs', candidate)
        write_text(folder / 'original.rs', Path(task['file']).read_text(encoding='utf-8'))
        write_json(folder / 'verification.json', verification)
        write_json(folder / 'integrity.json', check)
        write_json(folder / 'editor-audit.json', {**audit, 'sites': sites})
        # Reuse only raw replay events of the SHARED initial candidate, never later repairs.
        saved = source / 'shared' / task['id'] / 'initial-feedback'
        reused = (saved / 'internals').exists()
        if reused:
            shutil.copytree(saved / 'internals', folder / 'initial/internals', dirs_exist_ok=True)
        row = {k: task[k] for k in ('id', 'category', 'sha256')}
        rows.append({**row, 'status': status, 'initial_integrity_status': check.get('status'), 'initial_editor': audit, 'saved_replay_events_available': reused})
    files = {str(p.relative_to(root)): digest(p.read_bytes()) for p in (root / 'inputs').rglob('*') if p.is_file()}
    write_json(root / 'manifest.json', {'source': str(source), 'source_run_sha256': digest((source / 'run.json').read_bytes()),
        'config': config, 'tasks': rows, 'files': files, 'implementation': implementation(),
        'tools': previous['tools'], 'solver_api': previous['solver_api'],
        'scope': 'three localized repair proposals after one frozen shared generation; edits-v2;  repair-only denominator excludes initial successes and explicit eligibility/editor exclusions'})
    write_json(root / 'selected_ids.json', {'all_ids': [r['id'] for r in rows], 'eligible_ids': [r['id'] for r in rows if r['status'] == 'eligible']})
    print('Prepared:', dict(Counter(r['status'] for r in rows)), flush=True)


def messages(original, code, verification, check, context, payload, progress, rejected=None, config=None):
    sites, audit = audit_sites(code)
    system = (ROOT / 'prompts/v4/system.txt').read_text(encoding='utf-8') + '\n' + (ROOT / 'prompts/verusbench-three-solver-info.txt').read_text(encoding='utf-8')
    system += '\n' + (ROOT / 'prompts/repair-study/local.txt').read_text(encoding='utf-8')
    system += '\n' + (ROOT / 'prompts/verusbench-local-v2.txt').read_text(encoding='utf-8')
    if (config or {}).get('loop_isolation_fixed'):
        system = system.replace('four total proposals', 'three total proposals').replace('at most three localized repair proposals', 'at most two localized repair proposals')
        system += '\n' + config['extra_system_prompt']
    user = '<original_program>\n' + original + '\n</original_program>\n<current_candidate>\n' + code + '\n</current_candidate>\n'
    user += '<verus_diagnostics>\n' + verification['stdout'] + '\n' + verification['stderr'] + '\n</verus_diagnostics>\n'
    for tag, value in [('integrity_diagnostics', check), ('source_failure_context', context), ('progress', progress), ('editable_sites', sites), ('editor_scope', audit)]:
        user += '<' + tag + '>\n' + json.dumps(value, ensure_ascii=False, indent=2) + '\n</' + tag + '>\n'
    if rejected is not None:
        user += '<rejected_edit>\n' + json.dumps(rejected, ensure_ascii=False, indent=2) + '\n</rejected_edit>\n'
    if payload and payload.get('queries'):
        user += '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>\n'
    user += 'Return exactly site_id and replacement JSON. One region per proposal; no full file. A missing site is an editor limitation, not proof impossibility.'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def feedback(folder, frozen, original, code, verification, check, progress, inference, config, initial=False, rejected=None):
    cache = folder / 'local-feedback.json'
    if cache.exists():
        return read_json(cache)
    from solver_needs_study.feedback import internals
    def builder(code, verification, action, context, payload, history, **kw):
        return messages(original, code, verification, check, context, payload, progress, rejected=rejected, config=config)
    if initial:
        shutil.copytree(frozen / 'initial/solver', folder / 'solver', dirs_exist_ok=True)
        if (frozen / 'initial/internals').exists():
            shutil.copytree(frozen / 'initial/internals', folder / 'internals', dirs_exist_ok=True)
    # Never read the old full-file feedback.json: package for the actual localized prompt.
    report = read_json(folder / 'solver/report.json')
    failed = [q for q in report['queries'] if q['result'] in ('sat', 'unknown')][:config['max_queries']]
    saved = initial and all((folder / 'internals' / q['id'] / 'process.json').exists() for q in failed)
    value = internals(folder, code, verification, {}, [], inference.tokenizer, config, replay=not saved, message_builder=builder)
    write_json(cache, value)
    return value


def proposal_status(edit_error, checked, verified):
    if edit_error:
        return 'edit_error'
    if checked.get('status') == 'unparseable':
        return 'unparseable'
    if not checked['valid']:
        if checked.get('status') != 'invalid':
            raise RuntimeError('Unknown integrity rejection; not classed as forbidden change')
        return 'forbidden_change'
    if verified.get('error_type') == 'syntax':
        return 'unparseable'
    return 'verified' if verified['success'] else 'proof_or_compilation_failure'


def run_case(root, arm, row, config, inference, verifier, integrity):
    output = root / arm / row['id']
    if (output / 'task.json').exists():
        return read_json(output / 'task.json')
    frozen = root / 'inputs' / row['id']
    original = (frozen / 'original.rs').read_text(encoding='utf-8')
    code = (frozen / 'candidate.rs').read_text(encoding='utf-8')
    verification, check = read_json(frozen / 'verification.json'), read_json(frozen / 'integrity.json')
    progress, records, rejected = '', [], None
    for index in range(1, config['max_repairs'] + 1):
        folder = output / f'repair_{index:02}'
        sites, audit = audit_sites(code)
        if not sites:
            result = {'id': row['id'], 'success': False, 'status': 'editor_unavailable', 'repairs': records, 'editor': audit}
            write_json(output / 'task.json', result)
            return result
        if (folder / 'result.json').exists():
            record = read_json(folder / 'result.json')
        else:
            started = time.perf_counter()
            context = source_context(code, verification)
            payload, exposure = None, None
            if arm == 'with_internals':
                evidence_folder = root / 'initial-feedback' / row['id'] if index == 1 else output / f'repair_{index-1:02}'
                if index > 1 and (evidence_folder / 'state-feedback/solver').exists():
                    evidence_folder = evidence_folder / 'state-feedback'
                value = feedback(evidence_folder, frozen, original, code, verification, check, progress, inference, config, initial=index == 1, rejected=rejected)
                payload, context = value['internals'], value['context']
                exposure = value
            prompt = messages(original, code, verification, check, context, payload, progress, rejected=rejected, config=config)
            common = messages(original, code, verification, check, context, None, progress, rejected=rejected, config=config)
            count = len(inference.tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True))
            if count + config['max_tokens'] > config['max_model_len']:
                raise ValueError('Localized prompt exceeds context; no source truncation')
            request = {'messages': prompt, 'seed': config['seed'] + index, 'parameters': config,
                'candidate_sha256': digest(code.encode()), 'offered_sites': sites, 'editor_audit': audit,
                'common_messages_sha256': digest(json.dumps(common, sort_keys=True).encode()),
                'prompt_tokens': count, 'headroom_after_output_reserve': config['max_model_len'] - config['max_tokens'] - count}
            if (folder / 'request.json').exists() and read_json(folder / 'request.json') != request:
                raise ValueError('Saved localized request changed')
            write_json(folder / 'request.json', request)
            write_json(folder / 'exposure.json', {'payload': payload, 'context': context, 'internals_exposed': bool(payload), 'metadata': exposure})
            response = read_json(folder / 'response.json') if (folder / 'response.json').exists() else inference.generate(prompt, config, request['seed'])
            write_json(folder / 'response.json', response)
            write_text(folder / 'response.txt', response['text'])
            if 'rendered_prompt' in response:
                write_text(folder / 'rendered_prompt.txt', response['rendered_prompt'])
            edit_error, region_id = None, None
            try:
                proposed, region_id = apply_patch(code, response['text'], sites)
            except (ValueError, KeyError, TypeError) as error:
                proposed, edit_error = code, str(error)
            write_text(folder / 'candidate.rs', proposed)
            checked = integrity.validate(frozen / 'original.rs', folder / 'candidate.rs')
            verified = verifier.verify(folder / 'candidate.rs')
            write_json(folder / 'verification.json', verified)
            write_json(folder / 'integrity.json', checked)
            if verified.get('error_type') == 'verifier_error' or checked.get('status') == 'checker_error':
                raise RuntimeError('Verifier/integrity infrastructure failure; proposal not finalized')
            # Rejected edits do not poison the next candidate. Still consume one proposal.
            status = proposal_status(edit_error, checked, verified)
            retain = status not in ('edit_error', 'unparseable', 'forbidden_change')
            write_text(folder / 'state.rs', proposed if retain else code)
            write_json(folder / 'state-verification.json', verified if retain else verification)
            write_json(folder / 'state-integrity.json', checked if retain else check)
            # Next replay must match the retained program, not an integrity-rejected edit.
            if not retain:
                origin = frozen / 'initial/solver'
                if index > 1:
                    previous = output / f'repair_{index-1:02}'
                    origin = previous / 'state-feedback/solver' if (previous / 'state-feedback/solver').exists() else previous / 'solver'
                if origin.exists():
                    shutil.copytree(origin, folder / 'retained-solver', dirs_exist_ok=True)
            rejection = None
            if not retain:
                rejection = {'overall_proposal': index + 1, 'classification': status,
                    'response': response['text'], 'edit_error': edit_error,
                    'integrity': checked, 'verus_diagnostics': {'stdout': verified['stdout'], 'stderr': verified['stderr']},
                    'state': 'Rejected edit was NOT applied. current_candidate is the previous retained program.'}
            write_json(folder / 'rejected-edit.json', rejection)
            try:
                unchanged = tokens(proposed) == tokens(code)
            except ValueError:
                unchanged = proposed == code
            record = {'repair': index, 'overall_proposal': index + 1, 'success': status == 'verified', 'status': status,
                'edit_error': edit_error, 'region_id': region_id, 'editor_site_count': len(sites),
                'error_type': verified['error_type'], 'integrity_status': checked.get('status', 'valid' if checked['valid'] else 'invalid'), 'integrity_valid': checked['valid'], 'retained_proposal': retain,
                'unchanged': unchanged, 'input_tokens': response['input_tokens'], 'output_tokens': response['output_tokens'],
                'truncated': response['truncated'], 'internals_exposed': bool(payload),
                'inference_seconds': response['inference_seconds'], 'processing_seconds': time.perf_counter() - started}
            write_json(folder / 'result.json', record)
        records.append(record)
        if record['success']:
            break
        code = (folder / 'state.rs').read_text(encoding='utf-8')
        verification, check = read_json(folder / 'state-verification.json'), read_json(folder / 'state-integrity.json')
        rejected = read_json(folder / 'rejected-edit.json')
        progress = 'Previous proposal: ' + record['status'] + '. ' + (record.get('edit_error') or 'Address current diagnostics; use one offered region.')
        if not record['retained_proposal'] and (folder / 'retained-solver').exists():
            # Keep proposed solver output as audit evidence; use a separate folder for retained state replay.
            state = folder / 'state-feedback'
            shutil.copytree(folder / 'retained-solver', state / 'solver', dirs_exist_ok=True)
    result = {'id': row['id'], 'success': any(r['success'] for r in records), 'status': 'completed', 'repairs': records}
    write_json(output / 'task.json', result)
    print(arm, row['id'], result['success'], flush=True)
    return result



def compare(root):
    m = validate(root)
    rows, summaries = [], {}
    for task in m['tasks']:
        row = dict(task)
        for arm in ARMS:
            path = root / arm / task['id'] / 'task.json'
            row[arm] = read_json(path) if path.exists() else None
        row['first_pair_valid'] = None
        if task['status'] == 'eligible':
            requests = [root / a / task['id'] / 'repair_01/request.json' for a in ARMS]
            if all(p.exists() for p in requests):
                a, b = map(read_json, requests)
                expected = digest((root / 'inputs' / task['id'] / 'candidate.rs').read_bytes())
                row['first_pair_valid'] = (a['candidate_sha256'] == b['candidate_sha256'] == expected and
                    a['common_messages_sha256'] == b['common_messages_sha256'] and a['seed'] == b['seed'] and
                    a['parameters'] == b['parameters'] and a['offered_sites'] == b['offered_sites'])
        rows.append(row)
    eligible = [r for r in rows if r['status'] == 'eligible']
    initial_successes = sum(r['status'] == 'initial_success' for r in rows)
    for arm in ARMS:
        tasks = [r[arm] for r in eligible if r[arm] is not None]
        records = [a for t in tasks for a in t['repairs']]
        requests = [read_json(p) for p in (root / arm).glob('*/repair_*/request.json')]
        s = {'eligible': len(eligible), 'completed': len(tasks), 'repaired': sum(t['success'] for t in tasks),
            'repaired_by_repair': {str(k): sum(any(a['success'] and a['repair'] <= k for a in t['repairs']) for t in tasks) for k in range(1, m['config']['max_repairs'] + 1)},
            'initial_successes': initial_successes,
            'known_successes_by_overall_proposal': {'1': initial_successes, **{str(k + 1): initial_successes + sum(any(a['success'] and a['repair'] <= k for a in t['repairs']) for t in tasks) for k in range(1, m['config']['max_repairs'] + 1)}},
            'known_full_benchmark_successes': initial_successes + sum(t['success'] for t in tasks),
            'editor_unavailable_after_edit': sum(t['status'] == 'editor_unavailable' for t in tasks),
            'unparseable': sum(r['status'] == 'unparseable' for r in records),
            'forbidden_changes': sum(r['status'] == 'forbidden_change' for r in records),
            'integrity_statuses': dict(Counter(r['integrity_status'] for r in records)),
            'proposal_statuses': dict(Counter(r['status'] for r in records)),
            'edit_error_reasons': dict(Counter(r['edit_error'] for r in records if r['edit_error'])),
            'unchanged': sum(r['unchanged'] for r in records), 'proposals': len(records),
            'internals_exposed': sum(r['internals_exposed'] for r in records),
            'input_tokens': sum(r['input_tokens'] for r in records), 'output_tokens': sum(r['output_tokens'] for r in records),
            'truncated': sum(r['truncated'] for r in records), 'context_violations': sum(r['headroom_after_output_reserve'] < 0 for r in requests),
            'minimum_context_headroom': min((r['headroom_after_output_reserve'] for r in requests), default=None),
            'by_category': {c: {'eligible': sum(r['category'] == c for r in eligible),
                'repaired': sum(r['category'] == c and r[arm] is not None and r[arm]['success'] for r in eligible)} for c in CATEGORIES},
            'missing': [r['id'] for r in eligible if r[arm] is None]}
        summaries[arm] = s
        write_json(root / arm / 'summary.json', s)
    report = {'summaries': summaries, 'paired': rows, 'selection_statuses': dict(Counter(r['status'] for r in rows)),
        'complete': all(not s['missing'] for s in summaries.values()),
        'first_pairs_valid': all(r['first_pair_valid'] is True for r in eligible),
        'with_only': [r['id'] for r in eligible if r[ARMS[1]] and r[ARMS[0]] and r[ARMS[1]]['success'] and not r[ARMS[0]]['success']],
        'without_only': [r['id'] for r in eligible if r[ARMS[1]] and r[ARMS[0]] and r[ARMS[0]]['success'] and not r[ARMS[1]]['success']],
        'scope': m['scope']}
    write_json(root / 'comparison.json', report)
    lines = ['# VerusBench: localized repair ablation', '', m['scope'], '',
        'Selection: ' + str(report['selection_statuses']), '',
        '| Arm | Completed eligible | After repair 1 | After repair 2 | After repair 3 | Edit errors | Unparseable | Forbidden changes |', '|---|---|---|---|---|---|---|---|']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{s['eligible']} | {s['repaired_by_repair']['1']} | {s['repaired_by_repair']['2']} | {s['repaired_by_repair']['3']} | {s['proposal_statuses'].get('edit_error', 0)} | {s['unparseable']} | {s['forbidden_changes']} |")
    lines += ['', f"Complete: {report['complete']}; initial pairs valid: {report['first_pairs_valid']}",
        'Initial successes and editor/integrity exclusions are reported separately. Editor coverage is not proof impossibility.',
        'One saved initial proposal + three new localized proposals = four total proposals. No new initial generation.']
    write_text(root / 'comparison.md', '\n'.join(lines))
    print(root / 'comparison.md', flush=True)
    return report


def run(root):
    m = validate(root)
    config = dict(m['config'])
    for name, env in [('verus', 'VERUS_BIN'), ('z3', 'Z3_BIN'), ('lynette', 'LYNETTE_BIN')]:
        config[name] = os.environ.get(env, name)
    identity = collect(config)
    if m['tools'] != {n: tool_signature(identity[n]) for n in ('verus', 'z3', 'lynette')} or m['solver_api'] != identity['solver_api']:
        raise ValueError('Verus/Lynette/Z3 differ from saved initial generation')
    pending = [r for r in m['tasks'] if r['status'] == 'eligible' and any(not (root / a / r['id'] / 'task.json').exists() for a in ARMS)]
    if not pending:
        report = compare(root)
        return 0 if report['complete'] and report['first_pairs_valid'] else 1
    runtime = {'versions': identity['versions'], 'gpu': identity['gpu'], 'manifest_sha256': digest((root / 'manifest.json').read_bytes())}
    if (root / 'runtime.json').exists() and read_json(root / 'runtime.json') != runtime:
        raise ValueError('Runtime/GPU class changed')
    write_json(root / 'runtime.json', runtime)
    os.environ['VERUS_Z3_PATH'] = identity['z3']['path']
    engine_start = time.perf_counter()
    inference = LocalVLLM(config)
    inference.tokenizer.model_max_length = config['max_model_len']
    session = {'model_load_seconds': time.perf_counter() - engine_start, 'provenance': identity}
    verifier = ObligationVerifier(identity['verus']['path'], identity['z3']['path'], config['verification_timeout'])
    integrity = IntegrityValidator(identity['lynette']['path'])
    try:
        for i, row in enumerate(pending):
            for arm in ARMS if i % 2 == 0 else ARMS[::-1]:
                try:
                    run_case(root, arm, row, m['config'], inference, verifier, integrity)
                except Exception as error:
                    write_json(root / arm / row['id'] / 'infrastructure-error.json', {'error': str(error), 'type': type(error).__name__})
                    print(arm, row['id'], 'infrastructure error:', error, flush=True)
    finally:
        session['wall_seconds_including_load'] = time.perf_counter() - engine_start
        write_json(root / ('session-' + str(time.time_ns()) + '.json'), session)
        report = compare(root)
    return 0 if report['complete'] and report['first_pairs_valid'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'compare'))
    parser.add_argument('--source', type=Path, default=Path('results/verusbench-qwen14b-three-arms/seed-20261018'))
    parser.add_argument('--output', type=Path, default=Path('results/verusbench-local-v2-base24k-four/seed-20261018'))
    args = parser.parse_args()
    root = args.output.resolve()
    with run_lock(root):
        if args.command == 'prepare':
            prepare(args.source, root)
            return 0
        if args.command == 'compare':
            compare(root)
            return 0
        return run(root)

if __name__ == '__main__':
    raise SystemExit(main())
