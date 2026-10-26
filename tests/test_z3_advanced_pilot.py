from pathlib import Path
import copy
import json
import tempfile
import unittest

from diagnostics.z3_advanced_pilot import BUDGETS, FIVE_PROBLEMS, package, select_cases
from diagnostics.z3_trace_evidence import parse_trace
from diagnostics.z3_clause_capture import ClauseCapture


class AdvancedPilotTests(unittest.TestCase):
    def test_default_sample_is_exactly_five_real_problems_without_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cases = [{'id': key, 'paper_label': label} for key, label in zip(
                [*FIVE_PROBLEMS, 'V-56'], ['AX', 'INST-forall', 'INST-witness', 'NLA', 'Other', 'FUEL'])]
            (root / 'manifest.json').write_text(json.dumps({'cases': cases}))
            for case in cases:
                path = root / 'inputs' / case['id']
                (path / 'solver').mkdir(parents=True)
                (path / 'solver/report.json').write_text(json.dumps({'queries': [
                    {'id': 'q1', 'file': 'q.smt2', 'result': 'unknown'}]}))
                (path / 'solver/q.smt2').write_text('(assert true)\n(check-sat)')
                (path / 'candidate.rs').write_text('proof fn example() {}')
                (path / 'verification.json').write_text(json.dumps({'stdout': '', 'stderr': ''}))
            selected, skipped = select_cases(root)
            self.assertEqual({c['problem_id'] for c in selected}, set(FIVE_PROBLEMS))
            self.assertEqual(len(selected), 5)
            self.assertTrue(all(c['kind'] == 'verus_saved_query' for c in selected))
            self.assertEqual(skipped, [])
            controls, skipped = select_cases(root, controls_only=True)
            self.assertEqual(len(controls), 5)
            self.assertTrue(all(c['kind'] == 'control' for c in controls))

    def test_actual_old_controls_are_rejected_instead_of_rendering_formatter_terms(self):
        root = Path(__file__).parent / 'fixtures/z3-trace-v1'
        for name in ('unsat_quantified', 'matching_equality_chain'):
            result = parse_trace(root / (name + '.log'), json.loads((root / (name + '.json')).read_text()))
            self.assertEqual(result['status'], 'contaminated_ast_namespace')
            self.assertEqual(result['matches'], [])
            payload, selection = package(result, [], {}, len)
            self.assertIsNone(payload)
            self.assertIn('invalid_trace', selection['status'])

    def parse(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace.log'
            path.write_text(text, encoding='utf-8')
            return parse_trace(path, {'quantifiers': [{'qid': 'user_candidate_q',
                'quantifier_smt': '(forall ((x Int)) true)', 'formula_sha256': 'hash'}]})

    def test_explicit_pair_paths_and_instance_association(self):
        result = self.parse('''[mk-app] #1 a
[mk-app] #2 b
[mk-app] #3 = #1 #2
[mk-app] #4 pattern #1
[mk-quant] #5 user_candidate_q 1 #4 #3
[eq-expl] #1 lit #3 ; #2
[eq-expl] #2 root
[new-match] F1 #5 #4 #1 ; #1 (#1 #2)
[instance] F1 ; 1
[attach-enode] #2 1
[end-of-instance]
[new-match] F2 #5 #4 #2 ; #2
[instance] F2 ; 2
[end-of-instance]
''')
        self.assertEqual(result['counts']['matches_saved'], 2)
        self.assertEqual(result['counts']['equality_pairs_resolved'], 1)
        self.assertEqual(result['matches'][0]['inventory_match'], 'unique_qid')
        self.assertEqual(len(result['dependencies']), 1)
        self.assertFalse(result['dependencies'][0]['causal_creation_proven'])
        self.assertEqual(result['chains'][0]['events'], ['m1', 'm2'])

    def test_no_dependencies_from_order_or_symbol_similarity(self):
        result = self.parse('''[mk-app] #1 a
[mk-app] #2 a
[mk-app] #4 pattern #1
[mk-quant] #5 user_candidate_q 1 #4 #1
[new-match] F1 #5 #4 #1 ; #1
[instance] F1 ; 1
[attach-enode] #1 1
[end-of-instance]
[new-match] F2 #5 #4 #2 ; #2
[instance] F2 ; 1
[end-of-instance]
''')
        self.assertEqual(result['dependencies'], [])
        self.assertFalse(result['matches'][0]['bindings'][0]['path_to_root']['complete'])

    def test_reused_ids_are_not_used_as_producers(self):
        result = self.parse('''[mk-app] #1 a
[mk-app] #4 pattern #1
[mk-quant] #5 user_candidate_q 1 #4 #1
[new-match] F1 #5 #4 #1 ; #1
[instance] F1 ; 1
[attach-enode] #1 1
[end-of-instance]
[mk-app] #1 b
[new-match] F2 #5 #4 #1 ; #1
[instance] F2 ; 1
[end-of-instance]
''')
        self.assertEqual(result['dependencies'], [])
        self.assertEqual(result['counts']['redefined_ids'], 1)

    def test_package_budget_and_missing_tokenizer(self):
        self.assertEqual(BUDGETS['context'], sum(v for k, v in BUDGETS.items() if k != 'context'))
        evidence = {'matches': [], 'chains': []}
        payload, selection = package(evidence, [{'rule': 'smt', 'clause_literals_smt': ['x' * 30000]}], {}, len)
        self.assertLessEqual(selection['actual_tokens'], 14336)
        self.assertEqual(payload['non_inst_clauses'], [])
        payload, selection = package(evidence, [], {}, None)
        self.assertIsNone(payload)
        self.assertIn('tokenizer_unavailable', selection['status'])

    def test_search_boundary_excludes_later_formatter_records(self):
        prefix = '[mk-var] #1 0\n[mk-app] #2 f #1\n[mk-app] #3 pattern #2\n[mk-quant] #4 user_candidate_q 1 #3 #2\n[new-match] F #4 #3 #1 ; #2\n'
        suffix = '[mk-app] #4 string\n[mk-app] #3 indent #4\n[mk-app] #5 compose #4\n'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace.log'
            path.write_text(prefix + suffix, encoding='utf-8', newline='')
            data = {'quantifiers': [{'qid': 'user_candidate_q', 'quantifier_smt': 'Q', 'formula_sha256': 'H'}]}
            result = parse_trace(path, data, end_bytes=len(prefix.encode()))
        self.assertEqual(result['status'], 'parsed')
        self.assertEqual(result['matches'][0]['qid'], 'user_candidate_q')
        self.assertEqual(result['matches'][0]['trigger']['term'], '(pattern (f (:var 0)))')
        self.assertTrue(result['matches'][0]['trigger']['resolved'])

    def test_native_marker_handles_buffered_trace_and_requires_marker(self):
        text = '[mk-app] #1 a\n[mk-app] #4 pattern #1\n[mk-quant] #5 user_candidate_q 1 #4 #1\n[new-match] F #5 #4 #1 ; #1\n'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace.log'
            data = {'quantifiers': [{'qid': 'user_candidate_q', 'quantifier_smt': 'Q', 'formula_sha256': 'H'}]}
            path.write_text(text + '[mk-app] #99 capture_end\n[mk-app] #5 string\n[mk-app] #4 indent #5\n[mk-app] #6 compose #5\n')
            result = parse_trace(path, data, end_marker='capture_end')
            self.assertEqual(result['status'], 'parsed')
            self.assertEqual(result['matches'][0]['qid'], 'user_candidate_q')
            path.write_text(text)
            result = parse_trace(path, data, end_marker='missing_marker')
            self.assertEqual(result['status'], 'missing_search_boundary')
            self.assertEqual(result['matches'], [])

    def test_resolved_false_for_missing_descendants(self):
        result = self.parse('[mk-app] #4 pattern #999\n[mk-quant] #5 user_candidate_q 1 #4 #999\n[new-match] F #5 #4 ; #999\n')
        self.assertFalse(result['matches'][0]['trigger']['resolved'])

    def test_large_candidate_pool_has_bounded_tokenization_work(self):
        seed = self.parse('[mk-app] #1 a\n[mk-app] #4 pattern #1\n[mk-quant] #5 user_candidate_q 1 #4 #1\n[new-match] F #5 #4 #1 ; #1\n')['matches'][0]
        matches = [{**copy.deepcopy(seed), 'id': 'm' + str(i), 'line': i} for i in range(1000)]
        payload, selection = package({'matches': matches, 'chains': []}, [], {}, len)
        self.assertEqual(selection['available']['matching'], 1000)
        self.assertEqual(selection['considered']['matching'], 64)
        self.assertLess(selection['encoder_calls'], 100)
        self.assertLessEqual(selection['actual_tokens'], 14336)
        self.assertTrue(payload['matching'])

    def test_estimation_cannot_bypass_exact_final_budget(self):
        def encode(text):
            return len(text) + (15000 if '"non_inst_clauses": [\n    {' in text else 0)
        payload, selection = package({'matches': [], 'chains': []},
            [{'rule': 'smt', 'clause_literals_smt': ['P']}], {}, encode)
        self.assertEqual(payload['non_inst_clauses'], [])
        self.assertGreater(selection['exact_package_checks'], 1)
        self.assertLessEqual(selection['actual_tokens'], 14336)

    def test_callback_never_serializes_asts(self):
        class Node:
            def __init__(self, key, name):
                self.key, self.symbol, self.calls = key, name, 0
            def get_id(self): return self.key
            def decl(self): return self
            def name(self): return self.symbol
            def children(self): return []
            def sexpr(self):
                self.calls += 1
                return self.symbol
        class API:
            @staticmethod
            def is_app(node): return True
        hint, a, b = Node(1, 'smt'), Node(2, 'P'), Node(3, 'Q')
        report = {}
        collector = ClauseCapture(API, {}, report)
        collector(hint, [], [a, b])
        collector(hint, [], [b, a])
        self.assertEqual(hint.calls + a.calls + b.calls, 0)
        self.assertEqual(len(collector.serialize()), 1)
        self.assertEqual(hint.calls + a.calls + b.calls, 3)
        self.assertEqual(report['clause_duplicates'], 1)


if __name__ == '__main__':
    unittest.main()
