"""Paired Qwen repair of essential Verus assertions from Identifying What the Solver Needs."""
import argparse
from collections import Counter
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

from baseline.__main__ import run_lock
from baseline.inference import LocalVLLM, model_identity, prepare_model
from baseline.integrity import tokens
from baseline.prompts import ROOT
from baseline.provenance import command, file_hashes, tool_identity, tool_signature
from baseline.storage import digest, read_json, write_json, write_text
from diagnostics.z3_internals import api_identity
from .actions import EMPTY, RESPONSE_POLICY, parse_response, render
from .data import LABELS, SELECTION, selected_cases, split_task
from .download import REVISION, SOURCE, VERUS_VERSION, source
from .feedback import ARMS, control_feedback, fits, internals, messages
from .verify import StudyVerifier


DEFAULT_CONFIG = ROOT / 'configs/solver-needs-qwen14b.json'


def configuration(path=DEFAULT_CONFIG):
    config = read_json(path)
    if config.get('provider') == 'claude_code':
        from .claude_code import validate_config
        validate_config(config)
        return config
    model_identity(config)
    advanced = bool(config.get('advanced_token_budget'))
    expected_context = 65536 if advanced else 61440 if config.get('complement_token_budget') else 49152
    if config['max_attempts'] not in (3, 4) or config['max_model_len'] != expected_context or config['max_tokens'] != 4096:
        raise ValueError('Expected three/four proposals, the configured 48k/60k/64k protocol, and 4096 output tokens')
    if config.get('complement_token_budget') and (
            config['max_attempts'] != 3 or config['internals_token_budget'] != 24576 or
            config['complement_token_budget'] != (12288 if advanced else 16384) or config['max_unobserved_quantifiers'] != 20 or
            config['max_quantifiers'] != 50 or config['max_instances_each'] != 3 or not config.get('collect_inventory')):
        raise ValueError('Complement experiment requires 24k base, 16k extra, 50x3, 20 unobserved formulas, three proposals')
    if advanced and (config['advanced_token_budget'] != 14336 or config['advanced_timeout_ms'] != 5000 or
                     config['advanced_trace_max_mb'] != 64 or config.get('gpu_memory_utilization') != 0.95 or
                     config.get('complement_token_budget') != 12288 or config['max_attempts'] != 3 or
                     not config.get('reuse_initial_events_required') or not config.get('shared_initial_events_required')):
        raise ValueError('Advanced study requires 14k extra, 5s replay, 64MiB trace cap and 0.95 GPU allocation')
    return config


def load_tokenizer(config):
    from transformers import AutoTokenizer
    if importlib.metadata.version('transformers') != '4.51.3':
        raise ValueError('Use transformers 4.51.3 for the frozen feedback budget')
    if config.get('provider') == 'claude_code':
        # Download tokenizer files only, never the Qwen weights.
        from baseline.inference import MODEL_CODER, REVISION_CODER
        tokenizer = AutoTokenizer.from_pretrained(MODEL_CODER, revision=REVISION_CODER)
    else:
        tokenizer = AutoTokenizer.from_pretrained(prepare_model(*model_identity(config)), local_files_only=True)
    tokenizer.model_max_length = 10**12
    return tokenizer


def implementation():
    return file_hashes([*(ROOT / 'solver_needs_study').glob('*.py'),
        ROOT / 'prompts/solver-needs/system.txt', ROOT / 'prompts/solver-needs/complement.txt',
        ROOT / 'prompts/solver-needs/advanced.txt', ROOT / 'configs/solver-needs-qwen14b-advanced64k.json',
        ROOT / 'configs/solver-needs-qwen14b-complement16k.json', ROOT / 'configs/solver-needs-qwen14b.json',
        ROOT / 'configs/solver-needs-qwen14b-internals24k.json',
        ROOT / 'configs/solver-needs-qwen14b-internals32k.json',
        ROOT / 'configs/solver-needs-qwen14b-internals32k-80x3.json',
        ROOT / 'configs/solver-needs-qwen14b-internals32k-50x5.json',
        SELECTION,
        *(ROOT / 'baseline').glob('*.py'), *(ROOT / 'diagnostics').glob('*.py'),
        ROOT / 'repair_study/worker.py', ROOT / 'repair_study/relevance.py'])


def tools():
    identities = {key: tool_identity(os.environ[env]) for key, env in [('verus', 'VERUS_BIN'), ('z3', 'Z3_BIN')]}
    for key in identities:
        identities[key]['version'] = command([identities[key]['path'], '--version'])
    if VERUS_VERSION not in str(identities['verus']['version']) or '4.12.5' not in str(identities['z3']['version']):
        raise ValueError('Use the separate Verus 0.2026.02.22.2c9a6a0 and bundled Z3 4.12.5')
    identities['solver_api'] = api_identity()
    return identities


def validate(root):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation():
        raise ValueError('Code/prompts changed; use another study directory')
    for name, expected in manifest['files'].items():
        if digest((root / name).read_bytes()) != expected:
            raise ValueError('Frozen input changed: ' + name)
    return manifest


def prepare(args):
    root = args.study.resolve()
    config = configuration(getattr(args, 'config', DEFAULT_CONFIG))
    settings_reference = getattr(args, 'reference_settings_from', None)
    reference_info = None
    if settings_reference is not None:
        from .reference import reference_settings
        config, reference_info = reference_settings(settings_reference.resolve(), config)
    reuse_source = getattr(args, 'reuse_initial_from', None)
    shared_pool = getattr(args, 'shared_initial_events', None)
    if config.get('shared_initial_events_required') and shared_pool is None:
        raise ValueError('This variant requires --shared-initial-events for the common five-instance replay pool')
    if shared_pool is not None:
        pool_path = shared_pool.resolve()
        for study_path in [root, *([reuse_source.resolve()] if reuse_source is not None else [])]:
            if pool_path == study_path or pool_path.is_relative_to(study_path) or study_path.is_relative_to(pool_path):
                raise ValueError('Shared pool must be outside both source and destination study directories')
    reuse_manifest = None
    if config.get('reuse_initial_events_required') and reuse_source is None:
        raise ValueError('This variant requires --reuse-initial-from pointing to the completed 24k study')
    if reuse_source is not None:
        if settings_reference is not None:
            raise ValueError('Choose settings-only reference or same-task evidence reuse, not both')
        from .reuse import inspect_source
        reuse_manifest, config = inspect_source(reuse_source.resolve(), root, config)
    if (root / 'manifest.json').exists():
        manifest = validate(root)
        if (manifest['task_count'] != args.tasks or
                manifest.get('selection_sha256') != digest(getattr(args, 'selection', SELECTION).read_bytes()) or
                manifest['config'] != config):
            raise ValueError('Prepared study has another selection or configuration')
        print('Already prepared:', root)
        return
    source()
    identities = tools()
    selection_path = getattr(args, 'selection', SELECTION)
    rows = selected_cases(args.tasks, selection_path)
    if config.get('advanced_token_budget') and (args.tasks != 100 or [r['id'] for r in rows] != read_json(SELECTION)['ids']):
        raise ValueError('Advanced study must use exactly the frozen original 100 IDs')
    selected_ids = [row['id'] for row in rows]
    if reference_info is not None:
        from .reference import check_reference_prompt
        if len(selected_ids) != 362 or set(selected_ids) & set(reference_info['ids']):
            raise ValueError('Expected exactly 362 tasks outside the original 100-task reference')
        check_reference_prompt(settings_reference.resolve(), config, reference_info['ids'][0])
    plan = {'revision': REVISION, 'task_count': args.tasks, 'selected_ids': selected_ids,
            'selection_sha256': digest(selection_path.read_bytes()), 'config': config,
            'tool_hashes': {k: tool_signature(v) for k, v in identities.items()}, 'implementation': implementation()}
    if reference_info is not None:
        reference_manifest = read_json(settings_reference / 'manifest.json')
        if reference_manifest['tool_hashes'] != plan['tool_hashes']:
            raise ValueError('Verus/Z3 tool identities differ from the original 24k experiment')
        plan['settings_reference'] = reference_info
    if reuse_manifest is not None:
        if [c['id'] for c in reuse_manifest['cases']] != selected_ids:
            raise ValueError('Reuse source must contain exactly the same selected IDs in the same order')
        if reuse_manifest['tool_hashes'] != plan['tool_hashes']:
            raise ValueError('Reuse source uses different Verus/Z3 binaries or API')
        plan['initial_event_source'] = {'path': str(reuse_source.resolve()),
            'manifest_sha256': digest((reuse_source / 'manifest.json').read_bytes())}
        if shared_pool is not None:
            plan['shared_initial_events'] = str(shared_pool.resolve())
    if (root / 'preparation.json').exists() and read_json(root / 'preparation.json') != plan:
        raise ValueError('Preparation changed; use another output directory')
    write_json(root / 'preparation.json', plan)
    write_json(root / 'selected_ids.json', {'revision': REVISION, 'ids': selected_ids})
    write_json(root / 'selection.json', read_json(selection_path))
    tokenizer = load_tokenizer(config)
    verifier = StudyVerifier(identities['verus']['path'], identities['z3']['path'], config['verification_timeout'])
    counts, selected = Counter(), []
    for row in rows:
        label = row['paper_label']
        folder = root / 'inputs' / row['id']
        if not (folder / 'ready.json').exists():
            if reuse_manifest is not None:
                from .reuse import prepare_case
                prepare_case(reuse_source.resolve(), root, row['id'], reuse_manifest, config, tokenizer,
                             shared_pool=shared_pool)
            else:
                prepare_fresh_case(root, row, folder, verifier, tokenizer, config)
        if config.get('advanced_token_budget'):
            from .advanced import attach
            attach(folder, (folder / 'candidate.rs').read_text(encoding='utf-8'),
                   read_json(folder / 'verification.json'), EMPTY, [], tokenizer, config,
                   read_json(folder / 'feedback.json'))
        selected.append({k: row[k] for k in ('id', 'corpus', 'problem', 'source_path', 'paper_label', 'release_label')})
        counts[label] += 1
        print('Prepared', row['id'], label, flush=True)
    files = {f"inputs/{case['id']}/{name}": digest((root / 'inputs' / case['id'] / name).read_bytes())
             for case in selected for name in ('task.json', 'candidate.rs', 'verification.json', 'feedback.json', 'ready.json')}
    files['selected_ids.json'] = digest((root / 'selected_ids.json').read_bytes())
    files['selection.json'] = digest((root / 'selection.json').read_bytes())
    if config.get('advanced_token_budget'):
        advanced_count = sum(bool(read_json(root / 'inputs' / c['id'] / 'feedback.json').get('advanced')) for c in selected)
        if not advanced_count:
            raise ValueError('No advanced feedback available in preparation; inspect saved advanced/*/availability.json')
        write_json(root / 'advanced-preparation.json', {'cases_with_advanced_feedback': advanced_count,
                   'selected_cases': len(selected), 'scope': 'shared initial evidence; generated once for both arms'})
        files['advanced-preparation.json'] = digest((root / 'advanced-preparation.json').read_bytes())
    if reuse_manifest is not None:
        files.update({str(p.relative_to(root)): digest(p.read_bytes()) for p in (root / 'inputs').rglob('*') if p.is_file()})
    manifest = {**plan, 'cases': selected, 'files': files, 'selection_counts': dict(counts),
                'paper_task_count': 462, 'release_extraction_count': 468,
                'source_receipt': read_json(SOURCE / 'download-receipt.json'),
                'scope': f"published essential assertions; no reference/placebo/restoration audit rerun; labels/probes hidden; {config['max_attempts']} total proposals"}
    write_json(root / 'manifest.json', manifest)
    print('Prepared', len(selected), 'paired tasks:', root, flush=True)


def prepare_fresh_case(root, row, folder, verifier, tokenizer, config):
    task = split_task(row)
    write_json(folder / 'task.json', {k: v for k, v in task.items() if k != 'reference'})
    write_json(root / 'private' / (row['id'] + '.json'), row)
    write_text(folder / 'candidate.rs', render(task, EMPTY))
    verification = verifier.verify(folder / 'candidate.rs')
    write_json(folder / 'verification.json', verification)
    if verification['error_type'] == 'verifier_error':
        raise ValueError('Verifier infrastructure error; inspect ' + str(folder / 'verification.json'))
    code = (folder / 'candidate.rs').read_text(encoding='utf-8')
    internals(folder, code, verification, EMPTY, [], tokenizer, config)
    write_json(folder / 'ready.json', {'initially_verified': verification['success'],
               'published_screens_used': True, 'reference_placebo_restoration_not_rerun': True})


def run_case(root, arm, case, config, inference, verifier):
    frozen = root / 'inputs' / case['id']
    task = read_json(frozen / 'task.json')
    code = (frozen / 'candidate.rs').read_text(encoding='utf-8')
    verification = read_json(frozen / 'verification.json')
    if verification['success']:
        result = {'id': case['id'], 'success': False, 'initially_verified': True, 'attempts': []}
        write_json(root / arm / case['id'] / 'task.json', result)
        return result
    feedback = read_json(frozen / 'feedback.json')
    action, history, records = dict(EMPTY), [], []
    for index in range(1, config['max_attempts'] + 1):
        folder = root / arm / case['id'] / f'attempt_{index:02}'
        if (folder / 'result.json').exists():
            result = read_json(folder / 'result.json')
        else:
            started = time.perf_counter()
            base_comparison = bool(config.get('complement_token_budget'))
            payload = feedback['internals'] if arm == 'with_internals' or base_comparison else None
            advanced_study = bool(config.get('advanced_token_budget'))
            extra = feedback.get('complement') if base_comparison and (arm == 'with_internals' or advanced_study) else None
            advanced = feedback.get('advanced') if advanced_study and arm == 'with_internals' else None
            prompt = messages(code, verification, action, feedback['context'], payload, history,
                              config=config, complement=extra, advanced=advanced)
            common = messages(code, verification, action, feedback['context'], payload if base_comparison else None,
                              history, config=config, complement=extra if advanced_study else None)
            if not fits(code, verification, action, feedback['context'], payload, history, inference.tokenizer,
                        config, complement=extra, advanced=advanced):
                raise ValueError('Actual prompt exceeds context; no automatic truncation')
            request = {'messages': prompt, 'seed': (config['seed'] + index if config.get('seed') is not None else None), 'parameters': config,
                'candidate_sha256': digest(code.encode()), 'common_messages_sha256': digest(json.dumps(common, sort_keys=True).encode()),
                'internals_exposed': bool(payload and payload['queries']), 'complement_exposed': bool(extra),
                'advanced_exposed': bool(advanced)}
            if advanced_study:
                request['shared_feedback_sha256'] = digest(json.dumps({'base': payload, 'complement': extra}, sort_keys=True).encode())
                request['prompt_tokens'] = len(inference.tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True))
                request['headroom_after_output_reserve'] = config['max_model_len'] - config['max_tokens'] - request['prompt_tokens']
                request['advanced_feedback_status'] = feedback.get('advanced_selection', {}).get('status', 'unavailable') if arm == 'with_internals' else 'withheld_by_design'
            if config.get('provider') == 'claude_code':
                request['seed'] = None
            if (folder / 'request.json').exists() and read_json(folder / 'request.json') != request:
                raise ValueError('Saved request changed')
            write_json(folder / 'request.json', request)
            write_json(folder / 'exposure.json', {'availability': feedback['availability'] if arm == 'with_internals' or base_comparison else 'withheld_by_design',
                                               'payload': payload, 'complement': extra, 'advanced': advanced,
                                               'advanced_selection': feedback.get('advanced_selection') if advanced_study and arm == 'with_internals' else None,
                                               'advanced_queries': feedback.get('advanced_queries') if advanced_study and arm == 'with_internals' else None,
                                               'token_counts': {name: len(inference.tokenizer.encode(json.dumps(value,
                                                   ensure_ascii=False, indent=2), add_special_tokens=False)) if value else 0
                                                   for name, value in [('internals', payload), ('complement', extra), ('advanced', advanced)]},
                                               'context': feedback['context']})
            if (folder / 'response.json').exists():
                response = read_json(folder / 'response.json')
            else:
                if hasattr(inference, 'generate_at'):
                    response = inference.generate_at(prompt, config, folder)
                else:
                    response = inference.generate(prompt, config, request['seed'])
                write_json(folder / 'response.json', response)
            write_text(folder / 'rendered_prompt.txt', response['rendered_prompt'])
            write_text(folder / 'response.txt', response['text'])
            proposed, edit_error = action, None
            format_info = {'policy': RESPONSE_POLICY, 'accepted_action': False}
            try:
                proposed = parse_response(response['text'], metadata=format_info)
                format_info['accepted_action'] = True
                new_code = render(task, proposed)
                unchanged = tokens(new_code) == tokens(code) and proposed['nla'] == action['nla']
                if unchanged:
                    raise ValueError('No effective proof/solver-setting change')
            except (ValueError, KeyError, TypeError) as error:
                proposed, new_code, unchanged, edit_error = action, code, True, str(error)
            write_json(folder / 'response-format.json', format_info)
            write_json(folder / 'action.json', proposed)
            write_text(folder / 'candidate.rs', new_code)
            checked = verifier.verify(folder / 'candidate.rs', nla=proposed['nla'])
            write_json(folder / 'verification.json', checked)
            if config.get('provider') == 'claude_code' and checked['error_type'] == 'verifier_error':
                raise RuntimeError('Verifier infrastructure error; response preserved, proposal not finalized')
            write_json(folder / 'integrity.json', {'valid': True, 'policy': 'fixed prefix/suffix; validated proof slot; exact checked catalogue law; NLA Boolean only',
                       'edit_error': edit_error, 'acceptance_requires_whole_file_verus': True})
            result = {'attempt': index, 'success': checked['success'] and edit_error is None,
                'unchanged': unchanged, 'edit_error': edit_error, 'error_type': checked['error_type'],
                'nla_enabled': proposed['nla'], 'law': proposed['law'], 'mechanism': proposed['mechanism'],
                'input_tokens': response['input_tokens'], 'output_tokens': response['output_tokens'],
                'truncated': response['truncated'], 'inference_seconds': response['inference_seconds'],
                'processing_seconds': time.perf_counter() - started, 'internals_exposed': request['internals_exposed'],
                'advanced_exposed': request.get('advanced_exposed', False)}
            write_json(folder / 'result.json', result)
        records.append(result)
        if result['success']:
            break
        code = (folder / 'candidate.rs').read_text(encoding='utf-8')
        action, verification = read_json(folder / 'action.json'), read_json(folder / 'verification.json')
        history.append({'attempt': index, 'action': action, 'error_type': result['error_type'],
                        'edit_error': result['edit_error'], 'unchanged': result['unchanged']})
        if index < config['max_attempts']:
            started = time.perf_counter()
            cache = folder / 'next-feedback.json'
            if cache.exists():
                feedback = read_json(cache)
            else:
                feedback = internals(folder, code, verification, action, history, inference.tokenizer, config) if arm == 'with_internals' or config.get('complement_token_budget') else control_feedback(code, verification)
                if config.get('advanced_token_budget') and arm == 'with_internals':
                    from .advanced import attach
                    feedback = attach(folder, code, verification, action, history, inference.tokenizer, config, feedback)
                write_json(cache, feedback)
                result['feedback_seconds'] = time.perf_counter() - started
                write_json(folder / 'result.json', result)
    summary = {'id': case['id'], 'success': any(r['success'] for r in records), 'initially_verified': False, 'attempts': records}
    write_json(root / arm / case['id'] / 'task.json', summary)
    print(arm, case['id'], 'success' if summary['success'] else 'failed', flush=True)
    return summary


def compare(root):
    manifest = validate(root)
    rows, summaries = [], {}
    for case in manifest['cases']:
        row = {**case, 'initially_verified': read_json(root / 'inputs' / case['id'] / 'verification.json')['success'],
               'initial_internals_available': read_json(root / 'inputs' / case['id'] / 'feedback.json')['availability'] == 'available',
               'initial_advanced_available': bool(read_json(root / 'inputs' / case['id'] / 'feedback.json').get('advanced'))}
        requests = []
        for arm in ARMS:
            folder = root / arm / case['id']
            row[arm] = read_json(folder / 'task.json')['success'] if (folder / 'task.json').exists() else None
            path = folder / 'attempt_01/request.json'
            requests.append(read_json(path) if path.exists() else None)
        row['first_pair_valid'] = None
        if all(requests):
            a, b = requests
            expected = digest((root / 'inputs' / case['id'] / 'candidate.rs').read_bytes())
            row['first_pair_valid'] = (a['candidate_sha256'] == b['candidate_sha256'] == expected
                and a['common_messages_sha256'] == b['common_messages_sha256']
                and a['parameters'] == b['parameters'] and a['seed'] == b['seed']
                and ((not b.get('advanced_exposed') and a.get('shared_feedback_sha256') == b.get('shared_feedback_sha256')
                      and a.get('shared_feedback_sha256') is not None)
                     if manifest['config'].get('advanced_token_budget') else
                     not b.get('complement_exposed') if manifest['config'].get('complement_token_budget') else not b['internals_exposed']))
        rows.append(row)
    for arm in ARMS:
        completed = [read_json(root / arm / c['id'] / 'task.json') for c in manifest['cases'] if (root / arm / c['id'] / 'task.json').exists()]
        attempts = [a for t in completed for a in t['attempts']]
        summary = {'expected': len(rows), 'completed': len(completed), 'solved': sum(t['success'] for t in completed),
            'initially_verified': sum(r['initially_verified'] for r in rows),
            'repair_denominator': sum(not r['initially_verified'] for r in rows),
            'solved_by_attempt': {str(k): sum(any(a['success'] and a['attempt'] <= k for a in t['attempts']) for t in completed) for k in range(1, manifest['config']['max_attempts'] + 1)},
            'attempts': len(attempts), 'unchanged': sum(a['unchanged'] for a in attempts),
            'edit_errors': dict(Counter(a['edit_error'] for a in attempts if a['edit_error'])),
            'errors': dict(Counter(a['error_type'] for a in attempts)),
            'input_tokens': sum(a['input_tokens'] for a in attempts), 'output_tokens': sum(a['output_tokens'] for a in attempts),
            'truncated': sum(a['truncated'] for a in attempts),
            'inference_seconds': sum(a['inference_seconds'] for a in attempts),
            'processing_seconds': sum(a['processing_seconds'] + a.get('feedback_seconds', 0) for a in attempts),
            'exposed_attempts': sum(a['internals_exposed'] for a in attempts),
            'advanced_exposed_attempts': sum(a.get('advanced_exposed', False) for a in attempts),
            'by_paper_label': {label: {'expected': sum(r['paper_label'] == label for r in rows),
                'solved': sum(r['paper_label'] == label and r[arm] is True for r in rows)} for label in LABELS},
            'missing': [r['id'] for r in rows if r[arm] is None]}
        summaries[arm] = summary
        write_json(root / arm / 'summary.json', summary)
    report = {'summaries': summaries, 'paired': rows, 'complete': all(not s['missing'] for s in summaries.values()),
        'first_pair_check_passed': all(r['first_pair_valid'] is True for r in rows if not r['initially_verified']),
        'with_only': [r['id'] for r in rows if r[ARMS[0]] is True and r[ARMS[1]] is False],
        'without_only': [r['id'] for r in rows if r[ARMS[1]] is True and r[ARMS[0]] is False],
        'sessions': [read_json(p) for p in root.glob('session-*.json')],
        'label_disagreements': [r['id'] for r in rows if r['paper_label'] != r['release_label']],
        'scope': manifest['scope']}
    report['arm_meanings'] = ({'with_internals': 'base24k + complement12k + advanced14k',
                             'without_internals': 'base24k + complement12k'}
        if manifest['config'].get('advanced_token_budget') else
        {'with_internals': 'base24k plus complement16k', 'without_internals': 'base24k only'}
        if manifest['config'].get('complement_token_budget') else {'with_internals': 'internals', 'without_internals': 'no internals'})
    write_json(root / 'comparison.json', report)
    lines = [f"# Solver Needs: paired repair ({manifest['config']['model']})", '', '| Arm | Completed | Solved | Attempts | Unchanged |', '|---|---|---|---|---|']
    if manifest['config'].get('advanced_token_budget'):
        lines[2:2] = ['Both arms receive base24k + complement12k; only with_internals additionally receives advanced14k.', '']
    for arm, s in summaries.items():
        lines.append(f"| {arm} | {s['completed']}/{s['expected']} | {s['solved']} | {s['attempts']} | {s['unchanged']} |")
    lines += ['', '| Paper label | Selected | With internals | Without internals |', '|---|---|---|---|']
    for label in LABELS:
        lines.append(f"| {label} | {summaries[ARMS[0]]['by_paper_label'][label]['expected']} | {summaries[ARMS[0]]['by_paper_label'][label]['solved']} | {summaries[ARMS[1]]['by_paper_label'][label]['solved']} |")
    lines += ['', f"Complete: {report['complete']}; initial pairs valid: {report['first_pair_check_passed']}",
        f"Initially verified without a model: {summaries[ARMS[0]]['initially_verified']}; repair denominator: {summaries[ARMS[0]]['repair_denominator']}",
        f"{manifest['config']['max_attempts']} TOTAL proposals per task/arm. Labels and successful probes are hidden from model.",
        'Paper/release label disagreements and exclusive wins are listed in comparison.json.',
        'AX catalogue lemmas are checked, not unchecked axioms. NLA changes are explicit experimental actions.']
    if manifest['config'].get('advanced_token_budget'):
        lines += ['', 'IMPORTANT: with_internals = base24k + complement12k + advanced14k; without_internals = base24k + complement12k. Both receive internals; three proposals, 64k context.',
                  'Advanced exposure counts: ' + str({a: s['advanced_exposed_attempts'] for a, s in summaries.items()})]
    elif manifest['config'].get('complement_token_budget'):
        lines += ['', 'IMPORTANT: with_internals = base24k + complement16k; without_internals = base24k only (both receive internals).']
    write_text(root / 'comparison.md', '\n'.join(lines))
    print(root / 'comparison.md', flush=True)
    return report


def initialize_inference(root, config):
    try:
        return LocalVLLM(config)
    except Exception as error:
        if config.get('advanced_token_budget'):
            path = root / 'initialization-error.json'
            write_json(path, {'error': str(error), 'type': type(error).__name__,
                'max_model_len': config['max_model_len'], 'gpu_memory_utilization': config.get('gpu_memory_utilization'),
                'policy': 'No automatic context reduction, quantization or CPU offload'})
            raise RuntimeError('Could not initialize the fixed 64k model configuration; inspect ' + str(path)) from error
        raise


def run(args):
    source()  # Validate the pinned upstream files used by the catalogue/renderer.
    root = args.study.resolve()
    manifest, identities = validate(root), tools()
    if {k: tool_signature(v) for k, v in identities.items()} != manifest['tool_hashes']:
        raise ValueError('Prepared inputs and run use different tool binaries/API')
    config = manifest['config']
    if config.get('provider') == 'claude_code':
        from .claude_code import run_local
        return run_local(root, manifest, identities)
    versions = {p: importlib.metadata.version(p) for p in ('vllm', 'transformers', 'torch')}
    if versions['vllm'] != '0.8.5' or versions['transformers'] != '4.51.3':
        raise ValueError('Use the pinned GPU dependencies')
    import torch
    device = torch.cuda.get_device_properties(0)
    gpu = {'name': device.name, 'memory_bytes': device.total_memory, 'uuid': str(getattr(device, 'uuid', ''))}
    fingerprint = digest(json.dumps({'manifest': digest((root / 'manifest.json').read_bytes()), 'versions': versions,
        'gpu_class': device.name, 'requirements': digest((ROOT / 'requirements-cluster.txt').read_bytes())}, sort_keys=True).encode())
    if (root / 'run.json').exists() and read_json(root / 'run.json')['fingerprint'] != fingerprint:
        raise ValueError('Runtime/GPU class changed; resume on the same class or use another output')
    write_json(root / 'run.json', {'fingerprint': fingerprint, 'config': config, 'versions': versions,
        'python': sys.version, 'platform': platform.platform(), 'gpu': gpu, 'tools': identities,
        'solver_api_scope': 'same Z3 version; separate instrumented diagnostic library; not original search'})
    pending = [(i, c) for i, c in enumerate(manifest['cases']) if any(not (root / a / c['id'] / 'task.json').exists() for a in ARMS)]
    for _, case in pending:
        if read_json(root / 'inputs' / case['id'] / 'verification.json')['success']:
            for arm in ARMS:
                run_case(root, arm, case, config, None, None)
    pending = [(i, c) for i, c in pending if any(not (root / a / c['id'] / 'task.json').exists() for a in ARMS)]
    if not pending:
        compare(root)
        return 0
    started = time.perf_counter()
    inference = initialize_inference(root, config)
    session = {'model_load_seconds': time.perf_counter() - started, 'gpu': gpu}
    session_path = root / f'session-{time.time_ns()}.json'
    write_json(session_path, session)
    verifier = StudyVerifier(identities['verus']['path'], identities['z3']['path'], config['verification_timeout'])
    try:
        for index, case in pending:
            for arm in (ARMS if index % 2 == 0 else ARMS[::-1]):
                if (root / arm / case['id'] / 'task.json').exists():
                    continue
                try:
                    run_case(root, arm, case, config, inference, verifier)
                except Exception as error:
                    write_json(root / arm / case['id'] / 'error.json', {'error': str(error), 'type': type(error).__name__})
                    print(arm, case['id'], 'infrastructure error:', error, flush=True)
    finally:
        session['wall_seconds'] = time.perf_counter() - started
        write_json(session_path, session)
        report = compare(root)
    return 0 if report['complete'] and report['first_pair_check_passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'compare'))
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--tasks', type=int, default=100)
    parser.add_argument('--selection', type=Path, default=SELECTION)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG,
                        help='Preparation config; run uses the config frozen in the manifest')
    parser.add_argument('--reuse-initial-from', type=Path,
                        help='Completed study providing frozen initial candidates and saved replay events')
    parser.add_argument('--shared-initial-events', type=Path,
                        help='Shared initial replay pool collected once with five saved instances per group')
    parser.add_argument('--reference-settings-from', type=Path,
                        help='Original completed 100-task study whose settings/prompt must match the complementary run')
    args = parser.parse_args()
    if not 1 <= args.tasks <= 462:
        parser.error('tasks must be between 1 and 462 (and fit the saved selection)')
    with run_lock(args.study.resolve()):
        if args.command == 'prepare':
            prepare(args)
        elif args.command == 'run':
            return run(args)
        else:
            compare(args.study.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
