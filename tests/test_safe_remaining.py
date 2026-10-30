import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json
from safe_internals import pipeline

SPEC = importlib.util.spec_from_file_location('safe_remaining', pipeline.ROOT / 'scripts/prepare_safe_internals_remaining.py')
remaining = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remaining)
COVERAGE_SPEC = importlib.util.spec_from_file_location('safe_coverage', pipeline.ROOT / 'scripts/report_safe_full_coverage.py')
coverage = importlib.util.module_from_spec(COVERAGE_SPEC)
COVERAGE_SPEC.loader.exec_module(coverage)


class SafeRemainingTests(unittest.TestCase):
    def test_full_coverage_marks_missing_rows_instead_of_claiming_completion(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            first, second, rest = root / 'first', root / 'second', root / 'rest'
            key = read_json(pipeline.ROOT / 'configs/safe-repair-pilot1000.json')['cases'][0]['id']
            result_path = first / 'examples' / key / 'result.json'
            write_json(result_path, {'id': key, 'target_success': True, 'status': 'internals_available',
                                     'training_eligibility': {'eligible': True}})
            with patch.object(Path, 'exists', lambda p: p == result_path):
                result = coverage.report(first, second, rest, root / 'report')
            self.assertEqual(result['expected'], 13768)
            self.assertEqual(result['completed'], 1)
            self.assertEqual(len(result['missing']), 13767)
            self.assertFalse(result['complete'])
            self.assertEqual(result['eligible_with_internals'], 1)

    def test_four_frozen_shards_cover_all_repair_rows_without_id_overlap(self):
        first = read_json(pipeline.ROOT / 'configs/safe-repair-pilot1000.json')
        second = read_json(pipeline.ROOT / 'configs/safe-repair-second1000.json')
        previous = first['cases'] + second['cases']
        ids = {c['id'] for c in previous}
        cases = list(previous)
        template = read_json(pipeline.ROOT / 'configs/safe-internals-pilot1000.json')
        for batch in remaining.BATCHES:
            value = read_json(pipeline.ROOT / f'configs/safe-repair-remaining-{batch}.json')
            config = read_json(pipeline.ROOT / f'configs/safe-internals-remaining-{batch}.json')
            selected = {c['id'] for c in value['cases']}
            self.assertEqual(len(value['cases']), 2942)
            self.assertEqual(len(selected), 2942)
            self.assertFalse(ids & selected)
            ids.update(selected)
            cases.extend(value['cases'])
            self.assertEqual(value['dataset_sha256'], first['dataset_sha256'])
            self.assertEqual({k: v for k, v in config.items() if k not in ('examples', 'selection_file', 'remaining_shard')},
                             {k: v for k, v in template.items() if k not in ('examples', 'selection_file')})
        self.assertEqual(len(ids), 13768)
        self.assertEqual(len({c['input_code_sha256'] for c in cases}), 12844)
        self.assertTrue(all(c['id'] == f"safe-{c['index']:05d}" for c in cases))

    def test_duplicate_input_rows_are_not_discarded(self):
        prior = [{'id': f'safe-{i:05d}'} for i in range(2000)]
        rows = [{'prompt': 'The provided Verus code contains errors.'} for _ in range(2000)]
        rows += [{'prompt': 'The provided Verus code contains errors.',
                  'input': '```rust\nproof fn f() {}\n```\nerror: assertion failed\n```rust\nassert(false);\n```',
                  'output': '```rust\nproof fn f() {}\n```'} for _ in range(8)]
        refs = [{'cases': prior[:1000]}, {'cases': prior[1000:]}]
        with patch.object(remaining, 'read_json', side_effect=refs), \
                patch.object(remaining, 'original_select', return_value={'cases': prior, 'unique_repair_inputs': 2001}):
            batches = remaining.selections(rows)
        all_cases = [c for value in batches.values() for c in value['cases']]
        self.assertEqual(len(all_cases), 8)
        self.assertEqual(len({c['id'] for c in all_cases}), 8)
        self.assertEqual(len({c['input_code_sha256'] for c in all_cases}), 1)
        self.assertTrue(all(len(v['cases']) == 2 for v in batches.values()))

    def test_preparer_restores_shared_selector_even_on_failure(self):
        before = pipeline.select
        with tempfile.TemporaryDirectory() as work:
            output = Path(work)
            def prepare(dataset, root, config):
                self.assertIsNot(pipeline.select, before)
                write_json(root / 'frozen-files.json', {})
            with patch.object(pipeline, 'prepare', side_effect=prepare):
                remaining.prepare(Path('dataset'), output, 'a')
            self.assertIs(pipeline.select, before)
            self.assertEqual(read_json(output / 'selection-driver.json')['batch'], 'a')
            self.assertIn('selection-driver.py', read_json(output / 'frozen-files.json'))
            with patch.object(pipeline, 'prepare', side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError):
                    remaining.prepare(Path('dataset'), output, 'a')
            self.assertIs(pipeline.select, before)


if __name__ == '__main__':
    unittest.main()
