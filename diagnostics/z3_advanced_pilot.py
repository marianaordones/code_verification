"""Capability audit of matching/equality traces, instance links, and non-inst clauses.

No Verus or model invocation. Every replay is a fresh process using Z3 4.12.5.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import statistics
import sys
import threading
import time
import uuid

from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json, write_text
from baseline.verifier import execute
from diagnostics.z3_feedback_pilot import CONTROLS, inventory, offline_tokenizer, block_cost
from diagnostics.z3_internals import api_env, api_identity, identity
from diagnostics.z3_probe import head, snapshots
from diagnostics.z3_trace_evidence import parse_trace
from repair_study.relevance import rank, source_context

MODES = ('baseline', 'callback', 'trace', 'combined')
ALL_MODES = (*MODES, 'combined_proof')
# Fixed diagnostic sample: includes both cases previously hitting the trace cap.
FIVE_PROBLEMS = ('V-329', 'V-444', 'V-381', 'V-245', 'V-368')
BUDGETS = {'context': 65536, 'base': 24576, 'previous_complement': 12288,
           'new_blocks': 14336, 'output': 4096, 'program_and_other_input': 10240}
CONTROL_CHAIN = '''(declare-fun f (Int) Int) (declare-fun g (Int) Int)
(declare-const a Int) (declare-const b Int) (assert (= a b))
(assert (forall ((x Int)) (! (= (g (f x)) x) :pattern ((f x)) :qid user_candidate_chain1)))
(assert (forall ((x Int)) (! (> (g x) 0) :pattern ((g x)) :qid user_candidate_chain2)))
(assert (= (f a) b)) (assert (< b 0)) (check-sat)'''


def query_prefix(path):
    text = path.read_text(encoding='utf-8')
    if re.search(r'\(set-option\s+:(?:trace(?:_file_name)?|proof|solver\.proof\.log)\b', text):
        raise ValueError('Input controls trace/proof settings; no silent override permitted')
    checks = list(snapshots(text))
    if len(checks) != 1 or head(checks[0][1]) != 'check-sat':
        raise ValueError('Requires one plain check-sat, without approximating assumptions/tactics')
    return checks[0][0]


def collect_inventory(args):
    started = time.perf_counter()
    identity()
    import z3
    z3.set_param('trace', False)
    solver = z3.Solver()
    solver.from_string(query_prefix(args.query))
    data = inventory(solver.assertions(), z3)
    data['source_query_sha256'] = digest(args.query.read_bytes())
    data['collection_scope'] = 'separate non-traced input inventory; no check-sat'
    data['collection_seconds'] = time.perf_counter() - started
    write_json(args.output / 'input-quantifiers.json', data)
    return 0


def worker(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    callbacks = args.mode in ('callback', 'combined', 'combined_proof')
    trace = args.mode in ('trace', 'combined', 'combined_proof')
    proof = args.mode == 'combined_proof'
    report = {'status': 'unavailable', 'mode': args.mode, 'timeout_ms': args.timeout_ms,
        'overrides': {'timeout_ms': args.timeout_ms, 'trace': trace, 'proof': proof},
        'callback_errors': 0, 'rules_observed': {}, 'non_inst_clauses_observed': 0,
        'oversized_clauses_omitted': 0, 'clause_sample_omissions': 0, 'trace_limit_interrupted': False,
        'capture_schema': 'native-search-v3-native-end-marker', 'deferred_ast_serialization': True}
    clauses, stop = [], threading.Event()
    try:
        report['z3'] = identity()
        import z3
        # Prepare the inventory before enabling trace. The normal driver does this
        # ONCE in a separate process; standalone workers use a silent context.
        z3.set_param('trace', False)
        started = time.perf_counter()
        inventory_path = getattr(args, 'inventory_file', None)
        if inventory_path:
            data = read_json(inventory_path)
            if data.get('source_query_sha256') != digest(args.query.read_bytes()):
                raise ValueError('Inventory belongs to another query')
        else:
            silent = z3.Solver(ctx=z3.Context())
            silent.from_string(query_prefix(args.query))
            data = inventory(silent.assertions(), z3)
            data['source_query_sha256'] = digest(args.query.read_bytes())
            data['collection_scope'] = 'separate silent context, same input; no check-sat'
        write_json(output / 'input-quantifiers.json', data)
        report['inventory_seconds'] = time.perf_counter() - started
        report['inventory_scope'] = data['collection_scope']
        z3.set_param('trace', trace)
        z3.set_param('proof', proof)
        if trace:
            z3.set_param('trace_file_name', str(output / 'trace.log'))
        # A fresh explicit context is essential: the inventory context is silent.
        context = z3.Context()
        solver = z3.Solver(ctx=context)
        solver.from_string(query_prefix(args.query))
        solver.set(timeout=args.timeout_ms)
        from diagnostics.z3_clause_capture import ClauseCapture
        collector = ClauseCapture(z3, read_json(args.context), report)
        callback = z3.OnClause(solver, collector) if callbacks else None

        def monitor():
            while not stop.wait(0.05):
                path = output / 'trace.log'
                if trace and path.exists() and path.stat().st_size > args.max_trace_mb * 1024**2:
                    report['trace_limit_interrupted'] = True
                    solver.interrupt()
                    return

        guard = threading.Thread(target=monitor, daemon=True)
        guard.start()
        started = time.perf_counter()
        result = solver.check()
        elapsed = time.perf_counter() - started
        stop.set()
        guard.join(timeout=1)
        # The native stream is buffered: stat().st_size is NOT a reliable search
        # boundary. Emit a unique native AST marker, then parse up to that record
        # after process exit, when the stream has been flushed completely.
        trace_path = output / 'trace.log'
        report['trace_search_end_bytes'] = trace_path.stat().st_size if trace_path.exists() else 0
        if trace:
            marker_name = '__z3_pilot_capture_end_' + uuid.uuid4().hex
            marker_ast = z3.Bool(marker_name, ctx=context)
            report['trace_end_marker'] = marker_name
        z3.set_param('trace', False)
        report.update(status='completed', result=str(result), check_seconds=elapsed,
            reason_unknown=solver.reason_unknown() if result == z3.unknown else None,
            statistics={key: value for key, value in solver.statistics()})
        started = time.perf_counter()
        clauses = collector.serialize(render_context=z3.Context()) if callbacks else []
        report['clause_serialization_seconds'] = time.perf_counter() - started
        report['clause_serialization_context'] = 'captured ASTs translated into a separate non-traced context'
        assert not callbacks or callback is not None
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        stop.set()
    try:
        import resource
        report['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        report['peak_rss_kib'] = None
    write_json(output / 'clauses.json', clauses)
    write_json(output / 'report.json', report)
    return 0 if report['status'] == 'completed' else 1


def select_cases(study, per_category=3, controls_only=False, problem_ids=FIVE_PROBLEMS, include_controls=False):
    controls = {**CONTROLS, 'matching_equality_chain': ('unsat', CONTROL_CHAIN)}
    cases = [{'id': name, 'kind': 'control', 'original_result': None, 'expected_result': expected,
              'context': {}, 'query_text': text + '\n'} for name, (expected, text) in controls.items()]
    skipped = []
    if controls_only:
        return cases, skipped
    if not include_controls:
        cases = []
    manifest = read_json(study / 'manifest.json')
    if problem_ids is not None:
        if len(set(problem_ids)) != len(problem_ids):
            raise ValueError('Problem IDs must be unique')
        missing = set(problem_ids) - {row['id'] for row in manifest['cases']}
        if missing:
            raise ValueError('Problems missing from source manifest: ' + ', '.join(sorted(missing)))
    for label in ('AX', 'INST-forall', 'INST-witness', 'NLA', 'FUEL', 'Other'):
        requested = per_category if problem_ids is None else sum(
            row['paper_label'] == label and row['id'] in problem_ids for row in manifest['cases'])
        if requested == 0:
            continue
        count = 0
        for row in manifest['cases']:
            if row['paper_label'] != label or problem_ids is not None and row['id'] not in problem_ids:
                continue
            folder = study / 'inputs' / row['id']
            report = folder / 'solver/report.json'
            if not report.exists():
                continue
            for query in read_json(report)['queries']:
                if query['result'] not in ('sat', 'unknown'):
                    continue
                source = (folder / 'solver' / query['file']).resolve()
                if not source.is_relative_to((folder / 'solver').resolve()):
                    raise ValueError('Query escapes saved source folder')
                text = source.read_text(encoding='utf-8')
                checks = list(snapshots(text))
                if len(checks) != 1 or head(checks[0][1]) != 'check-sat':
                    continue
                code = (folder / 'candidate.rs').read_text(encoding='utf-8')
                cases.append({'id': label + '-' + row['id'], 'kind': 'verus_saved_query',
                    'paper_label': label, 'problem_id': row['id'], 'source_query_id': query['id'],
                    'original_result': query['result'], 'expected_result': None, 'source': str(source),
                    'context': source_context(code, read_json(folder / 'verification.json')), 'query_text': text})
                count += 1
                break
            if count == requested:
                break
        if count < requested:
            skipped.append({'label': label, 'requested': requested, 'found': count})
    return cases, skipped


def package(evidence, clauses, context, encode, *, token_budget=None, metadata=None, block=None):
    """Cache bounded candidate costs; tokenize the assembled package only at the end."""
    payload = {'scope': 'diagnostic replay, not original Verus search', 'matching': [],
               'chains': [], 'non_inst_clauses': [], 'referenced_matches': {}, 'formulas': {}}
    token_budget = BUDGETS['new_blocks'] if token_budget is None else token_budget
    if metadata:
        if set(metadata) & set(payload):
            raise ValueError('Metadata cannot replace feedback sections')
        payload.update(metadata)
    limits = {'matching': (12, 7168), 'chains': (6, 4096), 'non_inst_clauses': (24, 3072)}
    if block is not None:
        if block not in limits:
            raise ValueError('Unknown advanced block: ' + block)
        counts = {'matching': 48, 'chains': 24, 'non_inst_clauses': 96}
        limits = {name: (counts[name] if name == block else 0, token_budget if name == block else 0) for name in limits}
    matches = {m['id']: m for m in evidence['matches']}
    relevance_cache = {}
    def relevance(m):
        key = (m.get('input_formula') or '', m.get('qid') or '')
        if key not in relevance_cache:
            relevance_cache[key] = rank(key[0] + ' :qid ' + key[1], context)[0]
        return relevance_cache[key]
    def compact(m):
        def path(p):
            return {'complete_root_path_in_audit': p.get('complete', False), 'root': p.get('root'),
                'reason': p.get('reason'), 'steps_raw': [s['raw'] for s in p['steps'][:3]],
                'steps_omitted': max(0, len(p['steps']) - 3)}
        return {'id': m['id'], 'qid': m['qid'], 'inventory_match': m['inventory_match'],
            **({'query_id': m['query_id']} if m.get('query_id') is not None else {}),
            'formula_ref': m['input_formula_sha256'], 'trigger': m['trigger'],
            'bindings': [{'bound_term': b['bound_term'], 'path_to_root': path(b['path_to_root'])} for b in m['bindings']],
            'top_level_matched_terms': m['top_level_matched_terms'], 'instance_count': m['instance_count'],
            'equalities_used': [{'left': e['left'], 'right': e['right'],
                'left_path': path(e['left_path']), 'right_path': path(e['right_path']),
                'same_root_resolved_in_audit': e['same_root_resolved']} for e in m['equalities_used'][:3]],
            'equality_pairs_omitted': max(0, len(m['equalities_used']) - 3)}
    scores = {key: relevance(m) for key, m in matches.items()}
    pools = {'matching': sorted(matches.values(), key=lambda m: (scores[m['id']],
        m.get('inventory_match') != 'unique_qid', not m.get('instance_count'), m.get('selection_order', m['line']))),
        'chains': sorted(evidence['chains'], key=lambda c: (min(scores[i] for i in c['events']), len(c['events']))),
        'non_inst_clauses': []}
    duplicate_clauses, clause_keys = 0, set()
    for clause in clauses:
        key = (clause.get('query_id'), clause.get('rule'), clause.get('hint_smt'), tuple(clause.get('dependencies', [])),
               tuple(sorted(set(clause.get('clause_literals_smt', [])))))
        if key in clause_keys:
            duplicate_clauses += 1
        else:
            clause_keys.add(key)
            pools['non_inst_clauses'].append(clause)
    available = {k: len(v) for k, v in pools.items()}
    if evidence.get('status', 'parsed') not in ('parsed', 'trace_missing'):
        return None, {'status': 'invalid_trace; no package', 'trace_status': evidence['status'], 'available': available}
    if encode is None:
        return None, {'status': 'tokenizer_unavailable; package not budgeted', 'available': available}
    caps = {'matching': 64, 'chains': 24, 'non_inst_clauses': 64}
    if block is not None:
        caps = {'matching': 192, 'chains': 96, 'non_inst_clauses': 256}
    pools = {k: v[:caps[k]] if block is None or k == block else [] for k, v in pools.items()}
    compact_cache, token_cache = {}, {}
    encoder_calls, encoded_characters, exact_checks = 0, 0, 0

    def measured(value):
        nonlocal encoder_calls, encoded_characters
        text = json.dumps(value, ensure_ascii=False, indent=2)
        encoder_calls += 1
        encoded_characters += len(text)
        return encode(text)

    def cached(key, value):
        if key not in token_cache:
            token_cache[key] = measured(value)
        return token_cache[key]

    def event(key):
        if key not in compact_cache:
            compact_cache[key] = compact(matches[key])
        return compact_cache[key]

    selected = {name: [] for name in pools}
    referenced, formulas, history, spent = set(), set(), [], Counter()
    estimated_tokens = measured(payload)
    if estimated_tokens > token_budget:
        return None, {'status': 'insufficient_token_budget', 'available': available,
                      'minimum_tokens': estimated_tokens, 'token_budget': token_budget}
    reserve = 256

    def added_cost(name, index):
        item = pools[name][index]
        ids = [item['id']] if name == 'matching' else item['events'] if name == 'chains' else []
        delta = 48
        if name == 'chains':
            delta += cached(('chain', index), item)
        elif name == 'non_inst_clauses':
            delta += cached(('clause', index), item)
        new_formulas = set()
        for key in ids:
            if key not in referenced:
                delta += cached(('match', key), event(key)) + 16
                formula = matches[key].get('input_formula_sha256')
                if formula and formula not in formulas and formula not in new_formulas:
                    delta += cached(('formula', formula), {formula: matches[key].get('shared_formula_reference') or matches[key]['input_formula']})
                    new_formulas.add(formula)
        return delta, ids, new_formulas

    def try_add(name, index, borrow):
        nonlocal estimated_tokens
        if index in selected[name] or len(selected[name]) >= limits[name][0]:
            return False
        delta, ids, new_formulas = added_cost(name, index)
        if estimated_tokens + delta > token_budget - reserve or (
                not borrow and spent[name] + delta > limits[name][1]):
            return False
        selected[name].append(index)
        history.append((name, index))
        referenced.update(ids)
        formulas.update(new_formulas)
        estimated_tokens += delta
        spent[name] += delta
        return True

    # Seed each available block before filling it, so large matching packages do
    # not systematically starve chains. Still omit an item that cannot fit whole.
    for name, pool in pools.items():
        for index in range(len(pool)):
            if try_add(name, index, False):
                break
    for borrow in (False, True):
        for name, pool in pools.items():
            for index in range(len(pool)):
                try_add(name, index, borrow)

    def assemble():
        value = {**payload, 'matching': [], 'chains': [], 'non_inst_clauses': [],
                 'referenced_matches': {}, 'formulas': {}}
        match_ids = {pools['matching'][i]['id'] for i in selected['matching']}
        wanted = set(match_ids)
        value['matching'] = [event(pools['matching'][i]['id']) for i in selected['matching']]
        value['chains'] = [pools['chains'][i] for i in selected['chains']]
        value['non_inst_clauses'] = [pools['non_inst_clauses'][i] for i in selected['non_inst_clauses']]
        for chain in value['chains']:
            wanted.update(chain['events'])
        value['referenced_matches'] = {key: event(key) for key in sorted(wanted - match_ids)}
        for key in sorted(wanted):
            match = matches[key]
            if match.get('input_formula_sha256'):
                value['formulas'][match['input_formula_sha256']] = match.get('shared_formula_reference') or match['input_formula']
        return value

    # Additive BPE costs are estimates only. Exact full JSON measurement is the
    # authority; remove whole units until it fits, including their unused refs.
    while True:
        payload = assemble()
        actual_tokens = measured(payload)
        exact_checks += 1
        if actual_tokens <= token_budget:
            break
        removable = next(((name, i) for name, i in reversed(history)
            if i in selected[name] and len(selected[name]) > 1), None)
        if removable is None:
            removable = next(((name, i) for name, i in reversed(history) if i in selected[name]), None)
        if removable is None:
            raise ValueError('Even empty feedback exceeds token budget')
        selected[removable[0]].remove(removable[1])
    return payload, {'status': 'budgeted', 'limits': limits, 'available': available,
        'considered': {name: len(pool) for name, pool in pools.items()},
        'candidate_caps': caps, 'duplicate_clauses_removed': duplicate_clauses,
        'selected': {name: len(selected[name]) for name in pools},
        'omitted': {name: available[name] - len(selected[name]) for name in pools},
        'actual_tokens': actual_tokens, 'token_budget': token_budget,
        'estimated_tokens_before_final_check': estimated_tokens,
        'encoder_calls': encoder_calls, 'encoded_characters': encoded_characters,
        'exact_package_checks': exact_checks, 'selection_policy': 'cached item costs; bounded ranked candidates; final exact token check'}


def analyze_case(case, folder, records, encode, measure_all_tokens=False):
    def bulk_cost(value):
        result = block_cost(value, encode if measure_all_tokens else None)
        result['token_measurement'] = 'measured' if encode and measure_all_tokens else 'disabled' if encode else 'unavailable'
        if encode and not measure_all_tokens:
            result['tokenizer'] = 'available; bulk token measurement disabled (use --measure-all-tokens)'
        return result
    timings = {}
    for mode in (m for m in ALL_MODES if any(r['mode'] == m for r in records)):
        rows = [r for r in records if r['mode'] == mode and r['report'].get('status') == 'completed']
        baseline = {r['rep']: r for r in records if r['mode'] == 'baseline' and r['report'].get('status') == 'completed'}
        pairs = [(r, baseline[r['rep']]) for r in rows if r['rep'] in baseline]
        timings[mode] = {'completed': len(rows), 'results': dict(Counter(r['report']['result'] for r in rows)),
            'reasons': dict(Counter(r['report'].get('reason_unknown') or 'none' for r in rows)),
            'median_check_seconds': statistics.median(r['report']['check_seconds'] for r in rows) if rows else None,
            'median_process_seconds': statistics.median(r['process']['seconds'] for r in rows) if rows else None,
            'median_inventory_seconds': statistics.median(r['report']['inventory_seconds'] for r in rows) if rows else None,
            'outcome_mismatches': sum(a['report']['result'] != b['report']['result'] for a, b in pairs),
            'reason_mismatches': sum(a['report'].get('reason_unknown') != b['report'].get('reason_unknown') for a, b in pairs),
            'trace_limit_interruptions': sum(r['report']['trace_limit_interrupted'] for r in rows)}
        base_time = timings.get('baseline', {}).get('median_check_seconds')
        timings[mode]['time_ratio_to_baseline'] = timings[mode]['median_check_seconds'] / base_time if base_time and rows else None
    output = {'id': case['id'], 'kind': case['kind'], 'timings': timings,
        'original_result': case['original_result'], 'expected_result': case['expected_result'],
        'runs': [], 'failures': [r['path'] for r in records if r['report'].get('status') != 'completed'],
        'failure_details': [{'path': r['path'], 'error': r['report'].get('error'),
            'returncode': r['process']['returncode'], 'wall_timeout': r['process']['timed_out'],
            'stderr_excerpt': r['process'].get('stderr', '')[-2000:]}
            for r in records if r['report'].get('status') != 'completed'], 'semantic_control_errors': []}
    for record in records:
        path = Path(record['path'])
        if record['report'].get('status') != 'completed':
            continue
        started = time.perf_counter()
        data = read_json(path / 'input-quantifiers.json')
        marker = record['report'].get('trace_end_marker')
        evidence = parse_trace(path / 'trace.log', data, end_marker=marker,
            end_bytes=None if marker else record['report'].get('trace_search_end_bytes'))
        write_json(path / 'trace-evidence.json', evidence)
        parsing_seconds = time.perf_counter() - started
        clauses = read_json(path / 'clauses.json')
        started = time.perf_counter()
        payload, selection = package(evidence, clauses, case['context'], encode)
        packaging_seconds = time.perf_counter() - started
        write_json(path / 'new-feedback-14k.json', payload)
        if record['mode'] in ('trace', 'combined', 'combined_proof'):
            wanted = {'unsat_quantified': {'control_nonnegative'},
                'matching_equality_chain': {'user_candidate_chain1', 'user_candidate_chain2'}}.get(case['id'])
            if wanted and (evidence['status'] != 'parsed' or not wanted <= {m['qid'] for m in evidence['matches']}):
                output['semantic_control_errors'].append({'mode': record['mode'], 'rep': record['rep'],
                    'reason': 'Known control quantifiers were not recovered correctly'})
            if case['id'] == 'unsat_quantified' and evidence['matches']:
                match = evidence['matches'][0]
                if not match['bindings'] or match['bindings'][0]['bound_term']['term'] != '0' or not any(
                        t['term'] == '(f 0)' and t['resolved'] for t in match['top_level_matched_terms']):
                    output['semantic_control_errors'].append({'mode': record['mode'], 'rep': record['rep'],
                        'reason': 'Expected mathematical terms 0 and (f 0) were not recovered'})
        generic = sum(c['rule'] == 'smt' for c in clauses)
        specific = sum(c['rule'] in ('euf', 'farkas', 'bound', 'implied-eq') for c in clauses)
        output['runs'].append({'mode': record['mode'], 'rep': record['rep'],
            'trace_bytes': (path / 'trace.log').stat().st_size if (path / 'trace.log').exists() else 0,
            'trace_counts': evidence['counts'], 'parse_seconds': parsing_seconds,
            'trace_status': evidence['status'],
            'clause_serialization_seconds': record['report'].get('clause_serialization_seconds'),
            'packaging_seconds': packaging_seconds, 'callback_errors': record['report']['callback_errors'],
            'peak_rss_kib': record['report'].get('peak_rss_kib'),
            'non_inst_saved': len(clauses), 'generic_smt_saved': generic, 'specific_theory_hints_saved': specific,
            'clauses_with_dependencies': sum(bool(c['dependencies']) for c in clauses),
            'costs': {name: bulk_cost(value) for name, value in {
                'matching_available': evidence['matches'], 'chains_available': evidence['chains'],
                'non_inst_clauses_available': clauses}.items()} | {
                'combined_selected': block_cost(payload, encode),
                **{name + '_selected': block_cost((payload or {}).get(name, []), encode)
                   for name in ('matching', 'chains', 'non_inst_clauses')},
                'shared_formulas_selected': block_cost((payload or {}).get('formulas', {}), encode)},
            'bulk_token_measurement': measure_all_tokens, 'selection': selection,
            'inventory_incomplete': data['ast_node_limit_hit'] or bool(data['quantifiers_not_saved']),
            'matches_without_observed_instance': sum(not m['instance_count'] for m in evidence['matches'])})
    output['original_outcome_mismatches'] = [r['path'] for r in records if case['original_result'] and
        r['report'].get('status') == 'completed' and r['report']['result'] != case['original_result']]
    return output


def render_report(report):
    lines = ['# Advanced Z3 evidence pilot', '',
        'No LLM or Verus. Fresh diagnostic API replays; no claim of original search identity.',
        'Capture v3: isolated input inventory, no AST pretty-printing during search, native end marker.',
        'Planned context: 64k = base24k + previous-complement12k + new14k + output4k + other-input10k.',
        'This pilot measures the NEW blocks only; whole future chat fit and L40S GPU capacity are not tested.', '',
        '| Case | Mode | Matches | Qid unique / ambiguous / unmatched | Equality pairs / resolved | Binding paths resolved | Instance-term links | Chains | Non-inst clauses / specific hints | New tokens |',
        '|---|---|---|---|---|---|---|---|---|---|']
    for case in report['cases']:
        for run in case['runs']:
            if run['rep'] != 1:
                continue
            c = run['trace_counts']
            lines.append(f"| {case['id']} | {run['mode']} | {c.get('matches_saved', 0)} | {c.get('matched_input_qid', 0)} / {c.get('ambiguous_input_qid', 0)} / {c.get('unmatched_input_qid', 0)} | {c.get('equality_pairs', 0)} / {c.get('equality_pairs_resolved', 0)} | {c.get('binding_root_paths_resolved', 0)} | {c.get('dependency_edges', 0)} | {c.get('chains_saved', 0)} | {run['non_inst_saved']} / {run['specific_theory_hints_saved']} | {run['selection'].get('actual_tokens')} |")
    lines += ['', '## Available blocks and selected 14k package (first repetition)', '',
        '| Case | Mode | Matching available / sent | Chains available / sent | Clauses available / sent | Tokens available: matching / chains / clauses | Selected tokens |',
        '|---|---|---|---|---|---|---|']
    for case in report['cases']:
        for run in case['runs']:
            if run['rep'] != 1 or run['mode'] not in ('combined', 'combined_proof'):
                continue
            s = run['selection']
            selected, available = s.get('selected', {}), s.get('available', {})
            counts = [f"{available.get(k)} / {selected.get(k)}" for k in ('matching', 'chains', 'non_inst_clauses')]
            tokens = ' / '.join(str(run['costs'][k]['tokens']) for k in ('matching_available', 'chains_available', 'non_inst_clauses_available'))
            lines.append(f"| {case['id']} | {run['mode']} | {' | '.join(counts)} | {tokens} | {s.get('actual_tokens')} |")
    lines += ['', '## Paired instrumentation measurements', '',
        '| Case | Mode | Results | Median check s | Median process s | Check ratio | Changed outcomes | Changed reasons |',
        '|---|---|---|---|---|---|---|---|']
    for case in report['cases']:
        for mode, t in case['timings'].items():
            lines.append(f"| {case['id']} | {mode} | {t['results']} | {t['median_check_seconds']} | {t['median_process_seconds']} | {t['time_ratio_to_baseline']} | {t['outcome_mismatches']} | {t['reason_mismatches']} |")
    lines += ['', '## Interpretation', '',
        '- combined_proof is opt-in and explicitly enables proof mode; its previous real-query failures are not silently retried by default.',
        '- Raw-block token counts are disabled by default; selected blocks and the final 14k package are measured exactly.',
        '- Contaminated legacy traces and missing native boundaries are rejected, not reinterpreted as valid mathematical terms.',
        '- Unique qid association does not prove equality between an input formula and its transformed search version.',
        '- Missing equality roots, ambiguous qids, unmatched IDs, truncation and callback errors remain explicit.',
        '- Chains use earlier instance-associated enodes later named in a match. They do not prove first creation, necessity, or complete causality.',
        '- Clause dependencies are raw callback values, not resolved to trace event IDs; branch validity is not reconstructed.',
        '- Raw trace terms may be partial renderings; retain IDs and raw records. Do not feed unresolved explanations as complete proofs.',
        '- Per-block tokens and capped package costs are in report.json; no approximate word-to-token conversion.',
        '- Timing ratios for tiny checks or timeouts are unstable. Same result does not imply same search.',
        f"- Missing real categories: {report['skipped_categories']}",
        f"- Tokenizer: {report['tokenizer']}", f"- Complete processes: {report['complete']}"]
    lines += ['', '## Processing cost (medians over completed repetitions)', '',
        '| Case | Mode | Parse s | Package s | AST serialization s | Max encoder calls | Max exact full-package checks |',
        '|---|---|---|---|---|---|---|']
    for case in report['cases']:
        for mode in report['modes']:
            rows = [r for r in case['runs'] if r['mode'] == mode]
            if not rows:
                continue
            median = lambda key: statistics.median(r.get(key) or 0 for r in rows)
            lines.append(f"| {case['id']} | {mode} | {median('parse_seconds'):.4f} | {median('packaging_seconds'):.4f} | {median('clause_serialization_seconds'):.4f} | {max(r['selection'].get('encoder_calls', 0) for r in rows)} | {max(r['selection'].get('exact_package_checks', 0) for r in rows)} |")
    lines += ['', '## Failed processes and semantic control checks', '']
    for case in report['cases']:
        for error in case.get('failure_details', []):
            lines.append(f"- {case['id']}: {json.dumps(error, ensure_ascii=False)}")
        for error in case.get('semantic_control_errors', []):
            lines.append(f"- CONTROL {case['id']}: {json.dumps(error, ensure_ascii=False)}")
    return '\n'.join(lines) + '\n'


def run(args):
    study, output = args.study.resolve(), args.output.resolve()
    if output == study or output.is_relative_to(study) or study.is_relative_to(output):
        raise ValueError('Output must be outside the saved study and must not contain it')
    cases, skipped = select_cases(study, args.per_category, args.controls_only,
        None if args.full_sample else args.problem_ids, args.include_controls)
    print(f"Selected {sum(c['kind'] == 'verus_saved_query' for c in cases)} real problems and "
          f"{sum(c['kind'] == 'control' for c in cases)} synthetic controls", flush=True)
    encode, tokenizer_info = offline_tokenizer(args.tokenizer)
    modes = ALL_MODES if args.include_proof_mode else MODES
    plan = {'cases': [{k: v for k, v in c.items() if k != 'query_text'} |
        {'query_sha256': digest(c['query_text'].encode())} for c in cases],
        'repetitions': args.repetitions, 'timeout_ms': args.timeout_ms, 'max_trace_mb': args.max_trace_mb,
        'z3': api_identity(), 'planned_budgets': BUDGETS, 'tokenizer': tokenizer_info,
        'modes': modes, 'measure_all_tokens': args.measure_all_tokens,
        'tokenizer_sha256': digest(Path(tokenizer_info).read_bytes()) if encode else None,
        'implementation': {name: digest((ROOT / name).read_bytes()) for name in (
            'diagnostics/z3_advanced_pilot.py', 'diagnostics/z3_trace_evidence.py', 'diagnostics/z3_clause_capture.py',
            'diagnostics/z3_feedback_pilot.py', 'diagnostics/z3_probe.py', 'diagnostics/z3_internals.py',
            'repair_study/relevance.py', 'baseline/verifier.py', 'baseline/storage.py')}}
    if (output / 'plan.json').exists() and read_json(output / 'plan.json') != plan:
        raise ValueError('Pilot configuration/code changed; use a different output directory')
    write_json(output / 'plan.json', plan)
    results = []
    for case in cases:
        folder = output / case['id']
        if (folder / 'query.smt2').exists() and digest((folder / 'query.smt2').read_bytes()) != digest(case['query_text'].encode()):
            raise ValueError('Saved pilot query changed: ' + str(folder / 'query.smt2'))
        write_text(folder / 'query.smt2', case['query_text'])
        write_json(folder / 'context.json', case['context'])
        inventory_path = folder / 'inventory'
        if not (inventory_path / 'process.json').exists():
            call = execute([sys.executable, '-m', 'diagnostics.z3_advanced_pilot', 'inventory',
                '--query', str(folder / 'query.smt2'), '--output', str(inventory_path)], 60, env=api_env())
            write_json(inventory_path / 'process.json', call)
        inventory_call = read_json(inventory_path / 'process.json')
        if inventory_call['returncode'] != 0 or inventory_call['timed_out']:
            raise ValueError('Isolated input inventory failed; inspect ' + str(inventory_path / 'process.json'))
        records = []
        for rep in range(args.repetitions):
            order = modes[rep % len(modes):] + modes[:rep % len(modes)]
            for mode in order:
                path = folder / f'rep-{rep+1:02}' / mode
                if not (path / 'process.json').exists():
                    call = execute([sys.executable, '-m', 'diagnostics.z3_advanced_pilot', 'worker',
                        '--query', str(folder / 'query.smt2'), '--context', str(folder / 'context.json'),
                        '--inventory-file', str(inventory_path / 'input-quantifiers.json'),
                        '--output', str(path), '--mode', mode, '--timeout-ms', str(args.timeout_ms),
                        '--max-trace-mb', str(args.max_trace_mb)], args.timeout_ms / 1000 + 45, env=api_env())
                    write_json(path / 'process.json', call)
                    write_text(path / 'stderr.txt', call['stderr'])
                call = read_json(path / 'process.json')
                r = read_json(path / 'report.json') if (path / 'report.json').exists() else {'status': 'unavailable'}
                if call['timed_out'] or call['returncode'] != 0:
                    r = {**r, 'status': 'unavailable', 'process_failure': True}
                records.append({'mode': mode, 'rep': rep+1, 'path': str(path), 'process': call, 'report': r})
        result = analyze_case(case, folder, records, encode, args.measure_all_tokens)
        result['inventory_process_seconds'] = inventory_call['seconds']
        write_json(folder / 'summary.json', result)
        results.append(result)
        print('Probed', case['id'], flush=True)
    failures = [c['id'] for c in results if c['expected_result'] and any(
        result != c['expected_result'] for t in c['timings'].values() for result in t['results'])]
    report = {'cases': results, 'skipped_categories': skipped, 'tokenizer': tokenizer_info,
        'planned_budgets': BUDGETS, 'modes': modes, 'repetitions': args.repetitions,
        'bulk_token_measurement': args.measure_all_tokens,
        'control_expectation_failures': failures,
        'complete': not skipped and not failures and all(not c['failures'] and not c['semantic_control_errors'] for c in results)}
    write_json(output / 'report.json', report)
    write_text(output / 'report.md', render_report(report))
    print(output / 'report.md', flush=True)
    return 0 if report['complete'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'worker', 'inventory'))
    parser.add_argument('--study', type=Path, default=ROOT / 'results/solver-needs-qwen14b-100-internals24k/seed-20261018')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--query', type=Path)
    parser.add_argument('--context', type=Path)
    parser.add_argument('--mode', choices=ALL_MODES, default='combined')
    parser.add_argument('--inventory-file', type=Path)
    parser.add_argument('--include-proof-mode', action='store_true', help='Opt-in diagnostic mode; failed on previous real queries')
    parser.add_argument('--measure-all-tokens', action='store_true', help='Expensive raw-block token audit; selected blocks always measured')
    parser.add_argument('--per-category', type=int, default=3)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--timeout-ms', type=int, default=5000)
    parser.add_argument('--max-trace-mb', type=int, default=64)
    parser.add_argument('--tokenizer', type=Path)
    parser.add_argument('--controls-only', action='store_true')
    parser.add_argument('--include-controls', action='store_true', help='Add synthetic controls (off by default)')
    sample = parser.add_mutually_exclusive_group()
    sample.add_argument('--problem-ids', nargs='+', default=FIVE_PROBLEMS,
        help='Fixed diagnostic IDs; defaults to five real problems')
    sample.add_argument('--full-sample', action='store_true', help='Opt in to the original per-category real sample')
    args = parser.parse_args()
    if min(args.per_category, args.repetitions, args.timeout_ms, args.max_trace_mb) < 1:
        parser.error('Counts and limits must be positive')
    if args.command == 'worker' and (args.query is None or args.context is None):
        parser.error('worker requires --query and --context')
    if args.command == 'inventory' and args.query is None:
        parser.error('inventory requires --query')
    return worker(args) if args.command == 'worker' else collect_inventory(args) if args.command == 'inventory' else run(args)


if __name__ == '__main__':
    raise SystemExit(main())
