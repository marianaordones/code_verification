from pathlib import Path
import tempfile
import unittest

from diagnostics.z3_advanced_pilot import BUDGETS, package
from diagnostics.z3_trace_evidence import parse_trace


class AdvancedPilotTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
