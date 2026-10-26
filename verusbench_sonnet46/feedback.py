"""Existing ranked diagnostic replay policy with explicit 14k / 50x3 limits."""
import copy
import json
import sys

from baseline.internals import STATISTICS
from baseline.storage import read_json, write_json
from baseline.verifier import execute
from diagnostics.z3_internals import api_env
from repair_study.relevance import rank, source_context


def block(payload):
    return '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>'


def build_payload(folder, original, candidate, verification, integrity, tokenizer, config,
                  progress='', *, prompt_builder):
    destination = folder / 'payload.json'
    if destination.exists():
        return read_json(destination)
    context = source_context(candidate, verification)
    write_json(folder / 'source-context.json', context)
    report = read_json(folder / 'solver/report.json')
    selected = next((q for q in report['queries'] if q['result'] in ('sat', 'unknown')), None)
    replay = {'status': 'not_run'}
    output = folder / 'relevant-replay'
    if selected:
        call = execute([sys.executable, '-m', 'repair_study.worker', '--query',
            str((folder / 'solver' / selected['file']).resolve()), '--context',
            str((folder / 'source-context.json').resolve()), '--output', str(output.resolve())], 20, env=api_env())
        write_json(output / 'process.json', call)
        if call.get('returncode') == 0 and not call.get('timed_out') and (output / 'report.json').exists():
            replay = read_json(output / 'report.json')
    concordant = selected is not None and replay.get('status') == 'completed' and replay.get('result') == selected['result']
    payload = {'schema': 'relevant-internals-14k-50x3-v1', 'scope': 'diagnostic_replay_not_original_search',
        'availability': 'available' if concordant else 'unavailable',
        'original_result': selected['result'] if selected else None, 'replay_result': replay.get('result'),
        'reason_unknown': replay.get('reason_unknown'), 'diagnostic_timeout_ms': 5000,
        'unavailability_reason': None if concordant else 'no_query_replay_failure_or_result_mismatch',
        'source_context': context,
        'statistics': {k: replay.get('statistics', {}).get(k) if concordant else None for k in STATISTICS},
        'sampling': {'policy': 'ranked; diversity before repeated instances; heuristic qid categories',
                     'query_limit': 1, 'max_quantifiers': config['max_quantifiers'],
                     'max_instances_each': config['max_instances_each'],
                     'observed_instances': replay.get('instantiations_observed'),
                     'saved_instances': replay.get('instantiations_saved'), 'callback_errors': replay.get('callback_errors'),
                     'selected_groups': 0, 'selected_instances': 0}, 'quantifiers': []}
    history = json.loads(progress) if progress else []

    def fits(value):
        if len(tokenizer.encode(block(value), add_special_tokens=False)) > config['internals_token_budget']:
            return False
        prompt = prompt_builder(original, candidate, verification, integrity, value, history)
        return len(tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True)) + config['max_tokens'] <= config['max_model_len']

    if not fits(payload):
        raise ValueError('Minimum feedback/prompt exceeds budget; no truncation permitted')
    events = []
    if concordant and (output / 'instantiations.jsonl').exists():
        events = [json.loads(line) for line in (output / 'instantiations.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    groups = {}
    for event in events:
        formula = event['quantifier_smt']
        if formula not in groups:
            score, category = rank(formula, context)
            groups[formula] = {'rank': score, 'category': category, 'events': []}
        if event not in groups[formula]['events']:
            groups[formula]['events'].append(event)
    chosen, categories = {}, {}
    for depth in range(config['max_instances_each']):
        for formula, group in sorted(groups.items(), key=lambda item: item[1]['rank']):
            if depth >= len(group['events']):
                continue
            category = group['category']
            if formula not in chosen and (len(chosen) >= config['max_quantifiers'] or
                    category in ('representation', 'other_background') and categories.get(category, 0) >= 2):
                continue
            trial = copy.deepcopy(payload)
            item = next((g for g in trial['quantifiers'] if g['quantifier_smt'] == formula), None)
            if item is None:
                item = {'id': f'Q{len(chosen) + 1}', 'selection_category': category,
                        'quantifier_smt': formula, 'instances': []}
                trial['quantifiers'].append(item)
            item['instances'].append({k: group['events'][depth][k] for k in
                                      ('binding_terms_callback_order', 'clause_literals_smt')})
            trial['sampling']['selected_groups'] = len(trial['quantifiers'])
            trial['sampling']['selected_instances'] = sum(len(g['instances']) for g in trial['quantifiers'])
            if fits(trial):
                payload = trial
                if formula not in chosen:
                    chosen[formula] = True
                    categories[category] = categories.get(category, 0) + 1
    payload['token_count_method'] = 'pinned Qwen tokenizer, including solver_internals wrapper'
    # Metadata is itself part of the budget; remove it if it would overflow.
    if not fits(payload):
        payload.pop('token_count_method')
    write_json(destination, payload)
    return payload
