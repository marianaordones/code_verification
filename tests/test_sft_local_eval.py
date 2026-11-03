import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import write_json, write_text, read_json, digest
from sft_local_eval import __main__ as local


class Tokenizer:
    def apply_chat_template(self, *a, **kw):
        return [1, 2]


class Inference:
    def __init__(self, benchmark):
        self.benchmark = benchmark
        self.tokenizer = Tokenizer()
        self.calls = []
    def generate(self, messages, seed):
        self.calls.append((messages, seed))
        action = ({'mechanism': 'NLA', 'statements': '', 'law': None, 'nla': seed == 20261019}
                  if self.benchmark == 'solver-needs' else {'site_id': 'R1', 'replacement': 'proof { assert(true); }'})
        return {'text': json.dumps(action), 'input_tokens': 2, 'output_tokens': 8, 'truncated': False}


class Checker:
    def verify(self, path, nla=False):
        success = nla or 'assert(true)' in path.read_text()
        return {'success': success, 'error_type': None if success else 'verification', 'stdout': '', 'stderr': ''}


class LocalTests(unittest.TestCase):
    def execute(self, root, benchmark):
        task = {'id': 'task', 'category': 'NLA', 'status': 'eligible',
                'localized_proposals': 3 if benchmark == 'solver-needs' else 2}
        plan = {'benchmark': benchmark, 'adapter': 'fake', 'tasks': [task], 'overlap_flagged_ids': []}
        folder = root / 'inputs/task'
        slot = {'prefix': 'verus! { proof fn f() {', 'suffix': '} }', 'proof_context': True, 'line': 1}
        code = (local.render(slot, dict(local.EMPTY)) if benchmark == 'solver-needs'
                else 'fn f() -> i32 {\n    let x = 1;\n    x\n}\n')
        write_text(folder / 'candidate.rs', code)
        write_text(folder / 'original.rs', code)
        write_json(folder / 'slot.json', slot)
        write_json(folder / 'verification.json', {'success': False, 'stdout': '', 'stderr': '', 'error_type': 'verification'})
        write_json(root / 'manifest.json', plan)
        before = digest((folder / 'candidate.rs').read_bytes())
        inference = Inference(benchmark)
        def prompt(b, c, v, a, rejection, payload=None):
            return [{'role': 'user', 'content': json.dumps(payload)}]
        with patch.object(local, 'validate', return_value=plan), patch.object(local, 'Engine', return_value=inference), \
             patch.object(local, 'verifier', return_value=Checker()), patch.object(local, 'collect_events'), \
             patch.object(local, 'internals', return_value={'internals': {'queries': [{'id': 'q'}]}}), \
             patch.object(local, 'prompt', side_effect=prompt), \
             patch.object(local, 'preservation', return_value={'status': 'valid'}), \
             patch('solver_needs_study.actions.upstream', return_value=(None, type('Laws', (), {'LAWS': {}}))), \
             patch.dict(local.os.environ, {'LYNETTE_BIN': 'fake'}):
            local.run(root)
            count = len(inference.calls)
            local.run(root)
            self.assertEqual(len(inference.calls), count)
        self.assertEqual(digest((folder / 'candidate.rs').read_bytes()), before)
        return inference

    def test_solver_slot_actions_seeded_and_noop_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            inference = self.execute(root, 'solver-needs')
            self.assertEqual(len(inference.calls), 4)
            a = read_json(root / 'with_internals/task/task.json')
            b = read_json(root / 'without_internals/task/task.json')
            self.assertIn('No effective', a['attempts'][0]['edit_error'])
            self.assertTrue(a['attempts'][1]['success'])
            self.assertTrue(a['attempts'][0]['exposed'])
            self.assertFalse(b['attempts'][0]['exposed'])
            self.assertEqual(inference.calls[0][1], inference.calls[2][1])

    def test_verusbench_only_two_new_edits_follow_shared_proposal(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            inference = self.execute(root, 'verusbench')
            self.assertEqual(len(inference.calls), 2)
            a = read_json(root / 'with_internals/task/task.json')
            self.assertEqual(a['attempts'][0]['overall_proposal'], 2)
            comparison = read_json(root / 'comparison.json')
            self.assertEqual(comparison['summaries']['with_internals']['through_proposal'], {'1': 0, '2': 1, '3': 1})

    def test_editor_exclusions_reported_separately_from_missing(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            write_json(root / 'manifest.json', {'benchmark': 'verusbench', 'overlap_flagged_ids': [], 'tasks': [
                {'id': 'success', 'category': 'A', 'status': 'initial_success'},
                {'id': 'editor', 'category': 'A', 'status': 'editor_unavailable'},
                {'id': 'pending', 'category': 'A', 'status': 'eligible'}]})
            for arm in local.ARMS:
                write_json(root / arm / 'editor/task.json', {'id': 'editor', 'status': 'editor_unavailable', 'success': False, 'attempts': []})
            local.report(root)
            result = read_json(root / 'comparison.json')
            self.assertFalse(result['complete'])
            self.assertEqual(result['summaries']['with_internals']['eligible_failed'], 1)
            self.assertEqual(result['summaries']['with_internals']['through_proposal']['3'], 1)


if __name__ == '__main__':
    unittest.main()
