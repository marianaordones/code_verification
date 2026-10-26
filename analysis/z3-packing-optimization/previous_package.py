def package(evidence, clauses, context, encode):
    """Hard combined 14k cap; preferred shares 6k matching, 3k chains, 5k clauses."""
    payload = {'scope': 'diagnostic replay, not original Verus search', 'matching': [],
               'chains': [], 'non_inst_clauses': [], 'referenced_matches': {}, 'formulas': {}}
    limits = {'matching': (12, 6144), 'chains': (6, 3072), 'non_inst_clauses': (24, 5120)}
    matches = {m['id']: m for m in evidence['matches']}
    def relevance(m):
        return rank((m.get('input_formula') or '') + ' :qid ' + (m.get('qid') or ''), context)[0]
    def compact(m):
        def path(p):
            return {'complete_root_path_in_audit': p.get('complete', False), 'root': p.get('root'),
                'reason': p.get('reason'), 'steps_raw': [s['raw'] for s in p['steps'][:3]],
                'steps_omitted': max(0, len(p['steps']) - 3)}
        return {'id': m['id'], 'qid': m['qid'], 'inventory_match': m['inventory_match'],
            'formula_ref': m['input_formula_sha256'], 'trigger': m['trigger'],
            'bindings': [{'bound_term': b['bound_term'], 'path_to_root': path(b['path_to_root'])} for b in m['bindings']],
            'top_level_matched_terms': m['top_level_matched_terms'], 'instance_count': m['instance_count'],
            'equalities_used': [{'left': e['left'], 'right': e['right'],
                'left_path': path(e['left_path']), 'right_path': path(e['right_path']),
                'same_root_resolved_in_audit': e['same_root_resolved']} for e in m['equalities_used'][:3]],
            'equality_pairs_omitted': max(0, len(m['equalities_used']) - 3)}
    pools = {'matching': sorted(matches.values(), key=lambda m: (relevance(m), m['line'])),
        'chains': sorted(evidence['chains'], key=lambda c: min(relevance(matches[i]) for i in c['events'])),
        'non_inst_clauses': clauses}
    omissions = Counter()
    if encode is None:
        return None, {'status': 'tokenizer_unavailable; package not budgeted', 'available': {k: len(v) for k, v in pools.items()}}
    import copy
    current_tokens = block_cost(payload, encode)['tokens']
    spent = Counter()
    # First enforce preferred shares, then allow unused space to be borrowed.
    added = {k: set() for k in pools}
    for borrow in (False, True):
        for name, pool in pools.items():
            count_limit, share = limits[name]
            for index, item in enumerate(pool):
                if index in added[name] or len(payload[name]) >= count_limit:
                    continue
                trial = copy.deepcopy(payload)
                if name == 'matching':
                    trial['referenced_matches'].pop(item['id'], None)
                    selected_item = compact(item)
                    if item['input_formula_sha256']:
                        trial['formulas'][item['input_formula_sha256']] = item['input_formula']
                else:
                    selected_item = item
                if name == 'chains':
                    # Small references, but all referenced events must accompany the chain.
                    for match_id in item['events']:
                        if not any(m['id'] == match_id for m in trial['matching']):
                            trial['referenced_matches'][match_id] = compact(matches[match_id])
                        m = matches[match_id]
                        if m['input_formula_sha256']:
                            trial['formulas'][m['input_formula_sha256']] = m['input_formula']
                trial[name].append(selected_item)
                trial_tokens = block_cost(trial, encode)['tokens']
                delta = max(0, trial_tokens - current_tokens)
                if (borrow or spent[name] + delta <= share) and trial_tokens <= BUDGETS['new_blocks']:
                    payload = trial
                    current_tokens = trial_tokens
                    spent[name] += delta
                    added[name].add(index)
    for name, pool in pools.items():
        omissions[name] = len(pool) - len(payload[name])
    return payload, {'status': 'budgeted', 'limits': limits, 'available': {k: len(v) for k, v in pools.items()},
                     'selected': {k: len(payload[k]) for k in pools}, 'omitted': dict(omissions),
                     'actual_tokens': block_cost(payload, encode)['tokens']}
