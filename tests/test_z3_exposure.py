from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from diagnostics.z3_exposure import control, payloads
from baseline.storage import read_json, write_json, write_text


class ExposureStudyTests(unittest.TestCase):
    def test_ground_control_preserves_the_negated_goal_and_requests_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = Namespace(timeout_ms=100, max_events=2, repeats=3)
            with patch('diagnostics.z3_exposure.cli_replay', return_value={
                    'result':'sat','model_is_confirmed_sat':True}), \
                 patch('diagnostics.z3_exposure.api_probe', return_value={'status':'unavailable'}):
                result = control('sat_arithmetic', root, 'fake', args, None)
            folder = Path(result['folder'])
            query = read_json(folder/'query.json')
            self.assertIn('(> x 0)', query['inspect_terms'])
            self.assertIn('(assert (not (> x 0)))', (folder/'query.smt2').read_text())
            self.assertEqual(result['stability']['results'], ['sat'] * 3)
            self.assertIn('standalone SMT control', result['scope'])

    def test_payload_sizes_do_not_invent_tokens_or_validate_unknown_models(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            write_text(folder/'query.smt2', '(check-sat)')
            write_json(folder/'api/report.json', {'result':'unknown',
                'model_status':'empty_candidate_after_unknown'})
            write_text(folder/'api/model.smt2', '')
            sizes = payloads(folder, None)
            self.assertIsNone(sizes['query_smt']['tokens'])
            self.assertEqual(sizes['query_smt']['bytes'], 11)
            self.assertEqual(sizes['model_empty_candidate_after_unknown']['bytes'], 0)
            self.assertIn('Not sent to an LLM', (folder/'package-preview.txt').read_text())
