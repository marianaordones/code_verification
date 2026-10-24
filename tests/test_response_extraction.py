import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import digest, read_json, write_json, write_text
from solver_needs_study import actions
from solver_needs_study.audit_responses import audit


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.patch = patch.object(actions, 'upstream', return_value=(None, SimpleNamespace(LAWS={})))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.value = {**actions.EMPTY, 'statements': 'assert(true);'}
        self.payload = json.dumps(self.value)

    def test_direct_fenced_prose_and_legacy_standalone(self):
        for raw in (self.payload, '```json\n' + self.payload + '\n```',
                    'Mirror the loop.\n\n```json\n' + self.payload + '\n```\nExplanation.',
                    '```\n' + self.payload + '\n```'):
            info = {}
            self.assertEqual(actions.parse_response(raw, metadata=info), self.value)
            self.assertEqual(info['strict_json'], raw == self.payload)
            self.assertEqual(actions.parse_response(raw.replace('\n', '\r\n')), self.value)

    def test_reject_ambiguous_or_malformed_wrappers(self):
        block = '```json\n' + self.payload + '\n```'
        for raw in (block + '\n' + block, self.payload + '\n' + block,
                    '```rust\n' + self.payload + '\n```',
                    'Prose\n' + self.payload, 'Prose\n```\n' + self.payload + '\n```',
                    '```json\n' + self.payload, '```json\n{broken}\n```',
                    block + '\n~~~text\nextra\n~~~'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                actions.parse_response(raw)

    def test_no_duplicate_fields_or_schema_bypass(self):
        duplicate = self.payload[:-1] + ', "nla": true}'
        for payload in (duplicate, '[]', 'null', json.dumps({**self.value, 'extra': 1}),
                        json.dumps({**self.value, 'statements': 'assume(false);'}),
                        json.dumps({**self.value, 'law': 'unknown'})):
            for raw in (payload, 'Explanation\n```json\n' + payload + '\n```'):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    actions.parse_response(raw)

    def test_offline_audit_preserves_original_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as work:
            root, output = Path(work) / 'study', Path(work) / 'audit'
            task = {'prefix': 'verus! { proof fn f() {', 'suffix': '} }', 'proof_context': True}
            write_json(root / 'inputs/case/task.json', task)
            write_json(root / 'manifest.json', {'files': {'inputs/case/task.json':
                       digest((root / 'inputs/case/task.json').read_bytes())},
                       'cases': [{'id': 'case'}], 'config': {}})
            for arm in ('with_internals', 'without_internals'):
                folder = root / arm / 'case/attempt_01'
                write_json(folder / 'response.json', {'text': 'Mirror it.\n```json\n' + self.payload + '\n```'})
                write_json(folder / 'result.json', {'success': False, 'edit_error': 'old parser'})
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            verifier = SimpleNamespace(verify=lambda *a, **kw: {'success': True, 'error_type': None})
            report = audit(root, output, verifier)
            self.assertEqual(report['model_calls'], 0)
            self.assertEqual(report['unique_verifications'], 1)
            self.assertEqual(len(report['responses']), 2)
            self.assertTrue(all(r['audit_verifies'] for r in report['responses']))
            self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            with self.assertRaises(ValueError):
                audit(root, root / 'inside', verifier)
            with self.assertRaises(ValueError):
                audit(root, output, verifier)


if __name__ == '__main__':
    unittest.main()
