import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baseline.storage import write_json
from solver_needs_study import complement, feedback
from solver_needs_study.__main__ import configuration, ROOT


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(text)

    def apply_chat_template(self, messages, **kwargs):
        return list(json.dumps(messages))


class ComplementTests(unittest.TestCase):
    def test_no_replay_evidence_does_not_expose_empty_complement(self):
        self.assertIsNone(complement.build(Path('.'), {}, None, None, {}, lambda p: True))

    def test_configuration_and_separate_budgets(self):
        c = configuration(ROOT / 'configs/solver-needs-qwen14b-complement16k.json')
        self.assertEqual((c['max_model_len'], c['internals_token_budget'], c['complement_token_budget']),
                         (61440, 24576, 16384))
        self.assertEqual((c['max_attempts'], c['max_quantifiers'], c['max_instances_each'],
                          c['max_unobserved_quantifiers']), (3, 50, 3, 20))
        with patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            args = ('', {'stdout': '', 'stderr': ''}, {}, {}, {'queries': []}, [], Tokenizer(), c)
            self.assertFalse(feedback.fits(*args, complement={'x': 'a' * 16384}))
            self.assertFalse(feedback.fits('x' * 58000, *args[1:]))
            base = feedback.messages(*args[:6], config=c)
            extra = feedback.messages(*args[:6], config=c, complement={'queries': []})
            self.assertEqual(base[0], extra[0])
            self.assertNotIn('<complementary_internals>', base[1]['content'])
            self.assertIn('<complementary_internals>', extra[1]['content'])

    def test_zero_events_cap_ambiguity_and_input_examples(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            formulas = [{'qid': f'user_candidate_{i}', 'formula_sha256': str(i),
                         'quantifier_smt': f'(forall ((x Int)) (! (= x x) :qid user_candidate_{i}))'}
                        for i in range(25)]
            formulas += [{**formulas[0], 'formula_sha256': 'duplicate'}]
            matching = [{'formula_sha256': q['formula_sha256'],
                         'terms_by_same_root_symbol': [{'examples_smt': ['a', 'b', 'c']}]}
                        for q in formulas]
            write_json(folder / 'internals/q/input-quantifiers.json', {'quantifiers': formulas,
                'matching': matching, 'quantifiers_found': 26, 'ast_node_limit_hit': False,
                'quantifiers_not_saved': 0})
            report = {'instantiations_by_exact_formula': {'1': 10},
                      'instantiations_by_outer_qid': {'user_candidate_2': 3}, 'callback_errors': 0}
            write_json(folder / 'internals/q/report.json', report)
            result = complement.build(folder, {}, {'queries': [{'id': 'q'}]}, None,
                                      {'max_unobserved_quantifiers': 20}, lambda p: True)
            selected = result['quantifiers_without_observed_events']
            self.assertEqual(len(selected), 20)
            self.assertFalse({'user_candidate_0', 'user_candidate_1', 'user_candidate_2'} & {q['qid'] for q in selected})
            self.assertTrue(all(len(q['input_term_examples'][0]['examples_smt']) == 2 for q in selected))
            self.assertEqual(result['selection']['ambiguous_or_missing_qid'], 2)
            report['callback_errors'] = 1
            write_json(folder / 'internals/q/report.json', report)
            result = complement.build(folder, {}, {'queries': [{'id': 'q'}]}, None,
                                      {'max_unobserved_quantifiers': 20}, lambda p: True)
            self.assertEqual(result['selection']['selected'], 0)


if __name__ == '__main__':
    unittest.main()
