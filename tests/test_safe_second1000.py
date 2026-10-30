import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json
from safe_internals import pipeline

SPEC = importlib.util.spec_from_file_location('safe_second1000', pipeline.ROOT / 'scripts/prepare_safe_internals_second1000.py')
second = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(second)


class SafeSecondBatchTests(unittest.TestCase):
    def test_frozen_batches_are_disjoint_in_ids_and_input_programs(self):
        first = read_json(pipeline.ROOT / 'configs/safe-repair-pilot1000.json')
        new = read_json(pipeline.ROOT / 'configs/safe-repair-second1000.json')
        self.assertEqual(new['count'], 1000)
        self.assertEqual(len(new['cases']), 1000)
        self.assertFalse(set(c['id'] for c in first['cases']) & set(c['id'] for c in new['cases']))
        self.assertFalse(set(c['input_code_sha256'] for c in first['cases']) &
                         set(c['input_code_sha256'] for c in new['cases']))
        self.assertEqual(new['dataset_sha256'], first['dataset_sha256'])
        first_config = read_json(pipeline.ROOT / 'configs/safe-internals-pilot1000.json')
        new_config = read_json(second.CONFIG)
        self.assertEqual({k: v for k, v in new_config.items() if k not in ('selection_file', 'selection_offset')},
                         {k: v for k, v in first_config.items() if k != 'selection_file'})

    def test_offset_selects_next_thousand_without_changing_first_order(self):
        first = {'cases': [{'id': str(i), 'input_code_sha256': str(i)} for i in range(1000)]}
        all_rows = {'cases': first['cases'] + [{'id': str(i), 'input_code_sha256': str(i)} for i in range(1000, 2000)],
                    'count': 2000, 'method': 'fixed'}
        with patch.object(second, 'original_select', return_value=all_rows) as choose, \
                patch.object(second, 'read_json', return_value=first):
            selected = second.selection([], 1000, 20261018)
        self.assertEqual(selected['cases'][0]['id'], '1000')
        self.assertEqual(selected['cases'][-1]['id'], '1999')
        choose.assert_called_once_with([], 2000, 20261018)

    def test_driver_restores_shared_selector_and_freezes_its_provenance(self):
        before = pipeline.select
        with tempfile.TemporaryDirectory() as work:
            output = Path(work)
            def prepare(dataset, root, config):
                self.assertIs(pipeline.select, second.selection)
                write_json(root / 'frozen-files.json', {})
            with patch.object(pipeline, 'prepare', side_effect=prepare):
                second.prepare(Path('dataset'), output)
            self.assertIs(pipeline.select, before)
            self.assertEqual(read_json(output / 'selection-driver.json')['offset'], 1000)
            self.assertIn('selection-driver.py', read_json(output / 'frozen-files.json'))
            with patch.object(pipeline, 'prepare', side_effect=RuntimeError('failure')):
                with self.assertRaises(RuntimeError):
                    second.prepare(Path('dataset'), output)
            self.assertIs(pipeline.select, before)


if __name__ == '__main__':
    unittest.main()
