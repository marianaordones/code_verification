import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


data = module('safe_sft_data')
train = module('train_safe_sft')


class FakeTokenizer:
    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        if add_generation_prompt:
            return [1, 2]
        return [1, 2, 3, 4]


class SFTTests(unittest.TestCase):
    def test_assistant_only_mask_and_no_truncation(self):
        messages = [{'role': 'user', 'content': 'input'}, {'role': 'assistant', 'content': 'target'}]
        result = train.encode(FakeTokenizer(), messages, 4)
        self.assertEqual(result['labels'], [-100, -100, 3, 4])
        with self.assertRaises(ValueError):
            train.encode(FakeTokenizer(), messages, 3)

    def test_prefix_mismatch_rejected(self):
        class Wrong(FakeTokenizer):
            def apply_chat_template(self, messages, tokenize, add_generation_prompt):
                return [9] if add_generation_prompt else [1, 2]
        with self.assertRaises(ValueError):
            train.encode(Wrong(), [{'role': 'assistant'}], 10)

    def test_overlap_ignores_comments_and_checks_target(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root / 'a.rs').write_text('fn f() { assert(true); }')
            (root / 'manifest.json').write_text(json.dumps({'tasks': [{'id': 'task', 'path': 'a.rs'}]}))
            result = data.overlap([{'input': 'nothing', 'output': '```rust\nfn f() { /* comment */ assert(true); }\n```'}], root / 'manifest.json')
            self.assertEqual(result['hits'][0]['match'], 'token_exact')
            self.assertEqual(result['hits'][0]['field'], 'output')

    def test_missing_batches_require_explicit_partial_and_generation_stays_out(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            rows = [{'prompt': 'The provided Verus code contains errors', 'input': '```rust\nfn f(){}\n```',
                     'output': '```rust\nfn f(){}\n```'},
                    {'prompt': 'Generate proof', 'input': '```rust\nfn g(){}\n```', 'output': '```rust\nfn g(){}\n```'}]
            dataset = root / 'source.json'
            dataset.write_text(json.dumps(rows))
            args = SimpleNamespace(dataset=dataset, benchmark=root / 'unused', first=root/'first',
                                   second=root/'second', remaining=root/'rest', output=root/'out',
                                   package='50x3', generation_validation=None, allow_partial=False, seed=42)
            with patch.object(data, 'overlap', return_value={'hits': []}):
                with self.assertRaisesRegex(ValueError, 'missing'):
                    data.build(args)


if __name__ == '__main__':
    unittest.main()
