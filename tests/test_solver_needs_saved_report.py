import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('saved_report', Path(__file__).resolve().parents[1] / 'scripts/report_solver_needs_saved.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class SavedReportTests(unittest.TestCase):
    def test_single_arm_reports_after_code_drift_and_keeps_missing_cases(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            cases = [{'id': name, 'paper_label': 'AX'} for name in ('a', 'b', 'c')]
            for case in cases:
                p = root / 'inputs' / case['id'] / 'verification.json'
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps({'success': False}))
            for name, successes in [('a', [False, True]), ('b', [False, False, False])]:
                p = root / 'with_internals' / name / 'task.json'
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps({'attempts': [{'attempt': i + 1, 'success': success} for i, success in enumerate(successes)]}))
            manifest = {'config': {'single_arm': 'with_internals', 'max_attempts': 3, 'complement_token_budget': 16384},
                        'cases': cases, 'files': {'inputs/a/verification.json': module.sha(root / 'inputs/a/verification.json')},
                        'implementation': {'missing_historical_code.py': 'old_hash'}}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            report = module.report(root, root / 'saved-report')
            self.assertFalse(report['complete'])
            self.assertEqual(set(report['summaries']), {'with_internals'})
            summary = report['summaries']['with_internals']
            self.assertEqual(summary['solved_by_attempt'], {'1': 0, '2': 1, '3': 1})
            self.assertEqual(summary['missing'], ['c'])
            self.assertEqual(summary['completed'], 2)
            self.assertTrue(report['frozen_files_validated'])
            self.assertEqual(report['current_implementation_changes'], ['missing_historical_code.py'])
            (root / 'inputs/a/verification.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
                module.report(root, root / 'saved-report')


if __name__ == '__main__':
    unittest.main()
