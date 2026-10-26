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

from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json, write_text
from baseline.verifier import execute
from diagnostics.z3_feedback_pilot import CONTROLS, inventory, offline_tokenizer, block_cost
from diagnostics.z3_internals import api_env, api_identity, identity
from diagnostics.z3_probe import head, snapshots
from diagnostics.z3_trace_evidence import parse_trace
from repair_study.relevance import rank, source_context

MODES = ('baseline', 'callback', 'trace', 'combined', 'combined_proof')
BUDGETS = {'context': 65536, 'base': 24576, 'previous_complement': 12288,
           'new_blocks': 14336, 'output': 4096, 'program_and_other_input': 10240}
CONTROL_CHAIN = '''(declare-fun f (Int) Int) (declare-fun g (Int) Int)
(declare-const a Int) (declare-const b Int) (assert (= a b))
(assert (forall ((x Int)) (! (= (g (f x)) x) :pattern ((f x)) :qid user_candidate_chain1)))
(assert (forall ((x Int)) (! (> (g x) 0) :pattern ((g x)) :qid user_candidate_chain2)))
(assert (= (f a) b)) (assert (< b 0)) (check-sat)'''


def worker(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    callbacks = args.mode in ('callback', 'combined', 'combined_proof')
    trace = args.mode in ('trace', 'combined', 'combined_proof')
    proof = args.mode == 'combined_proof'
    report = {'status': 'unavailable', 'mode': args.mode, 'timeout_ms': args.timeout_ms,
        'overrides': {'timeout_ms': args.timeout_ms, 'trace': trace, 'proof': proof},
        'callback_errors': 0, 'rules_observed': {}, 'non_inst_clauses_observed': 0,
        'oversized_clauses_omitted': 0, 'clause_sample_omissions': 0, 'trace_limit_interrupted': False}
    clauses, stop = [], threading.Event()
    try:
        report['z3'] = identity()
        import z3
        z3.set_param('trace', trace)
        z3.set_param('proof', proof)
        if trace:
            z3.set_param('trace_file_name', str(output / 'trace.log'))
        query_text = args.query.read_text(encoding='utf-8')
        if re.search(r'\(set-option\s+:(?:trace(?:_file_name)?|proof|solver\.proof\.log)\b', query_text):
            raise ValueError('Input controls trace/proof settings; no silent override permitted')
        checks = list(snapshots(query_text))
        if len(checks) != 1 or head(checks[0][1]) != 'check-sat':
            raise ValueError('Requires one plain check-sat, without approximating assumptions/tactics')
        solver = z3.Solver()
        solver.from_string(checks[0][0])
        solver.set(timeout=args.timeout_ms)
        started = time.perf_counter()
        data = inventory(solver.assertions(), z3)
        write_json(output / 'input-quantifiers.json', data)
        report['inventory_seconds'] = time.perf_counter() - started
        context = read_json(args.context)

        def on_clause(hint, dependencies, clause):
            try:
                rule = str(hint.decl().name()) if z3.is_app(hint) else 'unknown'
                report['rules_observed'][rule] = report['rules_observed'].get(rule, 0) + 1
                if rule in ('inst', 'assumption', 'del', 'deleted', 'tseitin'):
                    return
                report['non_inst_clauses_observed'] += 1
                event = {'rule': rule, 'hint_smt': hint.sexpr(), 'dependencies': list(dependencies),
                         'clause_literals_smt': [c.sexpr() for c in clause],
                         'scope': 'replay clause; dependencies/branch validity not reconstructed'}
                text = json.dumps(event)
                if len(text) > 32000:
                    report['oversized_clauses_omitted'] += 1
                    return
                score = rank(text, context)[0]
                if any(e['event'] == event for e in clauses):
                    return
                if len(clauses) >= 256:
                    worst = max(range(len(clauses)), key=lambda i: clauses[i]['rank'])
                    report['clause_sample_omissions'] += 1
                    if score >= clauses[worst]['rank']:
                        return
                    clauses.pop(worst)
                clauses.append({'rank': score, 'event': event})
            except Exception:
                report['callback_errors'] += 1

        callback = z3.OnClause(solver, on_clause) if callbacks else None

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
        report.update(status='completed', result=str(result), check_seconds=time.perf_counter() - started,
            reason_unknown=solver.reason_unknown() if result == z3.unknown else None,
            statistics={key: value for key, value in solver.statistics()})
        stop.set()
        guard.join(timeout=1)
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
    write_json(output / 'clauses.json', [e['event'] for e in sorted(clauses, key=lambda e: e['rank'])])
    write_json(output / 'report.json', report)
    return 0 if report['status'] == 'completed' else 1


def select_cases(study, per_category=3, controls_only=False):
    controls = {**CONTROLS, 'matching_equality_chain': ('unsat', CONTROL_CHAIN)}
    cases = [{'id': name, 'kind': 'control', 'original_result': None, 'expected_result': expected,
              'context': {}, 'query_text': text + '\n'} for name, (expected, text) in controls.items()]
    skipped = []
    if controls_only:
        return cases, skipped
    manifest = read_json(study / 'manifest.json')
    for label in ('AX', 'INST-forall', 'INST-witness', 'NLA', 'FUEL', 'Other'):
        count = 0
        for row in manifest['cases']:
            if row['paper_label'] != label:
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
            if count == per_category:
                break
        if count < per_category:
            skipped.append({'label': label, 'requested': per_category, 'found': count})
    return cases, skipped


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


def analyze_case(case, folder, records, encode):
    timings = {}
    for mode in MODES:
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
        base_time = timings['baseline']['median_check_seconds']
        timings[mode]['time_ratio_to_baseline'] = timings[mode]['median_check_seconds'] / base_time if base_time and rows else None
    output = {'id': case['id'], 'kind': case['kind'], 'timings': timings,
        'original_result': case['original_result'], 'expected_result': case['expected_result'],
        'runs': [], 'failures': [r['path'] for r in records if r['report'].get('status') != 'completed']}
    for record in records:
        path = Path(record['path'])
        if record['report'].get('status') != 'completed':
            continue
        started = time.perf_counter()
        data = read_json(path / 'input-quantifiers.json')
        evidence = parse_trace(path / 'trace.log', data)
        write_json(path / 'trace-evidence.json', evidence)
        parsing_seconds = time.perf_counter() - started
        clauses = read_json(path / 'clauses.json')
        started = time.perf_counter()
        payload, selection = package(evidence, clauses, case['context'], encode)
        packaging_seconds = time.perf_counter() - started
        write_json(path / 'new-feedback-14k.json', payload)
        generic = sum(c['rule'] == 'smt' for c in clauses)
        specific = sum(c['rule'] in ('euf', 'farkas', 'bound', 'implied-eq') for c in clauses)
        output['runs'].append({'mode': record['mode'], 'rep': record['rep'],
            'trace_bytes': (path / 'trace.log').stat().st_size if (path / 'trace.log').exists() else 0,
            'trace_counts': evidence['counts'], 'parse_seconds': parsing_seconds,
            'packaging_seconds': packaging_seconds, 'callback_errors': record['report']['callback_errors'],
            'peak_rss_kib': record['report'].get('peak_rss_kib'),
            'non_inst_saved': len(clauses), 'generic_smt_saved': generic, 'specific_theory_hints_saved': specific,
            'clauses_with_dependencies': sum(bool(c['dependencies']) for c in clauses),
            'costs': {name: block_cost(value, encode) for name, value in {
                'matching_available': evidence['matches'], 'chains_available': evidence['chains'],
                'non_inst_clauses_available': clauses, 'combined_selected': payload}.items()}, 'selection': selection,
            'inventory_incomplete': data['ast_node_limit_hit'] or bool(data['quantifiers_not_saved']),
            'matches_without_observed_instance': sum(not m['instance_count'] for m in evidence['matches'])})
    output['original_outcome_mismatches'] = [r['path'] for r in records if case['original_result'] and
        r['report'].get('status') == 'completed' and r['report']['result'] != case['original_result']]
    return output


def render_report(report):
    lines = ['# Advanced Z3 evidence pilot', '',
        'No LLM or Verus. Fresh diagnostic API replays; no claim of original search identity.',
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
        '- combined_proof explicitly enables proof mode: report its semantic/performance effect separately.',
        '- Unique qid association does not prove equality between an input formula and its transformed search version.',
        '- Missing equality roots, ambiguous qids, unmatched IDs, truncation and callback errors remain explicit.',
        '- Chains use earlier instance-associated enodes later named in a match. They do not prove first creation, necessity, or complete causality.',
        '- Clause dependencies are raw callback values, not resolved to trace event IDs; branch validity is not reconstructed.',
        '- Raw trace terms may be partial renderings; retain IDs and raw records. Do not feed unresolved explanations as complete proofs.',
        '- Per-block tokens and capped package costs are in report.json; no approximate word-to-token conversion.',
        '- Timing ratios for tiny checks or timeouts are unstable. Same result does not imply same search.',
        f"- Missing real categories: {report['skipped_categories']}",
        f"- Tokenizer: {report['tokenizer']}", f"- Complete processes: {report['complete']}"]
    return '\n'.join(lines) + '\n'


def run(args):
    study, output = args.study.resolve(), args.output.resolve()
    if output == study or output.is_relative_to(study) or study.is_relative_to(output):
        raise ValueError('Output must be outside the saved study and must not contain it')
    cases, skipped = select_cases(study, args.per_category, args.controls_only)
    encode, tokenizer_info = offline_tokenizer(args.tokenizer)
    plan = {'cases': [{k: v for k, v in c.items() if k != 'query_text'} |
        {'query_sha256': digest(c['query_text'].encode())} for c in cases],
        'repetitions': args.repetitions, 'timeout_ms': args.timeout_ms, 'max_trace_mb': args.max_trace_mb,
        'z3': api_identity(), 'planned_budgets': BUDGETS, 'tokenizer': tokenizer_info,
        'tokenizer_sha256': digest(Path(tokenizer_info).read_bytes()) if encode else None,
        'implementation': {name: digest((ROOT / name).read_bytes()) for name in (
            'diagnostics/z3_advanced_pilot.py', 'diagnostics/z3_trace_evidence.py',
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
        records = []
        for rep in range(args.repetitions):
            order = MODES[rep % len(MODES):] + MODES[:rep % len(MODES)]
            for mode in order:
                path = folder / f'rep-{rep+1:02}' / mode
                if not (path / 'process.json').exists():
                    call = execute([sys.executable, '-m', 'diagnostics.z3_advanced_pilot', 'worker',
                        '--query', str(folder / 'query.smt2'), '--context', str(folder / 'context.json'),
                        '--output', str(path), '--mode', mode, '--timeout-ms', str(args.timeout_ms),
                        '--max-trace-mb', str(args.max_trace_mb)], args.timeout_ms / 1000 + 45, env=api_env())
                    write_json(path / 'process.json', call)
                    write_text(path / 'stderr.txt', call['stderr'])
                call = read_json(path / 'process.json')
                r = read_json(path / 'report.json') if (path / 'report.json').exists() else {'status': 'unavailable'}
                if call['timed_out'] or call['returncode'] != 0:
                    r = {**r, 'status': 'unavailable', 'process_failure': True}
                records.append({'mode': mode, 'rep': rep+1, 'path': str(path), 'process': call, 'report': r})
        result = analyze_case(case, folder, records, encode)
        write_json(folder / 'summary.json', result)
        results.append(result)
        print('Probed', case['id'], flush=True)
    failures = [c['id'] for c in results if c['expected_result'] and any(
        result != c['expected_result'] for t in c['timings'].values() for result in t['results'])]
    report = {'cases': results, 'skipped_categories': skipped, 'tokenizer': tokenizer_info,
        'planned_budgets': BUDGETS, 'modes': MODES, 'repetitions': args.repetitions,
        'control_expectation_failures': failures,
        'complete': not skipped and not failures and all(not c['failures'] for c in results)}
    write_json(output / 'report.json', report)
    write_text(output / 'report.md', render_report(report))
    print(output / 'report.md', flush=True)
    return 0 if report['complete'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'worker'))
    parser.add_argument('--study', type=Path, default=ROOT / 'results/solver-needs-qwen14b-100-internals24k/seed-20261018')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--query', type=Path)
    parser.add_argument('--context', type=Path)
    parser.add_argument('--mode', choices=MODES, default='combined')
    parser.add_argument('--per-category', type=int, default=3)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--timeout-ms', type=int, default=5000)
    parser.add_argument('--max-trace-mb', type=int, default=64)
    parser.add_argument('--tokenizer', type=Path)
    parser.add_argument('--controls-only', action='store_true')
    args = parser.parse_args()
    if min(args.per_category, args.repetitions, args.timeout_ms, args.max_trace_mb) < 1:
        parser.error('Counts and limits must be positive')
    if args.command == 'worker' and (args.query is None or args.context is None):
        parser.error('worker requires --query and --context')
    return worker(args) if args.command == 'worker' else run(args)


if __name__ == '__main__':
    raise SystemExit(main())
