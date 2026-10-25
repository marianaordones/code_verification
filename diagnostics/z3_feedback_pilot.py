"""Capability pilot: saved SMT queries, isolated API replays, no LLM or Verus calls."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import statistics
import sys
import time

from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json, write_text
from baseline.verifier import execute
from diagnostics.z3_internals import api_env, api_identity, identity
from diagnostics.z3_probe import head, snapshots

MODES = ('baseline', 'callback', 'profile', 'combined')
THEORY_HINTS = {'euf', 'farkas', 'bound', 'implied-eq'}
CONTROLS = {
    'sat_ground': ('sat', '(declare-const x Int)\n(assert (>= x 0))\n(assert (<= x 0))\n(check-sat)'),
    'unsat_arithmetic': ('unsat', '(declare-const a Real)\n(declare-const b Real)\n(declare-const c Real)\n(assert (>= a b))\n(assert (>= b c))\n(assert (> c a))\n(check-sat)'),
    'unsat_quantified': ('unsat', '(declare-fun f (Int) Int)\n(assert (forall ((x Int)) (! (>= (f x) 0) :pattern ((f x)) :qid control_nonnegative)))\n(assert (< (f 0) 0))\n(check-sat)'),
    'quantifier_without_ground_trigger': (None, '(set-option :smt.mbqi false)\n(declare-fun f (Int) Int)\n(declare-const a Int)\n(assert (forall ((x Int)) (! (> (f x) x) :pattern ((f x)) :qid control_no_ground_term)))\n(assert (>= a 0))\n(check-sat)')}


def clean_qid(value):
    value = str(value)
    return None if value in ('', '<null>', 'null') else value


def formula_record(q, z3):
    text = q.sexpr()
    patterns = []
    heads = set()
    for index in range(q.num_patterns()):
        pattern = q.pattern(index)
        patterns.append(pattern.sexpr())
        for term in pattern.children():
            if z3.is_app(term):
                heads.add(str(term.decl().name()))
    return {'formula_sha256': digest(text.encode()), 'qid': clean_qid(q.qid()),
        'quantifier_smt': text if len(text) <= 64000 else None,
        'formula_omitted': len(text) > 64000,
        'kind': 'forall' if q.is_forall() else 'exists',
        'bound_variables': [{'name': q.var_name(i), 'sort': q.var_sort(i).sexpr()} for i in range(q.num_vars())],
        'explicit_patterns_smt': patterns, 'pattern_root_symbols': sorted(heads),
        'weight': q.weight()}


def inventory(assertions, z3):
    stack, nodes, seen = list(assertions), [], set()
    quantifiers = []
    while stack and len(seen) < 100000:
        expr = stack.pop()
        if expr.get_id() in seen:
            continue
        seen.add(expr.get_id())
        nodes.append(expr)
        if z3.is_quantifier(expr) and not expr.is_lambda():
            quantifiers.append(formula_record(expr, z3))
        stack.extend(expr.children())
    quantifiers.sort(key=lambda q: (0 if (q['qid'] or '').startswith('user_candidate') else
                                    1 if 'candidate' in (q['qid'] or '') else 2, q['qid'] or '', q['formula_sha256']))
    found = len(quantifiers)
    quantifiers = quantifiers[:512]
    symbols = {name for q in quantifiers for name in q['pattern_root_symbols']}
    terms, term_counts, ground_cache = defaultdict(list), Counter(), {}

    def is_ground(expr):
        key = expr.get_id()
        if key not in ground_cache:
            pending = [(expr, False)]
            while pending:
                item, done = pending.pop()
                item_id = item.get_id()
                if item_id in ground_cache:
                    continue
                if z3.is_var(item) or z3.is_quantifier(item):
                    ground_cache[item_id] = False
                elif done:
                    ground_cache[item_id] = all(ground_cache[c.get_id()] for c in item.children())
                else:
                    pending.append((item, True))
                    pending.extend((c, False) for c in item.children() if c.get_id() not in ground_cache)
        return ground_cache[key]

    oversized = 0
    for expr in nodes:
        if z3.is_app(expr) and str(expr.decl().name()) in symbols and is_ground(expr):
            name = str(expr.decl().name())
            term_counts[name] += 1
            if len(terms[name]) < 6:
                text = expr.sexpr()
                if len(text) <= 12000:
                    terms[name].append(text)
                else:
                    oversized += 1
    matching = [{'formula_sha256': q['formula_sha256'], 'qid': q['qid'],
        'explicit_patterns_smt': q['explicit_patterns_smt'], 'bound_variables': q['bound_variables'],
        'terms_by_same_root_symbol': [{'symbol': name, 'ground_terms_in_input_count': term_counts[name],
            'examples_smt': terms[name]} for name in q['pattern_root_symbols']],
        'origin': 'loaded input AST, not the active E-matching term database',
        'matching_diagnosis': 'not determined; symbol overlap is not a matching test'} for q in quantifiers]
    return {'quantifiers': quantifiers, 'matching': matching, 'ast_nodes_visited': len(seen),
        'ast_node_limit_hit': bool(stack), 'quantifiers_found': found,
        'quantifiers_not_saved': max(0, found - len(quantifiers)),
        'oversized_ground_terms_not_saved': oversized}


def worker(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'unavailable', 'mode': args.mode, 'callback_errors': 0,
              'rules_observed': {}, 'events_omitted_by_limits': 0,
              'scope': 'isolated diagnostic API replay, not original Verus search'}
    try:
        report['z3'] = identity()
        import z3
        checks = list(snapshots(args.query.read_text(encoding='utf-8')))
        if len(checks) != 1 or head(checks[0][1]) != 'check-sat':
            raise ValueError('Requires exactly one plain check-sat; no approximation of tactics/assumptions')
        solver = z3.Solver()
        solver.from_string(checks[0][0])
        profiling = args.mode in ('profile', 'combined')
        callbacks = args.mode in ('callback', 'combined')
        solver.set(timeout=args.timeout_ms)
        solver.set('qi.profile', profiling)
        report['overrides'] = {'timeout_ms': args.timeout_ms, 'qi.profile': profiling}
        data = inventory(solver.assertions(), z3)
        write_json(output / 'input-quantifiers.json', data)
        formulas, qids, events, saved_rules = Counter(), Counter(), [], Counter()
        sample_bindings = defaultdict(list)
        callback = None

        def on_clause(hint, dependencies, clause):
            try:
                rule = str(hint.decl().name()) if z3.is_app(hint) else 'unknown'
                report['rules_observed'][rule] = report['rules_observed'].get(rule, 0) + 1
                quantifier = None
                if rule == 'inst' and z3.is_app(hint) and hint.num_args() and z3.is_quantifier(hint.arg(0)):
                    quantifier = hint.arg(0)
                    fingerprint = digest(quantifier.sexpr().encode())
                    qid = clean_qid(quantifier.qid())
                    formulas[fingerprint] += 1
                    if qid is not None:
                        qids[qid] += 1
                    if len(sample_bindings[fingerprint]) < 3:
                        binding = [term.sexpr() for child in hint.children()
                                   if z3.is_app(child) and str(child.decl().name()) == 'bind' for term in child.children()]
                        if len(json.dumps(binding)) <= 64000:
                            sample_bindings[fingerprint].append(binding)
                if saved_rules[rule] >= 20 or len(events) >= 400:
                    report['events_omitted_by_limits'] += 1
                    return
                event = {'rule': rule, 'hint_smt': hint.sexpr(),
                         'dependencies': list(dependencies), 'clause_literals_smt': [c.sexpr() for c in clause]}
                if quantifier is not None:
                    event['quantifier_sha256'] = fingerprint
                    event['qid'] = qid
                if len(json.dumps(event)) > 64000:
                    report['events_omitted_by_limits'] += 1
                    return
                events.append(event)
                saved_rules[rule] += 1
            except Exception:
                report['callback_errors'] += 1

        if callbacks:
            callback = z3.OnClause(solver, on_clause)
        started = time.perf_counter()
        result = solver.check()
        report.update(status='completed', result=str(result), check_seconds=time.perf_counter() - started,
                      reason_unknown=solver.reason_unknown() if result == z3.unknown else None,
                      statistics={k: v for k, v in solver.statistics()})
        qid_frequency = Counter(q['qid'] for q in data['quantifiers'] if q['qid'] is not None)
        profiles = []
        for q in data['quantifiers']:
            exact = formulas[q['formula_sha256']] if callbacks else None
            by_qid = qids[q['qid']] if callbacks and q['qid'] is not None and qid_frequency[q['qid']] == 1 else None
            status = ('not_instrumented' if not callbacks else 'observed_exact_formula' if exact else
                      'observed_unique_qid' if by_qid else 'ambiguous_qid' if qid_frequency[q['qid']] > 1 else 'no_event_observed')
            profiles.append({**q, 'observed_exact_formula_events': exact,
                'observed_events_by_unique_qid': by_qid, 'observation_status': status,
                'native_profile_records': None,
                'binding_samples_callback_order': sample_bindings.get(q['formula_sha256'], [])})
        input_hashes = {q['formula_sha256'] for q in data['quantifiers']}
        input_qids = {q['qid'] for q in data['quantifiers'] if q['qid'] is not None}
        write_json(output / 'quantifier-profile.json', profiles)
        write_json(output / 'clauses.json', events)
        write_json(output / 'matching.json', data['matching'])
        report.update(saved_events=len(events), instantiations_by_exact_formula=dict(formulas),
                      instantiations_by_qid=dict(qids),
                      event_formulas_not_in_inventory=[h for h in formulas if h not in input_hashes],
                      event_qids_not_in_inventory=[q for q in qids if q not in input_qids],
                      input_quantifiers=data['quantifiers_found'],
                      inventory_quantifiers_saved=len(data['quantifiers']),
                      inventory_incomplete=data['ast_node_limit_hit'] or data['quantifiers_not_saved'] > 0,
                      dependency_nonempty_events=sum(bool(e['dependencies']) for e in events),
                      no_event_observed_quantifiers=sum(q['observation_status'] == 'no_event_observed' for q in profiles),
                      quantifiers_without_explicit_patterns=sum(not q['explicit_patterns_smt'] for q in profiles),
                      matching_rows_without_input_term_examples=sum(not any(t['examples_smt'] for t in m['terms_by_same_root_symbol']) for m in data['matching']),
                      detailed_theory_hints_observed={k: v for k, v in report['rules_observed'].items() if k in THEORY_HINTS})
        assert not callbacks or callback is not None
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    write_json(output / 'report.json', report)
    return 0 if report['status'] == 'completed' else 1


def parse_profile(stderr):
    records = []
    for line in stderr.splitlines():
        if '[quantifier_instances]' not in line:
            continue
        body = line.split('[quantifier_instances]', 1)[1].strip()
        fields = re.split(r'\s+:\s+', body)
        records.append({'qid_text': fields[0].strip(), 'fields_raw': fields[1:], 'raw': line,
                        'counter_semantics': 'raw version-specific fields, not interpreted as causes'})
    return records


def select_cases(study, controls_only=False):
    cases = [{'id': key, 'kind': 'control', 'expected_result': expected, 'original_result': None,
              'query_text': text + '\n'} for key, (expected, text) in CONTROLS.items()]
    skipped = []
    if controls_only:
        return cases, skipped
    manifest = read_json(study / 'manifest.json')
    for label in ('AX', 'INST-forall', 'INST-witness', 'NLA', 'FUEL', 'Other'):
        selected = None
        for row in manifest['cases']:
            if row['paper_label'] != label:
                continue
            folder = study / 'inputs' / row['id']
            path = folder / 'solver/report.json'
            if not path.exists():
                continue
            for query in read_json(path)['queries']:
                if query['result'] not in ('sat', 'unknown'):
                    continue
                source = (folder / 'solver' / query['file']).resolve()
                if not source.is_relative_to((folder / 'solver').resolve()):
                    raise ValueError('Query path escapes saved solver directory')
                text = source.read_text(encoding='utf-8')
                checks = list(snapshots(text))
                if len(checks) != 1 or head(checks[0][1]) != 'check-sat':
                    continue
                selected = {'id': label + '-' + row['id'], 'kind': 'verus_saved_query',
                    'paper_label': label, 'problem_id': row['id'], 'original_result': query['result'],
                    'expected_result': None, 'source': str(source), 'query_text': text}
                break
            if selected:
                break
        if selected:
            cases.append(selected)
        else:
            skipped.append({'label': label, 'reason': 'no saved SAT/UNKNOWN query with one plain check-sat'})
    return cases, skipped


def offline_tokenizer(explicit=None):
    revision = 'aedcc2d42b622764e023cf882b6652e646b95671'
    relative = 'models/Qwen2.5-Coder-14B-Instruct/' + revision + '/tokenizer.json'
    candidates = [explicit] if explicit else [ROOT / '.cluster' / relative, ROOT.parent / 'code_verification/.cluster' / relative]
    try:
        from tokenizers import Tokenizer
        path = next(p for p in candidates if p is not None and p.exists())
        tokenizer = Tokenizer.from_file(str(path))
        return lambda s: len(tokenizer.encode(s, add_special_tokens=False).ids), str(path)
    except Exception as error:
        return None, str(error)


def block_cost(value, encode):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    return {'bytes': len(text.encode()), 'characters': len(text),
            'tokens': encode(text) if encode else None,
            'tokenizer': 'pinned Qwen Coder tokenizer; standalone JSON, not whole chat' if encode else 'unavailable'}


def summarize_case(case, folder, records, encode):
    by_mode = {mode: [r for r in records if r['mode'] == mode and r['report'].get('status') == 'completed'] for mode in MODES}
    timings = {mode: {'completed': len(rows), 'results': dict(Counter(r['report']['result'] for r in rows)),
        'reasons_unknown': dict(Counter(r['report'].get('reason_unknown') or 'none' for r in rows)),
        'median_check_seconds': statistics.median([r['report']['check_seconds'] for r in rows]) if rows else None,
        'median_process_seconds': statistics.median([r['process']['seconds'] for r in rows]) if rows else None} for mode, rows in by_mode.items()}
    baseline_by_rep = {r['rep']: r for r in by_mode['baseline']}
    for mode in MODES:
        compared = [(r, baseline_by_rep[r['rep']]) for r in by_mode[mode] if r['rep'] in baseline_by_rep]
        timings[mode]['paired_outcome_mismatches'] = sum(a['report']['result'] != b['report']['result'] for a, b in compared)
        timings[mode]['paired_reason_mismatches'] = sum(a['report'].get('reason_unknown') != b['report'].get('reason_unknown') for a, b in compared)
        base = timings['baseline']['median_check_seconds']
        current = timings[mode]['median_check_seconds']
        timings[mode]['median_time_ratio_to_baseline'] = current / base if base and current is not None else None
    result = {'id': case['id'], 'kind': case['kind'], 'original_result': case['original_result'],
              'expected_result': case['expected_result'], 'timings': timings,
              'failed_processes': [r['path'] for r in records if r['report'].get('status') != 'completed']}
    representative = next(iter(by_mode['combined']), None)
    if representative is None:
        result['capabilities'] = {'status': 'unavailable', 'reason': 'no completed combined replay'}
        return result
    path = Path(representative['path'])
    report = representative['report']
    profile = read_json(path / 'quantifier-profile.json')
    native = representative['native_profile']
    native_by_qid = defaultdict(list)
    for item in native:
        native_by_qid[item['qid_text']].append(item)
    for q in profile:
        q['native_profile_records'] = native_by_qid.get(q['qid']) or None
    matching = read_json(path / 'matching.json')
    clauses = read_json(path / 'clauses.json')
    non_inst = [e for e in clauses if e['rule'] not in ('inst', 'assumption', 'del', 'deleted', 'tseitin')]
    theory = [e for e in non_inst if e['rule'] == 'smt' or e['rule'] in THEORY_HINTS]
    blocks = {'theory_inferences': theory, 'triggers_and_input_terms': matching,
              'quantifier_profile': profile, 'other_search_inferences': non_inst}
    for name, value in blocks.items():
        write_json(folder / 'payloads' / (name + '.json'), value)
    result['block_costs'] = {name: block_cost(value, encode) for name, value in blocks.items()}
    result['capabilities'] = {'status': 'measured', 'representative': str(path),
        'rules_observed': report['rules_observed'], 'saved_theory_events': len(theory),
        'detailed_theory_hints_observed': report['detailed_theory_hints_observed'],
        'dependency_nonempty_events': report['dependency_nonempty_events'],
        'callback_errors': report['callback_errors'], 'events_omitted_by_limits': report['events_omitted_by_limits'],
        'input_quantifiers_found': report['input_quantifiers'], 'inventory_incomplete': report['inventory_incomplete'],
        'no_event_observed_quantifiers': report['no_event_observed_quantifiers'],
        'ambiguous_qid_quantifiers': sum(q['observation_status'] == 'ambiguous_qid' for q in profile),
        'event_formulas_without_exact_inventory_match': len(report['event_formulas_not_in_inventory']),
        'event_qids_without_inventory_match': report['event_qids_not_in_inventory'],
        'native_profile_records': len(native),
        'native_profile_qids_without_inventory_match': sorted(set(native_by_qid) - {q['qid'] for q in profile}),
        'quantifiers_without_explicit_patterns': report['quantifiers_without_explicit_patterns'],
        'matching_rows_without_input_term_examples': report['matching_rows_without_input_term_examples'],
        'source_variable_to_binding_mapping': 'not established',
        'active_matching_term_database': 'not extracted',
        'solver_inferred_patterns': 'not extracted',
        'reason_a_quantifier_was_not_instantiated': 'not determined'}
    result['original_outcome_matches_combined'] = (report['result'] == case['original_result']) if case['original_result'] else None
    result['control_expected_outcome_matches'] = (report['result'] == case['expected_result']) if case['expected_result'] else None
    return result


def render_report(summary):
    lines = ['# Piloto de novos blocos de feedback Z3', '',
        'Sem inferência LLM ou chamadas ao Verus. Replays API isolados, não a busca original.',
        'Os termos listados são da AST de entrada; não afirmam disponibilidade no E-matching.', '',
        '| Caso | Fórmulas encontradas | Sem evento observado | Eventos de teoria salvos | Hints específicos observados | Perfil nativo |',
        '|---|---|---|---|---|---|']
    for case in summary['cases']:
        c = case['capabilities']
        if c['status'] != 'measured':
            lines.append(f"| {case['id']} | indisponível | — | — | — | — |")
            continue
        lines.append(f"| {case['id']} | {c['input_quantifiers_found']} | {c['no_event_observed_quantifiers']} | {c['saved_theory_events']} | {c['detailed_theory_hints_observed']} | {c['native_profile_records']} |")
    lines += ['', '## Custo dos blocos', '', '| Caso | Bloco | Bytes | Tokens Qwen |', '|---|---|---|---|']
    for case in summary['cases']:
        for block, cost in case.get('block_costs', {}).items():
            lines.append(f"| {case['id']} | {block} | {cost['bytes']} | {cost['tokens']} |")
    lines += ['', '## Campos vazios e correspondências ausentes', '',
        '| Caso | Sem padrões explícitos | Sem exemplos de termos da entrada | Qids de eventos fora do inventário | Qids ambíguos | Eventos com dependências não vazias | Erros callback |',
        '|---|---|---|---|---|---|---|']
    for case in summary['cases']:
        c = case['capabilities']
        if c['status'] == 'measured':
            lines.append(f"| {case['id']} | {c['quantifiers_without_explicit_patterns']} | {c['matching_rows_without_input_term_examples']} | {len(c['event_qids_without_inventory_match'])} | {c['ambiguous_qid_quantifiers']} | {c['dependency_nonempty_events']} | {c['callback_errors']} |")
    lines += ['', '## Efeito da instrumentação', '',
        '| Caso | Modo | Resultados | Mediana check (s) | Razão para baseline | Resultados diferentes | Motivos diferentes |',
        '|---|---|---|---|---|---|---|']
    for case in summary['cases']:
        for mode, t in case['timings'].items():
            lines.append(f"| {case['id']} | {mode} | {t['results']} | {t['median_check_seconds']} | {t['median_time_ratio_to_baseline']} | {t['paired_outcome_mismatches']} | {t['paired_reason_mismatches']} |")
    lines += ['', '## Limites de interpretação', '',
        '- Ausência de evento não prova descarte pelo solver nem trigger incorreto.',
        '- Hints smt genéricos não são justificativas detalhadas de aritmética/igualdade.',
        '- Perfil nativo preserva campos brutos: não inferimos a semântica de colunas não validada.',
        '- Fórmulas/termos/eventos grandes são omitidos inteiros, com limites registrados.',
        '- Igualmente SAT/UNKNOWN/UNSAT não significa sequência de busca idêntica.',
        '- Tempos muito curtos e execuções limitadas por timeout exigem cautela nas razões.',
        '- O custo medido é de JSON isolado; não inclui programa, prompt ou saída do modelo.',
        '- Dados ausentes e sem correspondência são detalhados no report.json.',
        f"Categorias reais sem consulta elegível: {summary['skipped_real_categories']}",
        f"Controles com resultado diferente do esperado: {summary.get('control_expectation_failures', [])}",
        f"Tokenizer: {summary['tokenizer']}"]
    return '\n'.join(lines) + '\n'


def run(args):
    selected, skipped = select_cases(args.study.resolve(), args.controls_only)
    if args.output.resolve() == args.study.resolve() or args.output.resolve().is_relative_to(args.study.resolve()):
        raise ValueError('Output must be outside the saved source study')
    plan = {'cases': [{k: v for k, v in c.items() if k != 'query_text'} | {'query_sha256': digest(c['query_text'].encode())} for c in selected],
            'repetitions': args.repetitions, 'timeout_ms': args.timeout_ms, 'z3': api_identity(),
            'implementation_sha256': digest(Path(__file__).read_bytes()),
            'dependencies_sha256': {name: digest((ROOT / name).read_bytes()) for name in (
                'diagnostics/z3_internals.py', 'diagnostics/z3_probe.py',
                'baseline/verifier.py', 'baseline/storage.py')}}
    if (args.output / 'plan.json').exists() and read_json(args.output / 'plan.json') != plan:
        raise ValueError('Pilot settings changed; use another output directory')
    write_json(args.output / 'plan.json', plan)
    encode, tokenizer_info = offline_tokenizer(args.tokenizer)
    results = []
    for case in selected:
        folder = args.output / case['id']
        query = folder / 'query.smt2'
        if query.exists() and digest(query.read_bytes()) != digest(case['query_text'].encode()):
            raise ValueError('Frozen pilot query changed: ' + str(query))
        write_text(query, case['query_text'])
        records = []
        for rep in range(args.repetitions):
            order = MODES[rep % len(MODES):] + MODES[:rep % len(MODES)]
            for mode in order:
                path = folder / f'rep-{rep + 1:02}' / mode
                if not (path / 'process.json').exists():
                    call = execute([sys.executable, '-m', 'diagnostics.z3_feedback_pilot', 'worker',
                        '--query', str(query.resolve()), '--output', str(path.resolve()), '--mode', mode,
                        '--timeout-ms', str(args.timeout_ms)], args.timeout_ms / 1000 + 45, env=api_env())
                    write_json(path / 'process.json', call)
                    write_text(path / 'stderr.txt', call['stderr'])
                call = read_json(path / 'process.json')
                report = read_json(path / 'report.json') if (path / 'report.json').exists() else {'status': 'unavailable', 'error': 'worker report missing'}
                if call['timed_out'] or call['returncode'] != 0:
                    report = {**report, 'status': 'unavailable', 'process_failure': True}
                records.append({'mode': mode, 'rep': rep + 1, 'path': str(path), 'report': report,
                                'process': call, 'native_profile': parse_profile(call['stderr'])})
        result = summarize_case(case, folder, records, encode)
        write_json(folder / 'summary.json', result)
        results.append(result)
        print('Probed', case['id'], flush=True)
    failed_controls = [c['id'] for c in results if c.get('control_expected_outcome_matches') is False]
    summary = {'cases': results, 'skipped_real_categories': skipped, 'tokenizer': tokenizer_info,
        'repetitions': args.repetitions, 'modes': MODES,
        'control_expectation_failures': failed_controls,
        'complete': not skipped and not failed_controls and all(not c['failed_processes'] for c in results),
        'instrumentation_scope': 'same API library/input/timeout, varying callback and qi.profile; no engine switch or proof-mode enablement'}
    write_json(args.output / 'report.json', summary)
    write_text(args.output / 'report.md', render_report(summary))
    print(args.output / 'report.md', flush=True)
    return 0 if summary['complete'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'worker'))
    parser.add_argument('--study', type=Path, default=ROOT / 'results/solver-needs-qwen14b-100-internals24k/seed-20261018')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--query', type=Path)
    parser.add_argument('--mode', choices=MODES, default='combined')
    parser.add_argument('--timeout-ms', type=int, default=5000)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--tokenizer', type=Path)
    parser.add_argument('--controls-only', action='store_true')
    args = parser.parse_args()
    if args.timeout_ms < 1 or args.repetitions < 1:
        parser.error('timeout and repetitions must be positive')
    if args.command == 'worker':
        if args.query is None:
            parser.error('worker requires --query')
        return worker(args)
    from baseline.__main__ import run_lock
    with run_lock(args.output.resolve()):
        return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
