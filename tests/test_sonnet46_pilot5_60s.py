import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from baseline.storage import read_json, write_json
from scripts.run_sonnet46_pilot5_60s import IDS, LIMITS, summary


class PilotTests(unittest.TestCase):
    def test_selection_and_policy(self):
        self.assertEqual(len(set(IDS)), 5)
        self.assertNotIn('misc_bubble', IDS)
        self.assertEqual(LIMITS['seconds_per_proposal'], 60)
        self.assertEqual(LIMITS['output_tokens_per_request'], 8192)

    def test_resource_stop_separate_from_rejected_proof(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            for attempt, response, result in [
                (2, {'resource_exhausted': True, 'resource_stop_reason': 'time_budget'}, {'success': False}),
                (3, {'resource_exhausted': False}, {'success': False, 'edit_error': None})]:
                folder = root / 'with_internals' / IDS[0] / f'attempt_{attempt:02}'
                write_json(folder / 'response.json', response)
                write_json(folder / 'result.json', result)
            with contextlib.redirect_stdout(io.StringIO()):
                summary(root)
            report = read_json(root / 'pilot-summary.json')
            self.assertFalse(report['complete'])
            self.assertEqual(report['proposal_outcomes']['with_internals'], {'time_budget': 1, 'rejected_proposal': 1})


if __name__ == '__main__':
    unittest.main()
