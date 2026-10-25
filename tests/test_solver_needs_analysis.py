import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/analyze_solver_needs.py'
spec = importlib.util.spec_from_file_location('solver_needs_analysis', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


CONFIG = {'max_attempts': 4, 'max_model_len': 49152, 'max_tokens': 4096,
          'internals_token_budget': 24576, 'model': 'Qwen/Qwen2.5-Coder-14B-Instruct', 'model_revision': 'test'}


def study(root, ids):
    save(root / 'manifest.json', {'config': CONFIG, 'cases': [{'id': key, 'paper_label': 'AX'} for key in ids]})
    for key in ids:
        save(root / 'inputs' / key / 'verification.json', {'success': False})


def completed(root, arm, key, win=None):
    attempts = [{'attempt': i, 'success': i == win} for i in range(1, (win or 4) + 1)]
    save(root / arm / key / 'task.json', {'success': win is not None, 'attempts': attempts})


class SolverNeedsAnalysisTests(unittest.TestCase):
    def test_quantifier_counts_use_evidence_from_previous_proposal(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            origin = root / 'with_internals/one/attempt_01'
            request_folder = root / 'with_internals/one/attempt_02'
            formula = '(forall ((x Int)) (! (= x x) :qid user_candidate_test))'
            save(origin / 'solver/report.json', {'queries': [
                {'id': 'a', 'result': 'unknown'}, {'id': 'b', 'result': 'unknown'}]})
            for q in ('a', 'b'):
                save(origin / f'internals/{q}/process.json', {'returncode': 0, 'timed_out': False})
                save(origin / f'internals/{q}/report.json', {'status': 'completed', 'result': 'unknown', 'instantiations_observed': 20})
                path = origin / f'internals/{q}/instantiations.jsonl'
                path.write_text('\n'.join(json.dumps({'quantifier_smt': formula,
                    'binding_terms_callback_order': [str(i)], 'clause_literals_smt': []}) for i in range(5)), encoding='utf-8')
            exposure = {'payload': {'queries': [{'id': 'a', 'quantifiers': [
                {'quantifier_smt': formula, 'selection_category': 'candidate_annotation', 'instances': [1, 2, 3]}]}]}, 'context': {}}
            result = audit.quantifier_counts(root, 'one', request_folder, exposure, {'max_quantifiers': 80, 'max_queries': 3})
            self.assertEqual(result['status'], 'available')
            self.assertEqual(result['available_groups'], 2)
            self.assertEqual(result['unique_formulas_available'], 1)
            self.assertEqual(result['saved_instances'], 10)
            self.assertEqual(result['observed_instantiation_events'], 40)
            self.assertEqual(result['candidate_groups_omitted'], 1)
            self.assertFalse(result['group_cap_reached'])
            self.assertEqual(result['omitted_groups_not_explained_by_group_or_background_caps'], 1)
            summary = audit.quantifier_summary([result])
            self.assertEqual(summary['available_groups_per_request']['mean'], 2)
            self.assertEqual(summary['by_proposal']['2']['sent_groups']['max'], 1)

    def test_missing_quantifier_evidence_is_not_measured_as_zero(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            result = audit.quantifier_counts(root, 'one', root / 'with_internals/one/attempt_01', {'payload': None}, {})
            self.assertEqual(result['status'], 'missing_evidence')
            self.assertIsNone(result['available_groups'])
            summary = audit.quantifier_summary([result])
            self.assertEqual(summary['available_groups_per_request']['n'], 0)
            self.assertEqual(summary['missing_or_invalid_evidence'], 1)

    def test_defaults_use_sibling_old_project_and_current_expanded_run(self):
        root = Path('/cluster/home/user/code_verification_git')
        defaults = audit.default_paths(root)
        old = root.parent / 'code_verification'
        self.assertEqual(defaults['initial'], [old / 'results/solver-needs-qwen14b-100/seed-20261018',
                                              old / 'results/solver-needs-qwen14b-remaining362/seed-20261018'])
        self.assertEqual(defaults['expanded'], root / 'results/solver-needs-qwen14b-100-internals24k/seed-20261018')

    def test_cumulative_new_and_pending_denominators_across_lots(self):
        with tempfile.TemporaryDirectory() as work:
            a, b = Path(work) / 'first', Path(work) / 'remaining'
            study(a, ['one', 'two'])
            study(b, ['three'])
            completed(a, 'with_internals', 'one', 2)
            completed(a, 'without_internals', 'one', 1)
            completed(a, 'with_internals', 'two')
            completed(a, 'without_internals', 'two', 4)
            save(b / 'with_internals/three/attempt_01/result.json', {'attempt': 1, 'success': True})
            with patch.object(audit, 'tokenizer_for', return_value=(None, 'unavailable')):
                result = audit.analyze_group([a, b])
            curve = result['all_selected_curve']
            self.assertEqual([r['with_internals']['cumulative_solved'] for r in curve], [1, 2, 2, 2])
            self.assertEqual([r['without_internals']['cumulative_solved'] for r in curve], [1, 1, 1, 2])
            self.assertEqual([r['without_internals']['new_solved'] for r in curve], [1, 0, 0, 1])
            self.assertEqual(result['repair_denominator'], 3)
            self.assertEqual(result['paired_completed'], 2)
            self.assertEqual(result['paired_completed_curve'][0]['with_internals']['cumulative_solved'], 0)
            self.assertFalse(result['complete'])

    def test_context_budget_errors_and_output_truncation_are_distinct(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            study(root, ['one'])
            folder = root / 'with_internals/one/attempt_01'
            payload = {'queries': [{'quantifiers': [{'instances': ['sample']}]}]}
            save(folder / 'request.json', {'parameters': {**CONFIG, 'internals_token_budget': 1}, 'internals_exposed': True})
            save(folder / 'response.json', {'input_tokens': 47000, 'output_tokens': 100,
                                           'rendered_prompt': 'small', 'truncated': True})
            save(folder / 'exposure.json', {'payload': payload})
            save(root / 'without_internals/one/error.json', {'error': 'Actual prompt exceeds context; no automatic truncation'})
            with patch.object(audit, 'tokenizer_for', return_value=(len, 'fake tokenizer')):
                result = audit.analyze_group([root])
            tokens = result['token_audit']
            self.assertEqual(tokens['input_plus_reserve_violations'], 1)
            self.assertEqual(tokens['actual_input_output_violations'], 0)
            self.assertEqual(tokens['truncated_outputs'], 1)
            self.assertEqual(tokens['internals_budget_violations'], 1)
            self.assertEqual(len(tokens['context_related_error_records']), 1)
            self.assertEqual(tokens['tokenizer_count_mismatches'], 1)

    def test_missing_tokenizer_is_not_zero_payload_tokens(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            study(root, ['one'])
            folder = root / 'with_internals/one/attempt_01'
            save(folder / 'request.json', {'internals_exposed': True})
            save(folder / 'response.json', {'input_tokens': 20000, 'output_tokens': 100})
            save(folder / 'exposure.json', {'payload': {'queries': [{'quantifiers': []}]}})
            with patch.object(audit, 'tokenizer_for', return_value=(None, 'unavailable')):
                result = audit.analyze_group([root])
            self.assertIsNone(result['token_rows'][0]['internals_tokens'])
            self.assertEqual(result['token_audit']['exposed_payloads_without_token_measurement'], 1)

    def test_duplicate_ids_rejected_and_initially_verified_excluded(self):
        with tempfile.TemporaryDirectory() as work:
            a, b = Path(work) / 'a', Path(work) / 'b'
            study(a, ['same'])
            study(b, ['same'])
            with patch.object(audit, 'tokenizer_for', return_value=(None, 'unavailable')):
                with self.assertRaisesRegex(ValueError, 'Duplicate task'):
                    audit.analyze_group([a, b])
                save(a / 'inputs/same/verification.json', {'success': True})
                result = audit.analyze_group([a])
            self.assertEqual(result['initially_verified'], 1)
            self.assertEqual(result['repair_denominator'], 0)

    def test_reports_and_missing_studies_remain_explicit(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            result = audit.analyze_group([root / 'missing'])
            self.assertFalse(result['complete'])
            self.assertTrue(result['issues'])
            audit.write_reports({'initial': result}, root / 'report')
            self.assertTrue((root / 'report/success_by_attempt.csv').exists())
            self.assertIn('completo: False', (root / 'report/report.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
