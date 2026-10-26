import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/compare_solver_needs_three_proposals.py'
spec = importlib.util.spec_from_file_location('three_proposals_report', MODULE)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ThreeProposalsReportTests(unittest.TestCase):
    def test_fourth_success_excluded_and_partial_records_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def write(relative, value):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding='utf-8')
            write('manifest.json', {'config': {'internals_token_budget': 24576,
                'max_quantifiers': 50, 'max_instances_each': 3},
                'cases': [{'id': 'V-1', 'paper_label': 'AX'}, {'id': 'V-2', 'paper_label': 'FUEL'}]})
            write('with_internals/V-1/task.json', {'success': True, 'attempts': [
                {'attempt': n, 'success': n == 4} for n in range(1, 5)]})
            write('without_internals/V-1/task.json', {'attempts': [
                {'attempt': 1, 'success': False}, {'attempt': 2, 'success': True}]})
            for n in (1, 2, 3):
                write(f'with_internals/V-2/attempt_{n:02}/result.json', {'attempt': n, 'success': False})
            write('without_internals/V-2/attempt_01/result.json', {'attempt': 1, 'success': False})
            rows, _ = report.read_studies([root], 24576)
            summary = report.summarize(list(rows.values()))
            self.assertEqual(summary['arms']['with_internals']['solved'], 0)
            self.assertEqual(summary['arms']['with_internals']['success_only_after_three_ids'], ['V-1'])
            self.assertEqual(summary['arms']['with_internals']['completed_at_three'], 2)
            self.assertEqual(summary['arms']['without_internals']['solved'], 1)
            self.assertEqual(summary['arms']['without_internals']['missing_ids'], ['V-2'])
            self.assertFalse(summary['complete'])
            with self.assertRaisesRegex(ValueError, 'Duplicate task'):
                report.read_studies([root, root], 24576)

    def test_latex_contains_full_and_category_tables(self):
        rows = [{'id': 'V-1', 'label': 'AX', 'initially_verified': False,
                 'arms': {a: {'solved': a == report.ARMS[0], 'complete_at_three': True,
                    'first_success': 1 if a == report.ARMS[0] else None,
                    'success_only_after_three': False} for a in report.ARMS}}]
        groups = {key: report.summarize(rows) for key in ('previous_full', 'current_full')}
        text = report.latex(groups)
        self.assertEqual(text.count('\\begin{table}'), 2)
        self.assertIn('24,576', text)
        self.assertIn('AX & 1 & 1 & 0 & +1', text)
        self.assertIn('100.0\\%', text)


if __name__ == '__main__':
    unittest.main()
