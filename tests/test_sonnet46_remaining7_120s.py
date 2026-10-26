import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from baseline.storage import read_json, write_json
from scripts.run_sonnet46_remaining7_120s import IDS, LIMITS, summary


class RemainingTests(unittest.TestCase):
    def test_exact_remaining_tasks_plus_filter(self):
        original = {'misc_bubble', 'misc_conditional_average', 'misc_fib', 'misc_filter',
                    'misc_findmax', 'misc_len_intersect', 'misc_linearsearch', 'misc_map',
                    'misc_remove_all_greater', 'misc_reverse', 'misc_sum', 'misc_tail_triangle'}
        previous = {'misc_bubble', 'misc_conditional_average', 'misc_fib', 'misc_filter',
                    'misc_findmax', 'misc_len_intersect'}
        self.assertEqual(set(IDS), (original - previous) | {'misc_filter'})
        self.assertEqual(len(IDS), 7)
        self.assertEqual(LIMITS['seconds_per_proposal'], 120)
        self.assertEqual(LIMITS['output_tokens_per_request'], 8192)

    def test_summary_separates_resource_stops(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            folder = root / 'with_internals' / 'misc_filter' / 'attempt_03'
            write_json(folder / 'response.json', {'resource_exhausted': True,
                                                'resource_stop_reason': 'time_budget'})
            write_json(folder / 'result.json', {'success': False})
            with contextlib.redirect_stdout(io.StringIO()):
                summary(root)
            report = read_json(root / 'pilot-summary.json')
            self.assertEqual(report['policy']['seconds_per_proposal'], 120)
            self.assertEqual(report['proposal_outcomes']['with_internals'], {'time_budget': 1})
            self.assertFalse(report['complete'])


if __name__ == '__main__':
    unittest.main()
