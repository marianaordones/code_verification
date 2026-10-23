from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from baseline.__main__ import validate_config
from baseline.inference import LocalVLLM
from baseline.obligation import solver_feedback
from baseline.prompts import ROOT
from baseline.storage import read_json, write_json, write_text


class CharacterTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return list(''.join(m['content'] for m in messages))


class B96kTests(unittest.TestCase):
    def test_only_context_and_memory_settings_differ(self):
        config = read_json(ROOT / 'configs/qwen25coder14b-b-96k-150.json')
        previous = read_json(ROOT / 'configs/qwen25coder14b-b-150.json')
        validate_config(config, 'full')
        extra = {'experiment', 'max_model_len', 'rope_scaling', 'cpu_offload_gb',
                 'enable_chunked_prefill', 'max_num_batched_tokens'}
        self.assertEqual({k: v for k, v in config.items() if k not in extra},
                         {k: v for k, v in previous.items() if k not in extra})
        config['max_model_len'] = 65536
        with self.assertRaises(ValueError):
            validate_config(config, 'full')

    def test_engine_receives_extended_context_and_memory_settings(self):
        config = read_json(ROOT / 'configs/qwen25coder14b-b-96k-150.json')
        constructor = Mock()
        with patch.dict('sys.modules', {'vllm': SimpleNamespace(LLM=constructor)}), patch(
                'baseline.inference.prepare_model', return_value='/local/coder'):
            LocalVLLM(config)
        options = constructor.call_args.kwargs
        self.assertEqual(options['max_model_len'], 98304)
        self.assertEqual(options['rope_scaling'], config['rope_scaling'])
        self.assertEqual(options['cpu_offload_gb'], 12)
        self.assertEqual(options['dtype'], 'bfloat16')
        self.assertTrue(options['enable_chunked_prefill'])
        self.assertEqual(options['max_num_batched_tokens'], 2048)

    def test_same_complete_query_omitted_at_32k_is_included_at_96k(self):
        config = read_json(ROOT / 'configs/qwen25coder14b-b-96k-150.json')
        engine = SimpleNamespace(tokenizer=CharacterTokenizer())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder / 'solver/report.json', {'queries': [
                {'id': 'query-0000', 'file': 'query-0000.smt2', 'result': 'unknown'}], 'capture_errors': []})
            query = '(assert (= |' + 'x' * 40000 + '| 0))\n(check-sat)\n'
            write_text(folder / 'solver/query-0000.smt2', query)
            previous = dict(config, max_model_len=32768)
            small = solver_feedback(folder, 'code', 'diagnostic', 'original', engine, previous)
            self.assertNotIn(query, small)
            large = solver_feedback(folder, 'code', 'diagnostic', 'original', engine, config)
            self.assertIn(query, large)
            exposure = read_json(folder / 'solver/exposure.json')
            self.assertEqual(exposure['context_limit'], 98304)
            self.assertEqual(exposure['reserved_output_tokens'], 4096)
            self.assertTrue(exposure['complete_query_exposed'])


if __name__ == '__main__':
    unittest.main()
