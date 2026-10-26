from pathlib import Path
import tempfile
import unittest

from baseline.storage import read_json, write_json, write_text
from scripts.resume_sonnet46_remaining import pending_tasks, interrupted_calls, archive_interrupted


class ResumeTests(unittest.TestCase):
    def test_exact_remaining_twelve_and_original_order(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            manifest = {'selection': [{'id': f't{i}'} for i in range(50)]}
            for i in range(38):
                write_json(root / 'shared' / f't{i}' / 'task.json', {'success': i < 21, 'initially_verified': False})
                if i >= 21:
                    for arm in ('with_internals', 'without_internals'):
                        write_json(root / arm / f't{i}' / 'task.json', {'success': True})
            pending = pending_tasks(root, manifest)
            self.assertEqual([i for i, _ in pending], list(range(38, 50)))

    def fixture(self, work):
        root = Path(work)
        folder = root / 'shared/case/attempt_01'
        write_json(folder / 'claude-call.json', {'state': 'started'})
        write_json(folder / 'request.json', {'messages': [], 'seed': None})
        return root, folder

    def test_archiving_requires_explicit_authorization_and_preserves_request(self):
        with tempfile.TemporaryDirectory() as work:
            root, folder = self.fixture(work)
            before = (folder / 'request.json').read_bytes()
            with self.assertRaises(RuntimeError):
                archive_interrupted(root, [folder])
            self.assertTrue((folder / 'claude-call.json').exists())
            records = archive_interrupted(root, [folder], True)
            self.assertEqual((folder / 'request.json').read_bytes(), before)
            self.assertFalse((folder / 'claude-call.json').exists())
            self.assertEqual(read_json(root / records[0]['archive'] / 'claude-call.json')['state'], 'started')

    def test_saved_response_is_reused_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as work:
            root, folder = self.fixture(work)
            write_json(folder / 'response.json', {'text': 'already received'})
            self.assertEqual(interrupted_calls(root, [(0, {'id': 'case'})]), [])

    def test_nonempty_raw_stream_blocks_resubmission(self):
        with tempfile.TemporaryDirectory() as work:
            root, folder = self.fixture(work)
            write_text(folder / 'claude-stdout.jsonl', '{"type":"assistant"}')
            with self.assertRaises(RuntimeError):
                archive_interrupted(root, [folder], True)
            self.assertTrue((folder / 'claude-call.json').exists())

    def test_successful_saved_call_is_not_archived(self):
        with tempfile.TemporaryDirectory() as work:
            root, folder = self.fixture(work)
            write_json(folder / 'claude-call.json', {'state': 'completed', 'returncode': 0})
            self.assertEqual(interrupted_calls(root, [(0, {'id': 'case'})]), [])


if __name__ == '__main__':
    unittest.main()
