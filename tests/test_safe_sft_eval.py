import json
from pathlib import Path
import tempfile
import unittest
import types
import sys
from unittest.mock import patch

from baseline.storage import write_json, write_text, read_json
from sft_eval import __main__ as study
from sft_eval.inference import adapter_identity, Engine


class Tokenizer:
    def apply_chat_template(self, *args, **kwargs):
        return [1, 2, 3]


class FakeEngine:
    def __init__(self, adapter):
        self.tokenizer = Tokenizer()
        self.calls = []

    def generate(self, messages, seed):
        self.calls.append((messages, seed))
        return {'text': '```rust\nfn main() {}\n// seed=' + str(seed) + '\n```',
                'input_tokens': 3, 'output_tokens': 10, 'truncated': False, 'adapter_applied': True}


class Checker:
    def verify(self, path):
        text = path.read_text()
        success = 'seed=20261019' in text
        return {'success': success, 'error_type': None if success else 'verification',
                'stdout': '', 'stderr': 'assertion failed' if not success else ''}


class EvaluationTests(unittest.TestCase):
    def fixture(self, root, benchmark):
        plan = {'benchmark': benchmark, 'adapter': 'fake', 'system_prompt': 'instruction',
                'first_proposal_shared': benchmark == 'verusbench',
                'overlap_flagged_ids': [], 'tasks': [{'id': 'task', 'category': 'AX'}]}
        folder = root / 'inputs/task'
        write_text(folder / 'candidate.rs', 'fn main() {}\n')
        write_json(folder / 'verification.json', {'success': False, 'error_type': 'verification',
                                                  'stdout': '', 'stderr': 'assertion failed'})
        write_json(root / 'manifest.json', plan)
        return plan

    def execute(self, root, benchmark):
        plan = self.fixture(root, benchmark)
        engine = FakeEngine('fake')
        with patch.object(study, 'validate', return_value=plan), patch.object(study, 'Engine', return_value=engine), \
             patch.object(study, 'verifier', return_value=Checker()), \
             patch.object(study, 'pack', return_value={'queries': [{'id': 'q'}]}), \
             patch.object(study, 'preservation', return_value={'status': 'valid'}), \
             patch.dict(study.os.environ, {'LYNETTE_BIN': 'fake'}):
            study.run(root)
            before = len(engine.calls)
            study.run(root)
            self.assertEqual(len(engine.calls), before, 'Resume must not perform new inference')
        return engine

    def test_verusbench_shared_first_is_executed_once(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            engine = self.execute(root, 'verusbench')
            self.assertEqual(len(engine.calls), 3)
            a = read_json(root / 'with_internals/task/task.json')
            b = read_json(root / 'without_internals/task/task.json')
            self.assertEqual(a['attempts'][0]['path'], b['attempts'][0]['path'])
            self.assertEqual(a['attempts'][0]['proposal'], 1)
            self.assertFalse(a['attempts'][0]['exposed'])
            self.assertTrue(a['attempts'][1]['exposed'])
            self.assertFalse(b['attempts'][1]['exposed'])

    def test_solver_needs_receives_internals_before_first_proposal(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            engine = self.execute(root, 'solver-needs')
            self.assertEqual(len(engine.calls), 4)
            a = read_json(root / 'with_internals/task/task.json')
            b = read_json(root / 'without_internals/task/task.json')
            self.assertTrue(a['attempts'][0]['exposed'])
            self.assertFalse(b['attempts'][0]['exposed'])
            self.assertEqual(engine.calls[0][1], engine.calls[2][1])

    def test_pending_is_not_success(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            self.fixture(root, 'solver-needs')
            study.report(root)
            result = read_json(root / 'comparison.json')
            self.assertFalse(result['complete'])
            self.assertEqual(result['summaries']['with_internals']['completed'], 0)
            self.assertEqual(result['summaries']['with_internals']['through_proposal']['3'], 0)

    def test_smoke_adapter_is_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            write_json(root / 'adapter/adapter_config.json', {'peft_type': 'LORA', 'task_type': 'CAUSAL_LM', 'r': 16})
            write_json(root / 'training-provenance.json', {'model': 'Qwen/Qwen2.5-Coder-14B-Instruct',
                'revision': 'aedcc2d42b622764e023cf882b6652e646b95671', 'smoke': True})
            with self.assertRaisesRegex(ValueError, 'completed full'):
                adapter_identity(root / 'adapter')

    def test_native_engine_passes_adapter_to_every_generation(self):
        calls = []
        class NativeTokenizer:
            def apply_chat_template(self, *a, **kw):
                return 'rendered'
            def encode(self, *a, **kw):
                return [1, 2]
        class Native:
            def __init__(self, **kwargs):
                self.options = kwargs
            def get_tokenizer(self):
                return NativeTokenizer()
            def generate(self, prompts, params, **kwargs):
                calls.append(kwargs)
                return [types.SimpleNamespace(prompt_token_ids=[1, 2], outputs=[
                    types.SimpleNamespace(text='code', token_ids=[3], finish_reason='stop')])]
        class Request:
            def __init__(self, *args):
                self.args = args
        modules = {'vllm': types.SimpleNamespace(LLM=Native, SamplingParams=lambda **k: k),
                   'vllm.lora': types.ModuleType('vllm.lora'),
                   'vllm.lora.request': types.SimpleNamespace(LoRARequest=Request)}
        with patch.dict(sys.modules, modules), patch('sft_eval.inference.adapter_identity'), \
             patch('sft_eval.inference.prepare_model', return_value='local'):
            engine = Engine(Path('adapter'))
            engine.generate([], 1)
            engine.generate([], 2)
        self.assertTrue(engine.engine.options['enable_lora'])
        self.assertIs(calls[0]['lora_request'], engine.request)
        self.assertIs(calls[1]['lora_request'], engine.request)


if __name__ == '__main__':
    unittest.main()
