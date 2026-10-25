from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from verusbench_shared import __main__ as shared


class SharedStartTests(unittest.TestCase):
    def fixture(self, root):
        folder = root / 'inputs/case'
        write_text(folder / 'original.rs', 'fn main() {}')
        checked = {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''}
        write_json(folder / 'verification.json', checked)
        write_json(folder / 'integrity.json', {'valid': True, 'status': 'valid'})
        return checked

    def inference(self, calls):
        def generate(prompt, cfg, folder):
            calls.append((prompt, folder))
            return {'text': f'fn main() {{ let x = {len(calls)}; }}'}
        return SimpleNamespace(tokenizer=SimpleNamespace(apply_chat_template=lambda *a, **kw: [1]), generate_at=generate)

    def test_shared_success_generates_once_and_never_forks(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checked = self.fixture(root)
            calls = []
            inference = self.inference(calls)
            verifier = SimpleNamespace(verify=lambda *a: {**checked, 'success': True, 'error_type': None})
            guard = SimpleNamespace(validate=lambda *a: {'valid': True})
            for _ in range(2):
                shared.run_task(root, {'id': 'case'}, shared.vb.config(shared.CONFIG), inference, verifier, guard, shared.vb.ARMS)
            self.assertEqual(len(calls), 1)
            self.assertNotIn('<solver_internals>', calls[0][0][1]['content'])
            self.assertFalse((root / 'with_internals').exists())

    def test_two_arms_fork_from_exactly_same_first_proposal(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checked = self.fixture(root)
            calls = []
            results = iter([checked, {**checked, 'success': True, 'error_type': None},
                            {**checked, 'success': True, 'error_type': None}])
            verifier = SimpleNamespace(verify=lambda *a: next(results))
            guard = SimpleNamespace(validate=lambda *a: {'valid': True})
            def payload(folder, *a):
                value = {'availability': 'available', 'quantifiers': []}
                write_json(folder / 'payload.json', value)
                return value
            with patch.object(shared, 'build_payload', side_effect=payload):
                for _ in range(2):
                    shared.run_task(root, {'id': 'case'}, shared.vb.config(shared.CONFIG), self.inference(calls), verifier, guard, shared.vb.ARMS)
            self.assertEqual(len(calls), 3)
            first = read_json(root / 'shared/case/attempt_01/request.json')
            a = read_json(root / 'with_internals/case/attempt_02/request.json')
            b = read_json(root / 'without_internals/case/attempt_02/request.json')
            self.assertFalse(first['internals_exposed'])
            for key in ('common_messages_sha256', 'candidate_sha256', 'shared_start_sha256'):
                self.assertEqual(a[key], b[key])
            self.assertTrue(a['internals_exposed'])
            self.assertFalse(b['internals_exposed'])

    def test_selection_excludes_all_twenty_five_previous_ids(self):
        cfg = shared.vb.config(shared.CONFIG)
        selection = read_json(shared.ROOT / cfg['selection_file'])
        previous = read_json(shared.ROOT / 'configs/verusbench-sonnet20-selection-v2.json')
        old = set(previous['excluded_ids']) | {t['id'] for t in previous['tasks']}
        self.assertEqual(len(old), 25)
        self.assertEqual(len(selection['tasks']), 20)
        self.assertFalse(old & {t['id'] for t in selection['tasks']})

    def test_report_separates_shared_success_from_conditional_repair(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            manifest = {'selection': [{'id': 'easy'}, {'id': 'hard'}]}
            write_json(root / 'shared/easy/task.json', {'success': True, 'initially_verified': False})
            write_json(root / 'shared/hard/task.json', {'success': False, 'initially_verified': False})
            for arm in shared.vb.ARMS:
                write_json(root / arm / 'hard/task.json', {'success': True, 'attempts': [{'attempt': 2, 'success': True}]})
            with patch.object(shared, 'validate', return_value=manifest):
                report = shared.compare(root)
            self.assertEqual(report['shared_first_successes'], 1)
            for arm in shared.vb.ARMS:
                self.assertEqual(report['summaries'][arm]['repair_denominator_so_far'], 1)
                self.assertEqual(report['summaries'][arm]['repaired_at_2'], 1)
            self.assertTrue(report['complete'])


if __name__ == '__main__':
    unittest.main()
