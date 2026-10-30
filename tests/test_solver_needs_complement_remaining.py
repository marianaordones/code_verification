from pathlib import Path
import unittest
from unittest.mock import patch

from baseline.storage import read_json
from baseline.prompts import ROOT
from solver_needs_study import reuse
from solver_needs_study.download import REVISION
from solver_needs_study.__main__ import configuration, study_arms
from solver_needs_study.single import summarize


class ComplementRemainingTests(unittest.TestCase):
    def test_only_augmented_arm_is_scheduled_and_missing_is_reported(self):
        config = configuration(ROOT / 'configs/solver-needs-qwen14b-complement16k-single.json')
        self.assertEqual(study_arms(config), ('with_internals',))
        manifest = {'config': config, 'cases': [{'id': 'a', 'paper_label': 'AX'},
                                               {'id': 'b', 'paper_label': 'NLA'}]}
        attempt = dict(success=True, attempt=2, unchanged=False, edit_error=None,
                       error_type=None, input_tokens=20, output_tokens=5, truncated=False,
                       internals_exposed=True, inference_seconds=1, processing_seconds=2)
        def saved(path):
            if path.name == 'verification.json':
                return {'success': False}
            return {'success': True, 'attempts': [attempt]}
        with patch('solver_needs_study.single.read_json', side_effect=saved), \
                patch.object(Path, 'exists', lambda p: 'a' in p.parts), \
                patch.object(Path, 'glob', return_value=[]), \
                patch('solver_needs_study.single.write_json'), \
                patch('solver_needs_study.single.write_text'):
            report = summarize(Path('/study'), manifest)
        self.assertFalse(report['complete'])
        self.assertFalse(report['paired_comparison'])
        self.assertEqual(set(report['summaries']), {'with_internals'})
        summary = report['summaries']['with_internals']
        self.assertEqual(summary['missing'], ['b'])
        self.assertEqual(summary['solved_by_attempt'], {'1': 0, '2': 1, '3': 1})

    def test_reuses_exact_remaining_ids_and_rejects_another_order(self):
        selection = read_json(ROOT / 'configs/solver-needs-tasks-remaining362.json')
        first = read_json(ROOT / 'configs/solver-needs-tasks100.json')
        self.assertEqual(len(selection['ids']), 362)
        self.assertFalse(set(selection['ids']) & set(first['ids']))
        old = read_json(ROOT / 'configs/solver-needs-qwen14b-internals24k.json')
        new = read_json(ROOT / 'configs/solver-needs-qwen14b-complement16k.json')
        manifest = {'revision': REVISION, 'cases': [{'id': key} for key in selection['ids']],
                    'config': old, 'files': {}}
        request = {'messages': [{'role': 'system', 'content': 'frozen prompt'}]}
        with patch.object(reuse, 'read_json', side_effect=[manifest, selection, request]), \
                patch.object(Path, 'exists', return_value=True):
            result, config = reuse.inspect_source(Path('/source'), Path('/destination'), new)
        self.assertEqual(result, manifest)
        self.assertEqual(config['system_prompt_text'], 'frozen prompt')
        self.assertEqual((config['max_attempts'], config['max_model_len']), (3, 61440))
        manifest['cases'].reverse()
        with patch.object(reuse, 'read_json', side_effect=[manifest, selection]):
            with self.assertRaisesRegex(ValueError, 'frozen remaining 362'):
                reuse.inspect_source(Path('/source'), Path('/destination'), new)


if __name__ == '__main__':
    unittest.main()
