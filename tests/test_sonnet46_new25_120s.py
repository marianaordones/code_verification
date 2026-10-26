import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json
from scripts import run_sonnet46_new25_120s as batch


class NewBatchTests(unittest.TestCase):
    def test_exact_selection_available_and_disjoint(self):
        tasks = batch.selected_tasks()
        self.assertEqual([t['id'] for t in tasks], batch.IDS)
        self.assertEqual(len(set(batch.IDS)), 25)
        self.assertEqual(batch.IDS[0], 'cloverbench_all_digits_strong')
        self.assertEqual(batch.IDS[-1], 'misc_simple_nested')
        self.assertEqual(batch.LIMITS['seconds_per_proposal'], 120)
        self.assertEqual(batch.LIMITS['output_tokens_per_request'], 8192)

    def test_unknown_id_is_not_silently_replaced(self):
        with patch.object(batch, 'IDS', ['not_a_real_id'] + batch.IDS[1:]):
            with self.assertRaisesRegex(ValueError, 'Unknown IDs'):
                batch.selected_tasks()

    def test_shared_success_and_resource_stop_counted_separately(self):
        with tempfile.TemporaryDirectory() as work, patch.object(batch, 'IDS', ['a', 'b', 'c']):
            root = Path(work)
            for name, value in [('a', {'success': True, 'initially_verified': False}),
                                ('b', {'success': False, 'initially_verified': False}),
                                ('c', {'success': False, 'initially_verified': True})]:
                write_json(root / 'shared' / name / 'task.json', value)
            for arm in batch.study.vb.ARMS:
                write_json(root / arm / 'b' / 'task.json', {'success': False})
            write_json(root / 'with_internals/b/attempt_03/response.json',
                       {'resource_exhausted': True, 'resource_stop_reason': 'time_budget'})
            with contextlib.redirect_stdout(io.StringIO()):
                batch.summary(root)
            result = read_json(root / 'pilot-summary.json')
            self.assertTrue(result['complete'])
            self.assertEqual(result['shared_successes'], 1)
            self.assertEqual(result['initially_verified'], 1)
            self.assertEqual(result['totals']['with_internals']['solved_including_shared'], 1)
            self.assertEqual(result['proposal_outcomes']['with_internals'], {'time_budget': 1})


if __name__ == '__main__':
    unittest.main()
