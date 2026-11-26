import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baseline.integrity import tokens
from guidance_study.editor import apply, classify, regions
from guidance_study.evaluate import prompt
from guidance_study import evaluate
from baseline.storage import write_json, write_text
from localized_sft.editor import EditError

CODE = '''use vstd::prelude::*;
verus! {
fn f(n: usize) -> (r: usize)
    ensures r == n,
{
    let mut i = 0;
    while i < n
        invariant i <= n,
    {
        i = i + 1;
    }
    proof { assert(i <= n); }
    i
}
}
'''


class GuidanceTests(unittest.TestCase):
    def test_multiple_regions_and_lemma_creation(self):
        sites = regions(CODE)
        self.assertNotIn('loop_isolation_option', [s['kind'] for s in sites])
        lemma = next(s for s in sites if s['kind'] == 'lemma_definitions')
        invariant = next(s for s in sites if s['kind'] == 'loop_invariants')
        action = {'edits': [{'site_id': lemma['id'], 'replacement': 'proof fn lemma_aux(x: int) ensures x == x { assert(x == x); }'},
                            {'site_id': invariant['id'], 'replacement': 'invariant i <= n, i >= 0,'}]}
        target = apply(CODE, action)
        self.assertIn('proof fn lemma_aux', target)
        self.assertIn('i >= 0', target)
        self.assertEqual(classify(lemma, action['edits'][0]['replacement'], CODE), 'lemmas')
        self.assertEqual(classify(invariant, action['edits'][1]['replacement'], CODE), 'loop_invariants')

    def test_unsafe_or_executable_helpers_rejected(self):
        site = next(s for s in regions(CODE) if s['kind'] == 'lemma_definitions')
        for code in ('fn exec_fn() {}', 'proof fn f() {}', 'proof fn lemma_bad() { assume(false); }',
                     '#[verifier::external_body] proof fn lemma_bad() {}', 'proof fn lemma_bad() { loop {} }'):
            with self.assertRaises(ValueError):
                apply(CODE, {'edits': [{'site_id': site['id'], 'replacement': code}]})

    def test_guidance_only_difference_and_no_reference_leak(self):
        sites = regions(CODE)
        decision = [{'site_id': sites[0]['id'], 'action': 'assertions_and_proof'}]
        control = prompt(CODE, 'failed', sites)
        guided = prompt(CODE, 'failed', sites, decision)
        self.assertEqual(control[0], guided[0])
        self.assertEqual(control[1]['content'], guided[1]['content'].split('<oracle_repair_guidance>')[0])
        suffix = guided[1]['content'].split('<oracle_repair_guidance>\n')[1].split('\n</oracle_repair_guidance>')[0]
        self.assertEqual(json.loads(suffix), decision)
        self.assertNotIn('replacement', suffix)
        self.assertNotIn('solver_internals', control[1]['content'])

    def test_repeated_sites_rejected(self):
        site = next(s for s in regions(CODE) if s['kind'] == 'proof_block')
        edit = {'site_id': site['id'], 'replacement': 'proof { assert(true); }'}
        with self.assertRaises(EditError):
            apply(CODE, {'edits': [edit, edit]})

    def test_paired_inference_and_resume_use_frozen_input(self):
        calls = []
        class Tokenizer:
            def apply_chat_template(self, *args, **kwargs):
                return [1, 2]
        class Engine:
            tokenizer = Tokenizer()
            def __init__(self, adapter):
                pass
            def generate(self, request, seed):
                calls.append((request, seed))
                if '<oracle_repair_guidance>' in request[1]['content']:
                    response = json.dumps(action)
                else:
                    response = 'bad JSON'
                return {'text': response, 'input_tokens': 2, 'output_tokens': 5,
                        'truncated': False, 'inference_seconds': .1}
        class Checker:
            def verify(self, path):
                success = 'reference' in path.parts or 'proposal_01' in path.parts
                return {'success': success, 'stdout': 'checked', 'stderr': '',
                        'error_type': None if success else 'verification'}
        sites = regions(CODE)
        site = next(s for s in sites if s['kind'] == 'proof_block')
        action = {'edits': [{'site_id': site['id'], 'replacement': 'proof { assert(true); }'}]}
        with tempfile.TemporaryDirectory() as tmp:
            dataset, output = Path(tmp) / 'dataset', Path(tmp) / 'output'
            task = {'id': 'case', 'category': 'Misc', 'decisions': [{'site_id': site['id'], 'action': 'assertions_and_proof'}]}
            folder = dataset / 'tasks/case'
            write_text(folder / 'candidate.rs', CODE)
            write_text(folder / 'original.rs', CODE)
            write_text(folder / 'reference/candidate.rs', apply(CODE, action))
            write_json(folder / 'reference/action.json', action)
            write_json(dataset / 'manifest.json', {'files': {}, 'source_tools': {}, 'tasks': [task]})
            args = SimpleNamespace(output=output, dataset=dataset, adapter=None, proposals=3)
            with patch.object(evaluate, 'tool_hashes', return_value={}), \
                 patch.object(evaluate, 'implementation', return_value={}), \
                 patch.object(evaluate, 'model_identity', return_value={'adapter': None}), \
                 patch.object(evaluate, 'verifier', return_value=Checker()), \
                 patch.object(evaluate, 'preservation', return_value={'status': 'valid'}), \
                 patch.object(evaluate, 'Engine', Engine), \
                 patch.dict('os.environ', {'LYNETTE_BIN': 'fake'}):
                evaluate.prepare(args)
                evaluate.run(output)
                evaluate.run(output)
            report = json.loads((output / 'comparison.json').read_text())
            self.assertTrue(report['complete'])
            self.assertEqual(report['summaries']['without_guidance']['solved'], 0)
            self.assertEqual(report['summaries']['with_guidance']['solved'], 1)
            self.assertEqual(len(calls), 4)
            self.assertEqual(calls[0][1], calls[3][1])
            for request, seed in calls:
                self.assertIn(CODE, request[1]['content'])


if __name__ == '__main__':
    unittest.main()
