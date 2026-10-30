"""Freeze initial evidence from a completed study and repackage it without replay."""
import copy
import json
import re

from baseline.storage import digest, read_json, write_json
from .actions import EMPTY, render
from .download import REVISION
from .feedback import internals, messages


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Evidence path escapes source directory: ' + str(relative))
    return path


def common_messages(request):
    value = copy.deepcopy(request['messages'])
    for message in value:
        message['content'] = re.sub(r'<solver_internals>\n.*?\n</solver_internals>\n', '',
                                    message['content'], flags=re.S)
    return value


def inspect_source(source, destination, config):
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('Source and destination studies must be separate directories')
    manifest = read_json(source / 'manifest.json')
    if manifest['revision'] != REVISION or len(manifest['cases']) not in (100, 362):
        raise ValueError('Expected a pinned 100-task or remaining-362 study')
    if len(manifest['cases']) == 362:
        from baseline.prompts import ROOT
        expected_ids = read_json(ROOT / 'configs/solver-needs-tasks-remaining362.json')['ids']
        if [case['id'] for case in manifest['cases']] != expected_ids:
            raise ValueError('Reuse source must contain the frozen remaining 362 IDs in order')
    previous = manifest['config']
    allowed_changes = {'max_attempts', 'internals_token_budget', 'experiment',
                       'reuse_initial_events_required', 'system_prompt_text',
                       'max_quantifiers', 'max_instances_each', 'replay_max_instances',
                       'shared_initial_events_required', 'max_model_len', 'complement_token_budget',
                       'max_unobserved_quantifiers', 'collect_inventory', 'advanced_token_budget',
                       'advanced_timeout_ms', 'advanced_trace_max_mb', 'gpu_memory_utilization', 'advanced_blocks', 'single_arm'}
    if previous.get('internals_token_budget') != 24576:
        raise ValueError('Reuse must start from the 24k study')
    if {k: v for k, v in config.items() if k not in allowed_changes} != {
            k: v for k, v in previous.items() if k not in allowed_changes}:
        raise ValueError('Generation/selection settings differ beyond the permitted budget changes')
    for name, expected in manifest['files'].items():
        if digest(contained(source, name).read_bytes()) != expected:
            raise ValueError('Frozen source artifact changed: ' + name)
    for case in manifest['cases']:
        for arm in ('with_internals', 'without_internals'):
            if not (source / arm / case['id'] / 'task.json').exists():
                raise ValueError('Source study is not complete: ' + arm + '/' + case['id'])
    first_id = manifest['cases'][0]['id']
    request = read_json(source / 'with_internals' / first_id / 'attempt_01/request.json')
    if request['messages'][0]['role'] != 'system':
        raise ValueError('Source system prompt is missing')
    config = {**config, 'system_prompt_text': request['messages'][0]['content']}
    return manifest, config


def prepare_case(source, destination, key, manifest, config, tokenizer, shared_pool=None):
    origin = source / 'inputs' / key
    folder = destination / 'inputs' / key
    copied = {}

    def snapshot(relative, target=None, evidence_root=None):
        evidence_root = evidence_root or origin
        path = contained(evidence_root, relative)
        content = path.read_bytes()
        source_name = str(path.relative_to(source)).replace('\\', '/') if evidence_root == origin else 'pool/' + str(relative)
        expected = manifest['files'].get(source_name) if evidence_root == origin else None
        if expected is not None and digest(content) != expected:
            raise ValueError('Source artifact changed: ' + source_name)
        new_path = contained(folder, target or relative)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_bytes(content)
        copied[str(relative)] = digest(content)

    for name in ('task.json', 'candidate.rs', 'verification.json'):
        snapshot(name)
    snapshot('feedback.json', 'source-feedback.json')
    task = read_json(folder / 'task.json')
    code = (folder / 'candidate.rs').read_text(encoding='utf-8')
    if render(task, EMPTY) != code:
        raise ValueError('Source candidate differs from the current mechanical proof-slot renderer: ' + key)
    verification = read_json(folder / 'verification.json')
    saved = read_json(folder / 'source-feedback.json')
    requests = [read_json(source / arm / key / 'attempt_01/request.json')
                for arm in ('with_internals', 'without_internals')]
    common = messages(code, verification, EMPTY, saved['context'], None, [],
                      config={k: v for k, v in config.items() if k not in ('complement_token_budget', 'advanced_token_budget')})
    common_hash = digest(json.dumps(common, sort_keys=True).encode())
    for request in requests:
        if common_messages(request) != common or request['common_messages_sha256'] != common_hash:
            raise ValueError('Common first prompt differs from source: ' + key)
        if request['candidate_sha256'] != digest((folder / 'candidate.rs').read_bytes()):
            raise ValueError('Initial candidate hash mismatch: ' + key)
        if request['seed'] != config['seed'] + 1:
            raise ValueError('First proposal seed mismatch: ' + key)
    if requests[1]['internals_exposed']:
        raise ValueError('Source control unexpectedly exposed internals: ' + key)
    snapshot('solver/report.json')
    report = read_json(folder / 'solver/report.json')
    failed = [q for q in report['queries'] if q['result'] in ('sat', 'unknown')]
    evidence = origin
    if shared_pool is not None:
        from .shared_events import ensure_pool
        evidence = ensure_pool(shared_pool.resolve() / key, origin, config, saved['context'], tokenizer)
    for query in failed[:config['max_queries']]:
        snapshot('solver/' + query['file'])
        prefix = 'internals/' + query['id'] + '/'
        process = read_json(contained(evidence, prefix + 'process.json'))
        snapshot(prefix + 'process.json', evidence_root=evidence)
        if process['returncode'] == 0 and not process['timed_out']:
            snapshot(prefix + 'report.json', evidence_root=evidence)
            replay_report = read_json(folder / prefix / 'report.json')
            if replay_report.get('status') == 'completed':
                snapshot(prefix + 'instantiations.jsonl', evidence_root=evidence)
                if config.get('collect_inventory'):
                    snapshot(prefix + 'input-quantifiers.json', evidence_root=evidence)
    # Verify query bytes match the original exposed payload whenever available.
    for query in (saved['internals'] or {}).get('queries', []):
        record = next(q for q in failed if q['id'] == query['id'])
        if digest((folder / 'solver' / record['file']).read_bytes()) != query['query_sha256']:
            raise ValueError('Saved query hash mismatch: ' + key + '/' + query['id'])
    value = internals(folder, code, verification, EMPTY, [], tokenizer, config,
                      replay=False, saved_context=saved['context'])
    def groups(payload):
        return {(q['id'], g['quantifier_smt']) for q in (payload or {}).get('queries', [])
                for g in q['quantifiers']}
    old_groups, new_groups = groups(saved['internals']), groups(value['internals'])
    write_json(folder / 'reuse.json', {'source': str(origin), 'source_artifacts_sha256': copied,
        'common_first_prompt_sha256': common_hash, 'first_seed': config['seed'] + 1,
        'new_replays': 0, 'initial_verifier_calls': 0,
        'shared_initial_events': str(evidence) if shared_pool is not None else None,
        'initial_event_scope': ('shared refreshed replays of the original queries' if shared_pool is not None
                                else 'saved replays from source study'),
        'source_group_count': len(old_groups), 'repacked_group_count': len(new_groups),
        'shared_group_count': len(old_groups & new_groups),
        'newly_exposed_group_count': len(new_groups - old_groups),
        'previously_exposed_groups_now_omitted': len(old_groups - new_groups),
        'source_payload_sha256': digest(json.dumps(saved['internals'], sort_keys=True).encode()),
        'repacked_payload_sha256': digest(json.dumps(value['internals'], sort_keys=True).encode())})
    write_json(folder / 'ready.json', {'initially_verified': verification['success'],
        'published_screens_used': True, 'reference_placebo_restoration_not_rerun': True,
        'initial_candidate_and_events_reused': True})
