from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from guidance_more.__main__ import inventory, order, validate
from guidance_study.editor import apply, regions

CODE = '''verus! {
fn f(n: usize) {
    let mut i = 0;
    while i < n
        invariant i <= n,
    {
        i = i + 1;
    }
}
}
'''


class Tokenizer:
    def encode(self, *args, **kwargs):
        return [1, 2]
    def apply_chat_template(self, *args, **kwargs):
        return [1, 2]


class MoreExamplesTests(unittest.TestCase):
    def test_order_reproducible_and_category_alternation(self):
        tasks = [{'id': str(i), 'category': 'A' if i < 3 else 'B'} for i in range(6)]
        self.assertEqual(order(tasks, 7), order(tasks[::-1], 7))
        self.assertEqual([t['category'] for t in order(tasks, 7)], ['A', 'B'] * 3)

    def test_only_validated_targets_selected_cache_and_no_old_ids(self):
        calls = []
        class Checker:
            def verify(self, path):
                calls.append(str(path))
                success = path.parent.name == 'reference' and 'bad' not in path.parts
                return {'success': success, 'error_type': None if success else 'verification',
                        'stdout': 'checked', 'stderr': ''}
        with tempfile.TemporaryDirectory() as tmp:
            pool, out = Path(tmp) / 'pool', Path(tmp) / 'selected'
            tasks = []
            site = next(s for s in regions(CODE) if s['kind'] == 'loop_invariants')
            action = {'edits': [{'site_id': site['id'], 'replacement': 'invariant i <= n, i >= 0,'}]}
            for key in ('good1', 'bad', 'good2'):
                folder = pool / 'tasks' / key
                write_text(folder / 'candidate.rs', CODE)
                write_text(folder / 'original.rs', CODE)
                write_text(folder / 'reference/candidate.rs', apply(CODE, action))
                write_json(folder / 'reference/action.json', action)
                tasks.append({'id': key, 'category': 'A', 'decisions': [{'site_id': site['id'], 'action': 'loop_invariants'}]})
            write_json(pool / 'manifest.json', {'schema': 'guidance-additional-provisional-v1',
                'source_tools': {}, 'files': inventory(pool), 'tasks': tasks, 'excluded_previous_ids': ['old1']})
            with patch('sft_eval.__main__.tool_hashes', return_value={}), \
                 patch('sft_eval.__main__.verifier', return_value=Checker()), \
                 patch('safe_internals.validation.preservation', return_value={'status': 'valid'}), \
                 patch.dict('os.environ', {'LYNETTE_BIN': 'fake'}):
                validate(pool, out, count=30, seed=7, tokenizer=Tokenizer())
                count = len(calls)
                validate(pool, out, count=30, seed=7, tokenizer=Tokenizer())
                self.assertEqual(count, len(calls))
            result = read_json(out / 'manifest.json')
            self.assertEqual({t['id'] for t in result['tasks']}, {'good1', 'good2'})
            self.assertEqual(result['requested'], 30)
            self.assertEqual(result['excluded_previous_ids'], ['old1'])
            self.assertTrue(all('\\' not in s for s in result['files']))
            self.assertEqual([r['id'] for r in result['audit'] if not r['selected']], ['bad'])


if __name__ == '__main__':
    unittest.main()
