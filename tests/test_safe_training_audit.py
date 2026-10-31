import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).resolve().parents[1] / 'scripts/audit_safe_training.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def test_frontend_requires_eligibility_and_evidence_of_no_queries(self):
        row = {'status': 'no_captured_failing_queries', 'input_error_type': 'compilation',
               'training_eligibility': {'eligible': True}}
        self.assertEqual(audit.category(row, {'queries': [], 'capture_errors': []}),
                         'eligible_frontend_error_without_internals')
        self.assertEqual(audit.category(row, None), 'eligible_other_without_internals')
        row['training_eligibility']['eligible'] = False
        self.assertEqual(audit.category(row, {'queries': []}), 'excluded_or_pending_validation')

    def test_unknown_without_packet_is_not_frontend(self):
        row = {'status': 'no_concordant_replay', 'input_error_type': 'verification',
               'training_eligibility': {'eligible': True}}
        self.assertEqual(audit.category(row, {'queries': []}), 'eligible_other_without_internals')
