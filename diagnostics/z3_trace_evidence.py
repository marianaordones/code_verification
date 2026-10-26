"""Conservative parser for Z3's documented equality-explanation trace format.

https://github.com/Z3Prover/z3/wiki/Equality-Explanation-Logging
attach-enode inside an instance is association, not proof of first creation.
"""
from collections import Counter
import re

REF = re.compile(r'#\d+')


def parse_trace(path, inventory, max_matches=1000, max_nodes=200000):
    nodes, versions, quants, explanations, producers, definitions = {}, {}, {}, {}, {}, {}
    matches, fingerprints, edges = [], {}, []
    stats = Counter()
    inventory_by_qid = {}
    for q in inventory.get('quantifiers', []):
        inventory_by_qid.setdefault(q['qid'], []).append(q)
    active = []

    def ref(key):
        return {'trace_id': key, 'definition_version': versions.get(key),
                'term': term(key), 'resolved': key in nodes}

    def term(key, depth=0, seen=None):
        if depth > 10 or key not in nodes:
            return key
        seen = (seen or set()) | {key}
        op, children = nodes[key]
        values = []
        size = len(op)
        for child in children:
            value = child if child in seen else term(child, depth + 1, seen)
            size += len(value) + 1
            if size > 4000:
                return key + ' [term expansion omitted]'
            values.append(value)
        text = '(' + ' '.join([op, *values]) + ')' if children else op
        return text if len(text) <= 4000 else key + ' [term expansion omitted]'

    def equality_path(key):
        steps, seen = [], set()
        for _ in range(12):
            if key in seen:
                return {'steps': steps, 'complete': False, 'reason': 'cycle'}
            seen.add(key)
            e = explanations.get(key)
            if e is None:
                return {'steps': steps, 'complete': False, 'reason': 'missing explanation'}
            if e['definition_version'] != versions.get(key):
                return {'steps': steps, 'complete': False, 'reason': 'reused ID'}
            if e.get('target_term') and e['target_term']['definition_version'] != versions.get(e['target']):
                return {'steps': steps, 'complete': False, 'reason': 'reused target ID'}
            steps.append(e)
            if e['rule'] == 'root':
                return {'steps': steps, 'complete': True, 'root': key}
            key = e.get('target')
            if key is None:
                break
        return {'steps': steps, 'complete': False, 'reason': 'depth or malformed step'}

    if not path.exists():
        return {'status': 'trace_missing', 'matches': [], 'dependencies': [], 'chains': [], 'counts': {}}
    with path.open(encoding='utf-8', errors='replace') as stream:
        for line_number, raw in enumerate(stream, 1):
            line = raw.strip()
            tag = line.split(']', 1)[0] + ']' if line.startswith('[') else 'unrecognized'
            stats[tag] += 1
            if tag in ('[mk-app]', '[mk-var]', '[mk-quant]', '[mk-lambda]'):
                fields = line.split()
                if len(fields) < 3:
                    stats['malformed_definitions'] += 1
                    continue
                key = fields[1]
                signature = (tag, ' '.join(fields[2:]), tuple((r, versions.get(r))
                    for r in REF.findall(' '.join(fields[2:]))))
                if definitions.get(key) == signature:
                    stats['repeated_identical_definitions'] += 1
                    continue
                if len(nodes) >= max_nodes and key not in nodes:
                    stats['node_cap_omissions'] += 1
                    continue
                if key in nodes:
                    stats['redefined_ids'] += 1
                versions[key] = versions.get(key, 0) + 1
                definitions[key] = signature
                explanations.pop(key, None)
                quants.pop(key, None)
                nodes[key] = (fields[2] if tag == '[mk-app]' else line,
                              REF.findall(line.split(key, 1)[1]) if tag == '[mk-app]' else [])
                if tag == '[mk-quant]':
                    quants[key] = fields[2]
            elif tag == '[attach-meaning]':
                fields = line.split(maxsplit=3)
                if len(fields) == 4 and fields[1] in nodes:
                    nodes[fields[1]] = (fields[3], [])
            elif tag == '[eq-expl]':
                fields = line.split()
                if len(fields) < 3:
                    stats['malformed_equalities'] += 1
                    continue
                key, rule = fields[1:3]
                tail = line.partition(';')[2]
                target = REF.search(tail)
                explanations[key] = {'source': ref(key), 'definition_version': versions.get(key),
                    'rule': rule, 'target': target.group() if target else None,
                    'target_term': ref(target.group()) if target else None,
                    'raw': line, 'line': line_number,
                    'supporting_terms': [ref(x) for x in REF.findall(line.partition(';')[0])[1:]]}
                if rule not in ('root', 'lit', 'cg', 'th'):
                    stats['unknown_equality_rules'] += 1
            elif tag == '[new-match]':
                if len(matches) >= max_matches:
                    stats['match_cap_omissions'] += 1
                    continue
                left, sep, right = line.partition(';')
                fields = left.split()
                if not sep or len(fields) < 4:
                    stats['malformed_matches'] += 1
                    continue
                fingerprint, quantifier, pattern = fields[1:4]
                binding_ids = REF.findall(' '.join(fields[4:]))
                pairs = re.findall(r'\(\s*(#\d+)\s+(#\d+)\s*\)', right)
                top_ids = REF.findall(re.sub(r'\([^)]*\)', '', right))
                qid = quants.get(quantifier)
                candidates = inventory_by_qid.get(qid, [])
                match_id = f'm{len(matches) + 1}'
                equalities = []
                for a, b in pairs:
                    pa, pb = equality_path(a), equality_path(b)
                    equalities.append({'left': ref(a), 'right': ref(b), 'left_path': pa, 'right_path': pb,
                        'same_root_resolved': pa.get('complete') and pb.get('complete') and pa.get('root') == pb.get('root')})
                bindings = [{'bound_term': ref(key), 'path_to_root': equality_path(key)} for key in binding_ids]
                inputs = top_ids + [x for pair in pairs for x in pair]
                match = {'id': match_id, 'line': line_number, 'raw': line, 'fingerprint': fingerprint,
                    'qid': qid, 'quantifier_trace_id': quantifier,
                    'inventory_match': 'unique_qid' if len(candidates) == 1 else 'ambiguous_qid' if candidates else 'unmatched',
                    'input_formula': candidates[0]['quantifier_smt'] if len(candidates) == 1 else None,
                    'input_formula_sha256': candidates[0]['formula_sha256'] if len(candidates) == 1 else None,
                    'formula_scope': 'input formula associated by qid; search formula may be transformed',
                    'trigger': ref(pattern), 'bindings': bindings, 'top_level_matched_terms': [ref(x) for x in top_ids],
                    'equalities_used': equalities, 'instance_count': 0}
                for key in inputs:
                    for producer in producers.get((key, versions.get(key)), []):
                        if len(edges) < 10000:
                            edges.append({'from': producer, 'to': match_id, 'term': ref(key),
                                'evidence': 'earlier attach-enode inside instance; later explicit new-match input',
                                'causal_creation_proven': False})
                        else:
                            stats['edge_cap_omissions'] += 1
                matches.append(match)
                fingerprints[fingerprint] = match_id
            elif tag == '[instance]':
                fields = line.split()
                instance = fingerprints.get(fields[1]) if len(fields) > 1 else None
                active.append(instance)
                if instance:
                    matches[int(instance[1:]) - 1]['instance_count'] += 1
                else:
                    stats['instances_without_saved_match'] += 1
            elif tag == '[end-of-instance]':
                if active:
                    active.pop()
                else:
                    stats['unmatched_instance_ends'] += 1
            elif tag == '[attach-enode]' and active and active[-1]:
                ids = REF.findall(line)
                if ids:
                    key = (ids[0], versions.get(ids[0]))
                    current = producers.setdefault(key, [])
                    if active[-1] not in current and len(current) < 8:
                        current.append(active[-1])
            elif tag in ('[pop]', '[pop-scope]'):
                # Conservative: do not link across an untracked search-scope rollback.
                producers.clear()
                explanations.clear()
                active.clear()
                stats['scope_resets'] += 1
    by_id = {m['id']: m for m in matches}
    # Require an actual instance for both endpoints; retained temporal edges avoid invented cycles.
    edges = [e for e in edges if by_id[e['from']]['instance_count'] and by_id[e['to']]['instance_count']]
    unique = {(e['from'], e['to'], e['term']['trace_id'], e['term']['definition_version']): e for e in edges}
    edges = list(unique.values())
    outgoing = {}
    for edge in edges:
        outgoing.setdefault(edge['from'], []).append(edge)
    chains = []
    for edge in edges:
        for next_edge in outgoing.get(edge['to'], [])[:3]:
            if next_edge['to'] != edge['from']:
                chains.append({'events': [edge['from'], edge['to'], next_edge['to']], 'edges': [edge, next_edge]})
                if len(chains) >= 100:
                    break
        if len(chains) >= 100:
            break
    # Keep short alternatives even when longer chains exist but do not fit the token budget.
    chains += [{'events': [e['from'], e['to']], 'edges': [e]} for e in edges[:max(0, 100-len(chains))]]
    stats.update(matches_saved=len(matches), dependency_edges=len(edges), chains_saved=len(chains),
        matched_input_qid=sum(m['inventory_match'] == 'unique_qid' for m in matches),
        ambiguous_input_qid=sum(m['inventory_match'] == 'ambiguous_qid' for m in matches),
        unmatched_input_qid=sum(m['inventory_match'] == 'unmatched' for m in matches),
        equality_pairs=sum(len(m['equalities_used']) for m in matches),
        equality_pairs_resolved=sum(bool(e['same_root_resolved']) for m in matches for e in m['equalities_used']),
        binding_root_paths_resolved=sum(b['path_to_root']['complete'] for m in matches for b in m['bindings']),
        bindings_with_non_root_steps=sum(any(s['rule'] != 'root' for s in b['path_to_root']['steps'])
                                        for m in matches for b in m['bindings']),
        triggers_resolved=sum(m['trigger']['resolved'] for m in matches),
        matches_with_top_level_terms=sum(bool(m['top_level_matched_terms']) for m in matches),
        unresolved_match_terms=sum(not t['resolved'] for m in matches for t in [m['trigger'], *m['top_level_matched_terms']]))
    return {'status': 'parsed', 'counts': dict(stats), 'matches': matches, 'dependencies': edges, 'chains': chains,
        'semantics': 'Only trace-supported associations. Not a complete causal proof graph or active term database.'}
