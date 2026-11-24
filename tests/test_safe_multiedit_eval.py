import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baseline.storage import write_json, write_text
from localized_sft import evaluate
from localized_sft.editor import FORMAT

CODE = '''verus! {
fn f(n: usize) {
    proof { assert(n >= 0); }
}
}
'''


class EvaluationTests(unittest.TestCase):
    def test_paired_resume_and_rejection_feedback(self):
        identity = {'provenance': {'dataset_manifest': {'response_format': FORMAT, 'implementation': {}}}}
        generated, observed = [], []
        class Tokenizer:
            def apply_chat_template(self, *args, **kwargs):
                return [1, 2]
        class Engine:
            tokenizer = Tokenizer()
            def __init__(self, adapter):
                pass
            def generate(self, request, seed):
                generated.append(seed)
                user = request[1]['content']
                if seed == 20261018:
                    text = 'not JSON'
                else:
                    observed.append(user)
                    offered = json.loads(user.split('<editable_sites>\n')[1].split('\n</editable_sites>')[0])
                    site = next(s for s in offered if s['kind'] == 'proof_block')
                    text = json.dumps({'edits': [{'site_id': site['id'], 'replacement': 'proof { assert(n == n); }'}]})
                return {'text': text, 'input_tokens': 2, 'output_tokens': 10, 'truncated': False}
        class Checker:
            def verify(self, path):
                return {'success': True, 'error_type': None, 'stdout': 'ok', 'stderr': ''}
        with tempfile.TemporaryDirectory() as folder:
            source, output, adapter = [Path(folder) / s for s in ('source', 'output', 'adapter')]
            inputs = source / 'inputs' / 'case'
            write_text(inputs / 'candidate.rs', CODE)
            write_text(inputs / 'original.rs', CODE)
            write_json(inputs / 'verification.json', {'success': False, 'stdout': '', 'stderr': 'failed', 'error_type': 'verification'})
            write_json(source / 'manifest.json', {'benchmark': 'verusbench', 'tools': {},
                'tasks': [{'id': 'case', 'category': 'MBPP', 'status': 'eligible'}]})
            args = SimpleNamespace(output=output, source=source, adapter=adapter, benchmark='verusbench')
            with patch.object(evaluate, 'adapter_identity', return_value=identity), \
                 patch.object(evaluate, 'tool_hashes', return_value={}), \
                 patch.object(evaluate, 'implementation', return_value={}), \
                 patch.object(evaluate, 'Engine', Engine), \
                 patch.object(evaluate, 'verifier', return_value=Checker()), \
                 patch.object(evaluate, 'preservation', return_value={'status': 'valid'}), \
                 patch.object(evaluate, 'collect_events'), \
                 patch.object(evaluate, 'internals', return_value={'internals': {'queries': [{'id': 'q'}]}}), \
                 patch.dict('os.environ', {'LYNETTE_BIN': 'fake'}):
                evaluate.prepare(args)
                evaluate.run(output)
                evaluate.run(output)
                evaluate.report(output)
            self.assertEqual(generated, [20261018, 20261019, 20261018, 20261019])
            self.assertTrue(all('<previous_edit_rejection>' in s and 'json_error' in s for s in observed))
            result = json.loads((output / 'comparison.json').read_text())
            for arm in evaluate.ARMS:
                self.assertEqual(result['summaries'][arm]['solved'], 1)
                self.assertEqual(result['summaries'][arm]['categories'], {'json_error': 1, 'success': 1})
                self.assertEqual(result['summaries'][arm]['through_proposal']['1'], 0)
            self.assertTrue(result['complete'])
            self.assertEqual(result['summaries']['with_internals']['exposed_attempts'], 2)
            self.assertEqual(result['summaries']['without_internals']['exposed_attempts'], 0)


if __name__ == '__main__':
    unittest.main()
