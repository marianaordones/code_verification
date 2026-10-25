"""Bounded input-quantifier evidence, never a claim about solver elimination."""
from collections import Counter
import copy

from baseline.storage import digest, read_json
from repair_study.relevance import rank


def build(folder, context, base, tokenizer, config, prompt_fits):
    if not (base or {}).get('queries'):
        return None
    payload = {'scope': 'diagnostic replay; loaded input AST, not original Verus search',
               'absence_meaning': 'no callback instantiation observed; elimination/activation unknown',
               'queries': [], 'quantifiers_without_observed_events': [],
               'selection': {'eligible': 0, 'selected': 0, 'ambiguous_or_missing_qid': 0,
                             'budget_omissions': 0, 'limit_omissions': 0,
                             'oversized_formula_omissions': 0}}
    candidates = []
    for query in (base or {}).get('queries', []):
        path = folder / 'internals' / query['id']
        if not (path / 'input-quantifiers.json').exists():
            raise ValueError('Inventory evidence missing: ' + str(path))
        data, report = read_json(path / 'input-quantifiers.json'), read_json(path / 'report.json')
        exact, outer = report['instantiations_by_exact_formula'], report['instantiations_by_outer_qid']
        frequency = Counter(q['qid'] for q in data['quantifiers'] if q['qid'])
        matching = {m['formula_sha256']: m for m in data['matching']}
        incomplete = data['ast_node_limit_hit'] or bool(data['quantifiers_not_saved'])
        zero = 0
        for q in data['quantifiers']:
            if incomplete or report['callback_errors']:
                continue
            if exact.get(q['formula_sha256'], 0):
                continue
            if not q['qid'] or frequency[q['qid']] != 1:
                payload['selection']['ambiguous_or_missing_qid'] += 1
                continue
            if outer.get(q['qid'], 0):
                continue
            zero += 1
            score, category = rank(q['quantifier_smt'] or '', context)
            # Prefer source and operation-related formulas; exclude representation noise.
            if category not in ('candidate_annotation', 'candidate_definition', 'operation_related_library'):
                continue
            payload['selection']['eligible'] += 1
            if not q['quantifier_smt']:
                payload['selection']['oversized_formula_omissions'] += 1
                continue
            item = {**q, 'query_id': query['id'], 'selection_category': category,
                    'observed_exact_formula_events': 0, 'observed_unique_qid_events': 0,
                    'observation_status': 'no_event_observed',
                    'input_term_examples': [{**t, 'examples_smt': t['examples_smt'][:2]}
                        for t in matching[q['formula_sha256']]['terms_by_same_root_symbol']]}
            # Patterns already occur in quantifier_smt: do not repeat their text.
            item.pop('explicit_patterns_smt', None)
            candidates.append(((score, query['id'], q['formula_sha256']), item))
        payload['queries'].append({'id': query['id'], 'input_quantifiers_found': data['quantifiers_found'],
            'inventory_incomplete': incomplete,
            'no_events_observed_with_unique_qid': zero, 'callback_errors': report['callback_errors'],
            'observed_profile_for_base_groups': [
                {'base_group_index': index, 'formula_sha256': digest(group['quantifier_smt'].encode()),
                 'observed_exact_formula_events': exact.get(digest(group['quantifier_smt'].encode()), 0),
                 'saved_instances_exposed_in_base': len(group['instances'])}
                for index, group in enumerate(query.get('quantifiers', []))]})
    if not prompt_fits(payload):
        return None
    library = 0
    for _, item in sorted(candidates, key=lambda pair: pair[0]):
        if len(payload['quantifiers_without_observed_events']) >= config['max_unobserved_quantifiers'] or (
                item['selection_category'] == 'operation_related_library' and library >= 2):
            payload['selection']['limit_omissions'] += 1
            continue
        trial = copy.deepcopy(payload)
        trial['quantifiers_without_observed_events'].append(item)
        trial['selection']['selected'] += 1
        if prompt_fits(trial):
            payload = trial
            library += item['selection_category'] == 'operation_related_library'
        else:
            payload['selection']['budget_omissions'] += 1
    # Counters grow during selection; validate the final serialized object too.
    while payload['quantifiers_without_observed_events'] and not prompt_fits(payload):
        payload['quantifiers_without_observed_events'].pop()
        payload['selection']['selected'] -= 1
        payload['selection']['budget_omissions'] += 1
    return payload if prompt_fits(payload) else None
