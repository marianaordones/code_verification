"""Resumable CPU pilot. Original records and failed evidence are never filtered out."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

from baseline.integrity import IntegrityValidator
from baseline.obligation import ObligationVerifier
from baseline.prompts import ROOT
from baseline.provenance import command, tool_identity, tool_signature, file_hashes
from baseline.storage import digest, read_json, write_json, write_text
from baseline.verifier import Verifier, execute
from diagnostics.z3_internals import api_env, api_identity
from repair_study.relevance import source_context, rank
from solver_needs_study.feedback import internals
from .data import select, codes, code_tags, families, preservation_target

CONFIG = ROOT / 'configs/safe-internals-pilot200.json'
TOKENIZER_MODEL = 'Qwen/Qwen2.5-Coder-14B-Instruct'
TOKENIZER_REVISION = 'aedcc2d42b622764e023cf882b6652e646b95671'
TOKENIZER_FILES = ['tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json',
                   'config.json', 'vocab.json', 'merges.txt']
PACKAGES = {'20x3': (12288, 20), '50x3': (24576, 50)}


def implementation():
    paths = [*(ROOT / 'safe_internals').glob('*.py'), CONFIG, ROOT / 'configs/safe-repair-pilot200.json',
             ROOT / 'prompts/safe-internals.txt', ROOT / 'requirements-safe-cpu.txt',
             ROOT / 'solver_needs_study/feedback.py', ROOT / 'repair_study/worker.py',
             ROOT / 'repair_study/relevance.py', ROOT / 'repair_study/regions.py',
             ROOT / 'baseline/obligation.py', ROOT / 'baseline/verifier.py',
             ROOT / 'baseline/integrity.py', ROOT / 'baseline/storage.py',
             ROOT / 'diagnostics/z3_internals.py', ROOT / 'diagnostics/z3_probe.py']
    return file_hashes(paths)


def prepare(dataset, root):
    config = read_json(CONFIG)
    source_sha = digest(dataset.read_bytes())
    frozen_selection = read_json(ROOT / 'configs/safe-repair-pilot200.json')
    if source_sha != frozen_selection['dataset_sha256']:
        raise ValueError('Dataset bytes differ from the frozen SAFE source. Use the original sft_safe_25k (1).json file.')
    rows = read_json(dataset)
    selection = select(rows, config['examples'], config['seed'])
    if selection != {k: v for k, v in frozen_selection.items() if k != 'dataset_sha256'}:
        raise ValueError('Selection differs from the frozen 200-example pilot')
    groups = families(rows)
    manifest = {'schema': 'safe-internals-pilot-v1', 'dataset_sha256': source_sha,
                'dataset_rows': len(rows), 'selection': selection, 'config': config,
                'implementation': implementation(), 'split': 'pilot_unsplit_not_training_ready',
                'family_policy': 'exact input/target code and nonempty label connected components; no semantic/benchmark-disjoint guarantee'}
    if (root / 'manifest.json').exists():
        if read_json(root / 'manifest.json') != manifest:
            raise ValueError('Dataset, configuration or code changed; use another output directory')
    else:
        write_json(root / 'manifest.json', manifest)
    frozen = {}
    for case in selection['cases']:
        folder = root / 'examples' / case['id']
        row = rows[case['index']]
        source, target = codes(row)
        values = {'original.json': row, 'metadata.json': {**case, 'family_id': groups[case['index']],
                  'input_tags': code_tags(source), 'target_tags': code_tags(target),
                  'target_code_sha256': digest(target.encode()),
                  'selection_uses_target': False, 'label_visible_to_model': False}}
        for name, value in values.items():
            if (folder / name).exists() and read_json(folder / name) != value:
                raise ValueError('Frozen record changed: ' + str(folder / name))
            write_json(folder / name, value)
        for name, code in [('candidate.rs', source), ('target/reference.rs', target)]:
            if (folder / name).exists() and (folder / name).read_text(encoding='utf-8') != code:
                raise ValueError('Frozen source changed: ' + str(folder / name))
            write_text(folder / name, code)
        for name in ['original.json', 'metadata.json', 'candidate.rs', 'target/reference.rs']:
            frozen[str((folder / name).relative_to(root))] = digest((folder / name).read_bytes())
    write_json(root / 'selected_ids.json', selection)
    write_json(root / 'frozen-files.json', frozen)
    print(f"Prepared {len(selection['cases'])} repair examples: {root}", flush=True)


def validate(root):
    manifest = read_json(root / 'manifest.json')
    if manifest['implementation'] != implementation():
        raise ValueError('Collector implementation changed; restore the original code or use another output')
    for name, sha in read_json(root / 'frozen-files.json').items():
        if digest((root / name).read_bytes()) != sha:
            raise ValueError('Frozen record changed: ' + name)
    return manifest


def load_tokenizer():
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    if importlib.metadata.version('transformers') != '4.51.3':
        raise ValueError('Use transformers 4.51.3')
    cache = Path(os.environ.get('SAFE_TOKENIZER_DIR', str(Path.home() / 'pylibs/safe-qwen-tokenizer')))
    cache.mkdir(parents=True, exist_ok=True)
    # local_dir produces regular files; never download model weights.
    snapshot_download(TOKENIZER_MODEL, revision=TOKENIZER_REVISION,
                      allow_patterns=TOKENIZER_FILES, local_dir=str(cache), max_workers=2)
    tokenizer = AutoTokenizer.from_pretrained(str(cache), local_files_only=True)
    tokenizer.model_max_length = 10**12
    identity = {'model': TOKENIZER_MODEL, 'revision': TOKENIZER_REVISION,
                'files': {f: digest((cache / f).read_bytes()) for f in TOKENIZER_FILES if (cache / f).exists()}}
    return tokenizer, identity


def visible_messages(code, verification, system, payload=None):
    user = ('<current_program>\n```rust\n' + code + '```\n</current_program>\n'
            '<verus_diagnostics>\n' + verification['stdout'] + '\n' + verification['stderr'] + '\n</verus_diagnostics>\n')
    if payload and payload.get('queries'):
        user += '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>\n'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def message_builder(code, verification, action, context, payload, history, config=None, **unused):
    return visible_messages(code, verification, config['system_prompt_text'], payload)


def limited(command_args, timeout, memory_mb, cwd=None, env=None):
    return execute([sys.executable, '-m', 'safe_internals.limits', '--memory-mb', str(memory_mb),
                    '--file-mb', '128', '--', *command_args], timeout, cwd=cwd, env=env)


class PilotVerifier(ObligationVerifier):
    def __init__(self, executable, z3, timeout, memory_mb):
        super().__init__(executable, z3, timeout)
        self.memory_mb = memory_mb

    def verify(self, source):
        # Existing transparent capture preserves the original solver protocol.
        # Its execute symbol is not monkeypatched (two parallel threads).
        from .verify import verify
        return verify(self, source)


def collect_events(folder, verification, config):
    report = read_json(folder / 'solver/report.json')
    code = (folder / 'candidate.rs').read_text(encoding='utf-8')
    context = source_context(code, verification)
    write_json(folder / 'source-context.json', context)
    failed = [q for q in report['queries'] if q['result'] in ('sat', 'unknown')]
    statuses = []
    if not verification['success']:
        for query in failed[:config['max_queries']]:
            output = folder / 'internals' / query['id']
            if not (output / 'process.json').exists():
                call = limited([sys.executable, '-m', 'repair_study.worker', '--query',
                                str((folder / 'solver' / query['file']).resolve()), '--context',
                                str((folder / 'source-context.json').resolve()), '--output', str(output.resolve()),
                                '--max-instances-per-group', str(config['raw_instances_per_group'])],
                               config['replay_wall_seconds'], config['replay_memory_mb'], env=api_env())
                write_json(output / 'process.json', call)
            call = read_json(output / 'process.json')
            replay = read_json(output / 'report.json') if (output / 'report.json').exists() else {}
            statuses.append({'id': query['id'], 'original_result': query['result'],
                             'query_sha256': digest((folder / 'solver' / query['file']).read_bytes()),
                             'replay_result': replay.get('result'),
                             'concordant': call['returncode'] == 0 and not call['timed_out'] and
                                           replay.get('status') == 'completed' and replay.get('result') == query['result'],
                             'process_returncode': call['returncode'], 'wall_timeout': call['timed_out'],
                             'seconds': call['seconds'], 'observed': replay.get('instantiations_observed'),
                             'saved': replay.get('instantiations_saved'), 'callback_errors': replay.get('callback_errors'),
                             'oversized_events': replay.get('oversized_events')})
    collection = {'scope': 'separate_instrumented_replays_not_original_search',
                  'failed_queries_available': len(failed), 'queries_not_replayed': max(0, len(failed) - len(statuses)),
                  'raw_policy': {'ranked_group_reservoir': 128,
                                 'instances_per_group': config['raw_instances_per_group'],
                                 'max_event_serialized_characters': 64000,
                                 'file_limit_mib_per_process_file': 128,
                                 'timeout_ms_per_solver_check': 5000,
                                 'wall_seconds_per_replay': config['replay_wall_seconds'],
                                 'memory_mb_per_process': config['replay_memory_mb'],
                                 'all_search_events_preserved': False}, 'queries': statuses}
    write_json(folder / 'collection.json', collection)
    return collection


def collect_case(root, case, config, tokenizer, verus, z3, lynette):
    started = time.perf_counter()
    folder = root / 'examples' / case['id']
    if (folder / 'result.json').exists():
        return read_json(folder / 'result.json')
    original = read_json(folder / 'original.json')
    code = (folder / 'candidate.rs').read_text(encoding='utf-8')
    system = original['prompt'] + '\n\n' + (ROOT / 'prompts/safe-internals.txt').read_text(encoding='utf-8')
    if not (folder / 'verification.json').exists() or read_json(folder / 'verification.json')['error_type'] == 'verifier_error':
        value = PilotVerifier(verus, z3, config['verification_timeout'], config['verus_memory_mb']).verify(folder / 'candidate.rs')
        write_json(folder / 'verification.json', value)
    verification = read_json(folder / 'verification.json')
    if verification['error_type'] == 'verifier_error':
        raise RuntimeError('Input verifier infrastructure failure; retained for retry')
    replay_started = time.perf_counter()
    collection = collect_events(folder, verification, config)
    replay_seconds = time.perf_counter() - replay_started
    packing_started = time.perf_counter()
    if not verification['success']:
        for name, (budget, groups) in PACKAGES.items():
            package_config = {**config, 'internals_token_budget': budget, 'max_quantifiers': groups,
                              'max_instances_each': 3, 'max_tokens': 4096, 'max_model_len': 61440,
                              'system_prompt_text': system, 'normalize_statistics': True}
            name_file = f'feedback-{name}.json'
            if not (folder / name_file).exists():
                try:
                    internals(folder, code, verification, {}, [], tokenizer, package_config, replay=False,
                              message_builder=message_builder, feedback_name=name_file)
                except ValueError as error:
                    write_json(folder / name_file, {'internals': None, 'availability': 'unavailable',
                                                   'error': str(error), 'context': collection['scope']})
    else:
        for name in PACKAGES:
            write_json(folder / f'feedback-{name}.json', {'internals': None, 'availability': 'input_already_verified'})
    packing_seconds = time.perf_counter() - packing_started
    # Target validation runs AFTER feedback selection and never feeds it.
    target_folder = folder / 'target'
    if not (target_folder / 'verification.json').exists() or read_json(target_folder / 'verification.json')['error_type'] == 'verifier_error':
        target = Verifier.classify(limited([verus, str((target_folder / 'reference.rs').resolve())],
                                          config['verification_timeout'], config['verus_memory_mb'],
                                          cwd=target_folder, env=dict(os.environ, VERUS_Z3_PATH=z3)))
        write_json(target_folder / 'verification.json', target)
    if read_json(target_folder / 'verification.json')['error_type'] == 'verifier_error':
        raise RuntimeError('Target verifier infrastructure failure; retained for retry')
    if not (target_folder / 'preservation.json').exists():
        try:
            comparison, count = preservation_target(code, (target_folder / 'reference.rs').read_text(encoding='utf-8'))
            write_text(target_folder / 'preservation-copy.rs', comparison)
            check = IntegrityValidator(lynette).validate(folder / 'candidate.rs', target_folder / 'preservation-copy.rs')
            check['added_loop_isolation_false_attributes_ignored_for_preservation'] = count
        except (ValueError, IndexError) as error:
            check = {'status': 'unparseable', 'valid': False, 'reason': str(error)}
        write_json(target_folder / 'preservation.json', check)
    packages = {}
    available, candidate_groups = set(), set()
    context = read_json(folder / 'source-context.json')
    for query in collection['queries']:
        if not query['concordant']:
            continue
        events_path = folder / 'internals' / query['id'] / 'instantiations.jsonl'
        if events_path.exists():
            for line in events_path.read_text(encoding='utf-8').splitlines():
                event = json.loads(line)
                key = (query['id'], event['quantifier_smt'])
                available.add(key)
                if rank(event['quantifier_smt'], context)[1].startswith('candidate_'):
                    candidate_groups.add(key)
    base = visible_messages(code, verification, system)
    target_text = original['output']
    for name, (budget, _) in PACKAGES.items():
        feedback = read_json(folder / f'feedback-{name}.json')
        payload = feedback['internals']
        msgs = visible_messages(code, verification, system, payload)
        input_tokens = len(tokenizer.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True))
        full_tokens = len(tokenizer.apply_chat_template(msgs + [{'role': 'assistant', 'content': target_text}], tokenize=True))
        block_tokens = len(tokenizer.encode(json.dumps(payload, ensure_ascii=False, indent=2), add_special_tokens=False)) if payload else 0
        sent = {(q['id'], g['quantifier_smt']) for q in (payload or {}).get('queries', []) for g in q['quantifiers']}
        packages[name] = {'availability': feedback['availability'], 'block_tokens': block_tokens,
                          'budget': budget, 'input_tokens': input_tokens, 'full_training_tokens': full_tokens,
                          'output_text_tokens': len(tokenizer.encode(target_text, add_special_tokens=False)),
                          'input_plus_reserved_output': input_tokens + 4096,
                          'fits_collection_context_with_reserve': input_tokens + 4096 <= 61440,
                          'full_training_fits_32k': full_tokens <= 32768,
                          'full_training_fits_48k': full_tokens <= 49152,
                          'groups_sent': sum(len(q['quantifiers']) for q in (payload or {}).get('queries', [])),
                          'groups_available_in_saved_events': len(available), 'groups_omitted': len(available - sent),
                          'candidate_groups_available': len(candidate_groups),
                          'candidate_groups_omitted': len(candidate_groups - sent),
                          'instances_sent': sum(len(g['instances']) for q in (payload or {}).get('queries', []) for g in q['quantifiers'])}
        write_json(folder / f'messages-{name}.json', msgs)
    write_json(folder / 'messages-baseline.json', base)
    status = ('input_already_verified' if verification['success'] else 'internals_available' if
              any(p['availability'] == 'available' for p in packages.values()) else
              'concordant_replay_without_fitting_packet' if any(q['concordant'] for q in collection['queries']) else
              'no_captured_failing_queries' if not collection['failed_queries_available'] else 'no_concordant_replay')
    result = {'id': case['id'], 'status': status, 'input_error_type': verification['error_type'],
              'target_success': read_json(target_folder / 'verification.json')['success'],
              'preservation_status': read_json(target_folder / 'preservation.json')['status'],
              'packages': packages, 'seconds': time.perf_counter() - started,
              'capture_seconds': verification['seconds'], 'replay_stage_seconds_this_session': replay_seconds,
              'packing_seconds_this_session': packing_seconds,
              'target_verification_seconds': read_json(target_folder / 'verification.json')['seconds']}
    write_json(folder / 'result.json', result)
    return result


def collect(root, workers=2):
    manifest = validate(root)
    config = manifest['config']
    identities = {}
    for name, env in [('verus', 'VERUS_BIN'), ('z3', 'Z3_BIN'), ('lynette', 'LYNETTE_BIN')]:
        value = tool_identity(os.environ[env])
        value['version'] = command([value['path'], '--help' if name == 'lynette' else '--version'])
        identities[name] = value
    if config['verus_revision_contains'] not in str(identities['verus']['version']):
        raise ValueError('Expected benchmark-compatible Verus revision ' + config['verus_revision_contains'])
    identities['api'] = api_identity()
    tokenizer, tokenizer_id = load_tokenizer()
    identity = {'tools': {k: tool_signature(v) for k, v in identities.items()}, 'tokenizer': tokenizer_id,
                'python_version': platform.python_version(),
                'packages': {p: importlib.metadata.version(p) for p in ('transformers', 'tokenizers', 'huggingface-hub')},
                'implementation': manifest['implementation']}
    bundle_manifest = os.environ.get('SAFE_TOOLS_MANIFEST')
    if bundle_manifest and Path(bundle_manifest).is_file():
        identity['native_bundle_manifest'] = read_json(bundle_manifest)
    resolved = Path(os.environ.get('PROJECT_LIBS', '.')) / 'requirements-resolved.txt'
    if resolved.is_file():
        identity['cpu_dependencies_sha256'] = digest(resolved.read_bytes())
    if (root / 'runtime.json').exists() and read_json(root / 'runtime.json') != identity:
        raise ValueError('Runtime/tool/tokenizer identity changed; use another output')
    write_json(root / 'runtime.json', identity)
    paths = [identities[k]['path'] for k in ('verus', 'z3', 'lynette')]
    pending = [c for c in manifest['selection']['cases'] if not (root / 'examples' / c['id'] / 'result.json').exists()]
    started = time.perf_counter()
    failures = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(collect_case, root, c, config, tokenizer, *paths): c for c in pending}
            for future in as_completed(futures):
                case = futures[future]
                try:
                    result = future.result()
                    print(f"Collected {case['id']}: {result['status']}", flush=True)
                except Exception as error:
                    failures.append(case['id'])
                    write_json(root / 'examples' / case['id'] / 'error.json', {'type': type(error).__name__, 'error': str(error)})
                    print(f"Collection error {case['id']}: {error}", flush=True)
    finally:
        write_json(root / f'session-{time.time_ns()}.json', {'wall_seconds': time.perf_counter() - started,
                   'workers': workers, 'submitted': len(pending), 'failed_this_session': failures,
                   'slurm_job_id': os.environ.get('SLURM_JOB_ID'), 'host': platform.node()})
        summarize(root)
    return 1 if failures else 0


def distribution(values):
    values = sorted(values)
    if not values:
        return {'n': 0}
    return {'n': len(values), 'min': values[0], 'mean': sum(values) / len(values),
            'median': (values[(len(values)-1)//2] + values[len(values)//2]) / 2,
            'p90': values[max(0, (9 * len(values) + 9) // 10 - 1)], 'max': values[-1]}


def summarize(root):
    manifest = read_json(root / 'manifest.json')
    cases = manifest['selection']['cases']
    results, missing, collections, captures = [], [], [], []
    exports = {name: [] for name in ('baseline', *PACKAGES)}
    master = []
    for case in cases:
        folder = root / 'examples' / case['id']
        row, metadata = read_json(folder / 'original.json'), read_json(folder / 'metadata.json')
        if not (folder / 'result.json').exists():
            missing.append(case['id'])
            master.append({'id': case['id'], 'original': row, 'metadata': metadata, 'status': 'pending_or_collection_error'})
            continue
        result = read_json(folder / 'result.json')
        results.append(result)
        if (folder / 'collection.json').exists():
            collections.append(read_json(folder / 'collection.json'))
        if (folder / 'solver/report.json').exists():
            captures.append(read_json(folder / 'solver/report.json'))
        master.append({'id': case['id'], 'original': row, 'metadata': metadata, 'collection': result,
                       'artifact_directory': str(folder.relative_to(root))})
        for name in exports:
            messages = read_json(folder / f'messages-{name}.json')
            exports[name].append({'id': case['id'], 'family_id': metadata['family_id'],
                                  'messages': messages + [{'role': 'assistant', 'content': row['output']}],
                                  'training_policy': 'assistant_output_only; pilot_unsplit_unfiltered'})
    for name, rows in exports.items():
        write_text(root / 'exports' / f'{name}.jsonl', ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    write_text(root / 'master.jsonl', ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in master))
    summary = {'expected': len(cases), 'completed': len(results), 'complete': not missing, 'missing': missing,
               'statuses': dict(Counter(r['status'] for r in results)),
               'input_errors': dict(Counter(r['input_error_type'] for r in results)),
               'target_verified': sum(r['target_success'] for r in results),
               'original_query_results': dict(Counter(q['result'] for c in captures for q in c['queries'])),
               'capture_errors': sum(len(c['capture_errors']) for c in captures),
               'replayed_queries': sum(len(c['queries']) for c in collections),
               'concordant_replayed_queries': sum(q['concordant'] for c in collections for q in c['queries']),
               'replay_wall_timeouts': sum(q['wall_timeout'] for c in collections for q in c['queries']),
               'callback_errors': sum(q['callback_errors'] or 0 for c in collections for q in c['queries']),
               'raw_observed_instances': sum(q['observed'] or 0 for c in collections for q in c['queries']),
               'raw_saved_instances': sum(q['saved'] or 0 for c in collections for q in c['queries']),
               'preservation': dict(Counter(r['preservation_status'] for r in results)),
               'input_assume_calls': sum(read_json(root / 'examples' / c['id'] / 'metadata.json')['input_tags']['assume_call'] is True for c in cases),
               'target_assume_calls': sum(read_json(root / 'examples' / c['id'] / 'metadata.json')['target_tags']['assume_call'] is True for c in cases),
               'case_seconds': distribution([r['seconds'] for r in results]),
               'packages': {name: {field: distribution([r['packages'][name][field] for r in results])
                                      for field in ('block_tokens', 'input_tokens', 'full_training_tokens', 'groups_sent', 'instances_sent',
                                                    'groups_available_in_saved_events', 'groups_omitted', 'candidate_groups_omitted')}
                            for name in PACKAGES},
               'package_budget_violations': sum(p['block_tokens'] > p['budget'] for r in results for p in r['packages'].values()),
               'context_reservation_violations': sum(not p['fits_collection_context_with_reserve'] for r in results for p in r['packages'].values()),
               'extra_groups_in_50x3': distribution([r['packages']['50x3']['groups_sent'] - r['packages']['20x3']['groups_sent'] for r in results]),
               'phase_seconds': {phase: distribution([r[phase] for r in results]) for phase in
                                 ('capture_seconds', 'replay_stage_seconds_this_session', 'packing_seconds_this_session', 'target_verification_seconds')},
               'artifact_bytes': sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
               'export_scope': 'same completed IDs and targets in all three views; unfiltered; not certified training data',
               'version_compatibility': 'SAFE original Verus commit not established; fixed historical VerusBench revision tested empirically'}
    write_json(root / 'summary.json', summary)
    lines = ['# SAFE internals pilot', '', f"Completed: {len(results)}/{len(cases)}; complete: {not missing}.",
             'CPU collection only: no LLM, fine-tuning, or full SMT query in messages.',
             '', '| Package | Mean tokens | P90 tokens | Mean groups | P90 full training tokens |', '|---|---|---|---|---|']
    for name, fields in summary['packages'].items():
        lines.append(f"| {name} | {fields['block_tokens'].get('mean', 0):.1f} | {fields['block_tokens'].get('p90', 0)} | {fields['groups_sent'].get('mean', 0):.1f} | {fields['full_training_tokens'].get('p90', 0)} |")
    lines += ['', 'Statuses: ' + str(summary['statuses']), 'Input errors: ' + str(summary['input_errors']),
              f"Targets accepted by Verus: {summary['target_verified']} (assume-containing targets are tagged, not filtered).",
              'Preservation: ' + str(summary['preservation']),
              f"Packet budget violations: {summary['package_budget_violations']}; input+4096 violations: {summary['context_reservation_violations']}.",
              f"Queries replayed/concordant: {summary['replayed_queries']}/{summary['concordant_replayed_queries']}; capture errors: {summary['capture_errors']}.",
              'Per-case seconds: ' + str(summary['case_seconds']),
              'All rows retained in master.jsonl. Exports are unsplit, unfiltered pilot views. Do not train blindly.',
              'Raw observations are bounded samples from outcome-concordant diagnostic replays, not the original solver search.']
    write_text(root / 'report.md', '\n'.join(lines))
    print(root / 'report.md', flush=True)
    return summary
