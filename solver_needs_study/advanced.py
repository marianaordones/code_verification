"""Advanced replay evidence and globally bounded feedback for the 64k paired study."""
import copy
import json
import sys
import time

from baseline.storage import digest, read_json, write_json
from baseline.verifier import execute
from diagnostics.z3_advanced_pilot import package
from diagnostics.z3_internals import api_env
from diagnostics.z3_trace_evidence import parse_trace
from .feedback import fits, messages
from .reuse import contained


def capture_query(folder, query, config):
    """The validated pilot collector, once per query; raw evidence survives resume."""
    output = contained(folder, 'advanced/' + query['id'])
    path = contained(folder / 'solver', query['file'])
    plan = {'query_sha256': digest(path.read_bytes()),
        'context_sha256': digest((folder / 'source-context.json').read_bytes()),
        'mode': 'combined', 'timeout_ms': config['advanced_timeout_ms'],
        'trace_max_mb': config['advanced_trace_max_mb'], 'capture_schema': 'native-search-v3-native-end-marker'}
    if (output / 'capture-plan.json').exists() and read_json(output / 'capture-plan.json') != plan:
        raise ValueError('Advanced cached query/context changed: ' + str(output))
    write_json(output / 'capture-plan.json', plan)
    process_path = output / 'process.json'
    if process_path.exists():
        call = read_json(process_path)
    else:
        call = execute([sys.executable, '-m', 'diagnostics.z3_advanced_pilot', 'worker',
            '--query', str(path), '--context', str((folder / 'source-context.json').resolve()),
            '--output', str(output), '--mode', 'combined',
            '--timeout-ms', str(config['advanced_timeout_ms']),
            '--max-trace-mb', str(config['advanced_trace_max_mb'])],
            config['advanced_timeout_ms'] / 1000 + 45, env=api_env())
        write_json(process_path, call)
    metadata = {'id': query['id'], 'query_sha256': digest(path.read_bytes()),
        'original_result': query['result'], 'replay_result': None,
        'diagnostic_timeout_ms': config['advanced_timeout_ms'], 'availability': 'unavailable',
        'scope': 'separate combined diagnostic replay, not original or base-package search'}
    if call['returncode'] != 0 or call['timed_out'] or not (output / 'report.json').exists():
        metadata['reason'] = 'worker_failure_or_wall_timeout'
        write_json(output / 'availability.json', metadata)
        return None, [], metadata
    report = read_json(output / 'report.json')
    metadata.update(replay_result=report.get('result'), reason_unknown=report.get('reason_unknown'),
        check_seconds=report.get('check_seconds'), callback_errors=report.get('callback_errors'),
        trace_limit_interrupted=report.get('trace_limit_interrupted'))
    reason = None
    if report.get('capture_schema') != 'native-search-v3-native-end-marker' or not report.get('trace_end_marker'):
        reason = 'unsupported_capture_or_missing_boundary'
    elif report.get('status') != 'completed' or report.get('result') != query['result']:
        reason = 'replay_result_mismatch'
    elif report.get('trace_limit_interrupted'):
        reason = 'trace_limit_interrupted'
    elif report.get('callback_errors') or report.get('clause_serialization_errors'):
        reason = 'callback_or_serialization_errors'
    if reason:
        metadata['reason'] = reason
        write_json(output / 'availability.json', metadata)
        return None, [], metadata
    data = read_json(output / 'input-quantifiers.json')
    if data['ast_node_limit_hit'] or data['quantifiers_not_saved']:
        metadata['reason'] = 'incomplete_input_inventory'
        write_json(output / 'availability.json', metadata)
        return None, [], metadata
    evidence_path = output / 'trace-evidence.json'
    if evidence_path.exists():
        evidence = read_json(evidence_path)
    else:
        evidence = parse_trace(output / 'trace.log', data, end_marker=report['trace_end_marker'])
        write_json(evidence_path, evidence)
    if evidence['status'] != 'parsed':
        metadata['reason'] = evidence['status']
        write_json(output / 'availability.json', metadata)
        return None, [], metadata
    metadata.update(availability='available', reason=None,
        observed_matches=evidence['counts'].get('matches_saved', 0),
        matches_omitted_by_capture_cap=evidence['counts'].get('match_cap_omissions', 0))
    write_json(output / 'availability.json', metadata)
    return evidence, read_json(output / 'clauses.json'), metadata


def merge_queries(records):
    """Namespace every event by query; never build cross-query chains."""
    evidence = {'status': 'parsed', 'matches': [], 'chains': []}
    clauses, queries, buckets = [], [], []
    for data, clause_rows, metadata in records:
        queries.append(metadata)
        if data is None:
            continue
        query_id = metadata['id']
        qualified = lambda key: query_id + ':' + key
        local = []
        for match in data['matches']:
            item = copy.deepcopy(match)
            item.update(id=qualified(match['id']), query_id=query_id)
            local.append(item)
        buckets.append(local)
        for chain in data['chains']:
            item = copy.deepcopy(chain)
            item['query_id'] = query_id
            item['events'] = [qualified(key) for key in chain['events']]
            for edge in item['edges']:
                edge.update({'from': qualified(edge['from']), 'to': qualified(edge['to']), 'query_id': query_id})
            evidence['chains'].append(item)
        clauses.extend({**row, 'query_id': query_id} for row in clause_rows)
    # Round-robin tie order across queries; relevance still has higher priority.
    for depth in range(max((len(b) for b in buckets), default=0)):
        for bucket in buckets:
            if depth < len(bucket):
                item = bucket[depth]
                item['selection_order'] = len(evidence['matches'])
                evidence['matches'].append(item)
    return evidence, clauses, queries


def pack_for_prompt(evidence, clauses, queries, code, verification, action, history, feedback, tokenizer, config):
    context, base, complement = feedback['context'], feedback['internals'], feedback.get('complement')
    shared = {}
    for query in (base or {}).get('queries', []):
        for index, group in enumerate(query.get('quantifiers', [])):
            shared[(query['id'], digest(group['quantifier_smt'].encode()))] = {
                'shared_block': 'solver_internals', 'query_id': query['id'], 'group_index': index}
    for index, item in enumerate((complement or {}).get('quantifiers_without_observed_events', [])):
        shared[(item['query_id'], item['formula_sha256'])] = {
            'shared_block': 'complementary_internals', 'item_index': index}
    # Exact formula hashes only; qid similarity alone never establishes identity.
    linked = []
    for match in evidence['matches']:
        item = dict(match)
        key = (match.get('query_id'), match.get('input_formula_sha256'))
        if key in shared:
            item['shared_formula_reference'] = shared[key]
        linked.append(item)
    evidence = {**evidence, 'matches': linked}
    if not fits(code, verification, action, context, base, history, tokenizer, config, complement=complement):
        raise ValueError('Shared base/complement prompt exceeds 64k; program and shared feedback are not truncated')
    common = messages(code, verification, action, context, base, history, config=config, complement=complement)
    used = len(tokenizer.apply_chat_template(common, tokenize=True, add_generation_prompt=True))
    available = config['max_model_len'] - config['max_tokens'] - used
    target = min(config['advanced_token_budget'], max(0, available - 128))
    metadata = {'queries': queries, 'global_query_limit': config['max_queries'],
        'capture_policy': 'outcome-concordant v3 replays, no trace-cap interruption or callback errors'}
    for _ in range(3):
        if target < 256:
            return None, {'status': 'insufficient_remaining_context', 'remaining_input_tokens': available}
        payload, selection = package(evidence, clauses, context,
            lambda text: len(tokenizer.encode(text, add_special_tokens=False)),
            token_budget=target, metadata=metadata, block=config.get("advanced_block"))
        selection['remaining_input_tokens_before_advanced'] = available
        if payload is None:
            return None, selection
        if not any(payload.get(key) for key in ('matching', 'chains', 'non_inst_clauses')):
            return None, {**selection, 'status': 'no_new_events_fit_or_available'}
        if fits(code, verification, action, context, base, history, tokenizer, config,
                complement=complement, advanced=payload):
            prompt = messages(code, verification, action, context, base, history, config=config,
                              complement=complement, advanced=payload)
            selection['actual_prompt_tokens'] = len(tokenizer.apply_chat_template(
                prompt, tokenize=True, add_generation_prompt=True))
            return payload, selection
        actual = len(tokenizer.apply_chat_template(messages(code, verification, action, context,
            base, history, config=config, complement=complement, advanced=payload),
            tokenize=True, add_generation_prompt=True))
        target -= max(128, actual + config['max_tokens'] - config['max_model_len'] + 64)
    return None, {'status': 'advanced_omitted_after_exact_context_checks', 'remaining_input_tokens': available}


def attach(folder, code, verification, action, history, tokenizer, config, feedback):
    if 'advanced' in feedback and not config.get('advanced_blocks'):
        return feedback
    if config.get('advanced_blocks') and 'advanced_variants' in feedback:
        return feedback
    started = time.perf_counter()
    records = []
    original = read_json(folder / 'solver/report.json')
    base_ids = {q['id'] for q in (feedback.get('internals') or {}).get('queries', [])}
    for query in original['queries']:
        if query['id'] in base_ids and len(records) < config['max_queries']:
            records.append(capture_query(folder, query, config))
    evidence, clauses, queries = merge_queries(records)
    if config.get('advanced_blocks'):
        variants = {}
        for block in config['advanced_blocks']:
            payload, selection = pack_for_prompt(evidence, clauses, queries, code, verification, action,
                history, feedback, tokenizer, {**config, 'advanced_block': block})
            variants[block] = {'payload': payload, 'selection': selection}
        result = {**feedback, 'advanced_variants': variants, 'advanced_queries': queries,
                  'advanced_processing_seconds': time.perf_counter() - started}
        write_json(folder / 'feedback.json', result)
        return result
    payload, selection = pack_for_prompt(evidence, clauses, queries, code, verification, action,
        history, feedback, tokenizer, config)
    result = {**feedback, 'advanced': payload, 'advanced_selection': selection,
              'advanced_queries': queries, 'advanced_processing_seconds': time.perf_counter() - started}
    write_json(folder / 'advanced-selection.json', selection)
    write_json(folder / 'feedback.json', result)
    return result
