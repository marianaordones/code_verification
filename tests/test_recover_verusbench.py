from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from baseline.storage import read_json, write_json, write_text
from scripts.recover_verusbench_lexerror import recover_attempt
from scripts.resume_verusbench_sonnet20 import resume


class RecoveryTests(unittest.TestCase):
    def test_only_known_recovery_permits_continuation(self):
        attempts = iter([1, 0])
        recovered = []
        self.assertEqual(resume('study', lambda: next(attempts), lambda p: recovered.append(p) or 1), 0)
        self.assertEqual(recovered, ['study'])

    def test_quota_or_unrelated_errors_stop_without_retry(self):
        calls = []
        self.assertEqual(resume('study', lambda: calls.append(1) or 7, lambda p: 0), 7)
        self.assertEqual(len(calls), 1)

    def folder(self, work, stderr='Result::unwrap() LexError'):
        folder = Path(work) / 'attempt_01'
        write_json(folder / 'integrity.json', {'status': 'checker_error', 'timed_out': False,
                   'returncode': 101, 'stderr': stderr, 'valid': False})
        write_json(folder / 'request.json', {'internals_exposed': True})
        write_json(folder / 'response.json', {'text': 'Prose before source fn main() {}'})
        write_text(folder / 'candidate.rs', 'Prose before source fn main() {}')
        return folder

    def test_known_lexerror_is_invalid_and_never_accepted(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.folder(work)
            raw_response = (folder / 'response.json').read_bytes()
            verifier = SimpleNamespace(verify=lambda *a: {'success': False, 'error_type': 'compilation'})
            self.assertTrue(recover_attempt(Path(work), folder, verifier))
            self.assertFalse(read_json(folder / 'result.json')['success'])
            self.assertEqual(read_json(folder / 'integrity.json')['status'], 'unparseable')
            self.assertEqual(read_json(folder / 'integrity-before-recovery.json')['status'], 'checker_error')
            self.assertEqual((folder / 'response.json').read_bytes(), raw_response)
            self.assertFalse(recover_attempt(Path(work), folder, verifier))

    def test_unrelated_panics_are_not_reclassified(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.folder(work, stderr='arbitrary panic')
            self.assertFalse(recover_attempt(Path(work), folder, None))
            self.assertFalse((folder / 'result.json').exists())

    def test_verifier_success_does_not_bypass_integrity(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.folder(work)
            with self.assertRaises(RuntimeError):
                recover_attempt(Path(work), folder, SimpleNamespace(verify=lambda *a: {'success': True, 'error_type': None}))
            self.assertFalse((folder / 'result.json').exists())


if __name__ == '__main__':
    unittest.main()
