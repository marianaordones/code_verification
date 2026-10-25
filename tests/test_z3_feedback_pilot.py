import json
from pathlib import Path
import tempfile
import unittest

from baseline.storage import write_json, write_text
from diagnostics import z3_feedback_pilot as pilot


class FeedbackPilotTests(unittest.TestCase):
    def test_native_profile_preserves_uninterpreted_fields(self):
        lines = 'warning\n[quantifier_instances] Q1 : 10 : 0 : 0 : 2 : 3\n'
        values = pilot.parse_profile(lines)
        self.assertEqual(values[0]['qid_text'], 'Q1')
        self.assertEqual(values[0]['fields_raw'], ['10', '0', '0', '2', '3'])
        self.assertEqual(pilot.parse_profile('no profile'), [])

    def test_tokens_unavailable_are_null_not_zero(self):
        self.assertIsNone(pilot.block_cost([], None)['tokens'])
        self.assertEqual(pilot.block_cost([], len)['tokens'], 2)

    def test_selects_only_saved_failed_plain_checks_one_per_category(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            write_json(root / 'manifest.json', {'cases': [{'id': 'example', 'paper_label': 'AX'}]})
            solver = root / 'inputs/example/solver'
            write_json(solver / 'report.json', {'queries': [
                {'id': 'q0', 'file': 'q0.smt2', 'result': 'unsat'},
                {'id': 'q1', 'file': 'q1.smt2', 'result': 'unknown'}]})
            write_text(solver / 'q1.smt2', '(assert true)\n(check-sat)')
            cases, skipped = pilot.select_cases(root)
            self.assertEqual(len(cases), 5)
            self.assertEqual(cases[-1]['id'], 'AX-example')
            self.assertEqual(cases[-1]['original_result'], 'unknown')
            self.assertEqual(len(skipped), 5)

    def test_mode_comparison_keeps_mismatches_and_ratios(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            base = {'status': 'completed', 'result': 'unknown', 'check_seconds': 1}
            combined = {**base, 'result': 'sat', 'check_seconds': 2,
                'rules_observed': {'smt': 1, 'farkas': 1}, 'detailed_theory_hints_observed': {'farkas': 1},
                'dependency_nonempty_events': 0, 'callback_errors': 0, 'events_omitted_by_limits': 0,
                'input_quantifiers': 1, 'inventory_incomplete': False, 'no_event_observed_quantifiers': 1,
                'event_formulas_not_in_inventory': [], 'event_qids_not_in_inventory': [],
                'quantifiers_without_explicit_patterns': 0, 'matching_rows_without_input_term_examples': 1}
            write_json(root / 'quantifier-profile.json', [{'qid': 'Q', 'observation_status': 'no_event_observed'}])
            write_json(root / 'matching.json', [])
            write_json(root / 'clauses.json', [{'rule': 'smt', 'dependencies': []}, {'rule': 'farkas', 'dependencies': []}])
            records = [{'mode': 'baseline', 'rep': 1, 'path': str(root), 'report': base,
                        'process': {'seconds': 1.2}, 'native_profile': []},
                       {'mode': 'combined', 'rep': 1, 'path': str(root), 'report': combined,
                        'process': {'seconds': 2.2}, 'native_profile': []}]
            case = {'id': 'test', 'kind': 'verus_saved_query', 'original_result': 'unknown', 'expected_result': None}
            value = pilot.summarize_case(case, root, records, len)
            self.assertEqual(value['timings']['combined']['paired_outcome_mismatches'], 1)
            self.assertEqual(value['timings']['combined']['median_time_ratio_to_baseline'], 2)
            self.assertEqual(value['capabilities']['saved_theory_events'], 2)
            self.assertEqual(value['capabilities']['detailed_theory_hints_observed'], {'farkas': 1})
            self.assertIsNone(json.loads((root / 'payloads/quantifier_profile.json').read_text())[0]['native_profile_records'])

    def test_controls_are_independent_of_saved_study(self):
        cases, skipped = pilot.select_cases(Path('missing'), controls_only=True)
        self.assertEqual(len(cases), 4)
        self.assertFalse(skipped)
        self.assertEqual(cases[0]['expected_result'], 'sat')


if __name__ == '__main__':
    unittest.main()
