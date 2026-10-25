from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import json

from baseline.storage import digest, read_json, write_json, write_text
from solver_needs_study import __main__ as study
from solver_needs_study import actions, feedback, reference
from solver_needs_study.download import REVISION


class ReferenceSettingsTests(unittest.TestCase):
    def fixture(self, root):
        config = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals24k.json')
        selection = root / 'selection-reference.json'
        write_json(selection, {'ids': ['old']})
        write_json(root / 'manifest.json', {'revision': REVISION, 'config': config, 'cases': [{'id': 'old'}]})
        for arm in ('with_internals', 'without_internals'):
            write_json(root / arm / 'old/task.json', {'success': False})
        code = 'verus! { proof fn example() {} }'
        verification = {'stdout': '', 'stderr': '', 'success': False}
        write_text(root / 'inputs/old/candidate.rs', code)
        write_json(root / 'inputs/old/verification.json', verification)
        write_json(root / 'inputs/old/feedback.json', {'context': {}})
        frozen = {**config, 'system_prompt_text': 'original system prompt'}
        messages = feedback.messages(code, verification, actions.EMPTY, {}, None, [], config=frozen)
        write_json(root / 'without_internals/old/attempt_01/request.json', {
            'messages': messages, 'common_messages_sha256': digest(json.dumps(messages, sort_keys=True).encode())})
        return config, selection

    def test_original_parameters_and_prompt_are_frozen_without_copying_candidates(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            root = Path(work)
            config, selection = self.fixture(root)
            with patch.object(reference, 'SELECTION', selection):
                frozen, info = reference.reference_settings(root, config)
            self.assertEqual({k: v for k, v in frozen.items() if k != 'system_prompt_text'}, config)
            self.assertEqual(frozen['system_prompt_text'], 'original system prompt')
            self.assertEqual(frozen['max_attempts'], 4)
            self.assertEqual(frozen['internals_token_budget'], 24576)
            self.assertEqual(frozen['max_quantifiers'], 50)
            self.assertEqual(frozen['max_instances_each'], 3)
            self.assertEqual(info['ids'], ['old'])
            reference.check_reference_prompt(root, frozen, 'old')

    def test_generation_change_and_incomplete_reference_are_rejected(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            root = Path(work)
            config, selection = self.fixture(root)
            with patch.object(reference, 'SELECTION', selection):
                with self.assertRaisesRegex(ValueError, 'configuration differs'):
                    reference.reference_settings(root, {**config, 'max_attempts': 3})
                (root / 'with_internals/old/task.json').unlink()
                with self.assertRaisesRegex(ValueError, 'incomplete'):
                    reference.reference_settings(root, config)

    def test_prompt_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            root = Path(work)
            config, selection = self.fixture(root)
            with patch.object(reference, 'SELECTION', selection):
                frozen, _ = reference.reference_settings(root, config)
            with self.assertRaisesRegex(ValueError, 'prompt/catalogue differs'):
                reference.check_reference_prompt(root, {**frozen, 'system_prompt_text': 'different'}, 'old')


if __name__ == '__main__':
    unittest.main()
