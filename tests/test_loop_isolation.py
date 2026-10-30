import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from baseline import verusbench_loop_isolation as study
from baseline import verusbench_local_v2 as local
from baseline.loop_isolation import force_false
from baseline.integrity import lexical_check
from baseline.storage import read_json, write_json, write_text
from baseline.provenance import tool_signature
from repair_study.relevance import source_context

CODE = 'use vstd::prelude::*;\nfn main() {}\nverus! {\nproof fn f() {\n    let x = 0;\n}\n}'

class Tokenizer:
    def encode(self, value, **kw):
        return list(value)
    def apply_chat_template(self, values, **kw):
        return list(json.dumps(values))

class IsolationTests(TestCase):
    def config(self):
        c = read_json(study.ROOT / 'configs/verusbench-qwen14b-three-arms.json')
        c.update(max_repairs=2, max_attempts=3, loop_isolation_fixed=True, collect_inventory=False,
            extra_system_prompt=(study.ROOT / 'prompts/verusbench-loop-isolation.txt').read_text(encoding='utf-8'))
        c.pop('complement_token_budget')
        return c

    def test_transform_only_fixed_setting_is_idempotent(self):
        code = """fn main() {}
verus! {
// loop_isolation(true) in this comment must stay.
spec fn s() -> int { 0 }
#[allow(unused)]
pub(crate) proof fn lemma() { }
#[verifier::loop_isolation(true)]
fn f() {
    #[verifier::loop_isolation(true)]
    while false { }
}
}"""
        result, audit = force_false(code)
        self.assertIn('fn main() {}', result)
        self.assertIn('// loop_isolation(true)', result)
        self.assertIn('spec fn s()', result)
        self.assertIn('pub(crate) proof fn lemma()', result)
        self.assertNotIn('#[verifier::loop_isolation(true)]', result)
        self.assertEqual(result.count('#[verifier::loop_isolation(false)]'), 3)
        self.assertEqual(force_false(result)[0], result)
        self.assertEqual(set(audit['functions']), {'lemma', 'f'})
        with self.assertRaises(ValueError):
            force_false('verus! { #[verifier::loop_isolation(UNKNOWN)] fn f() {} }')

    def test_split_is_frozen_disjoint_50_55(self):
        ids = ['T' + str(i) for i in range(105)]
        a = study.split_ids(ids)
        self.assertEqual(a, study.split_ids(ids[::-1]))
        self.assertEqual(len(a['batch50']), 50)
        self.assertEqual(len(a['batch55']), 55)
        self.assertFalse(set(a['batch50']) & set(a['batch55']))
        self.assertEqual(set(a['batch50']) | set(a['batch55']), set(ids))
        with self.assertRaises(ValueError):
            study.split_ids(ids[:-1])

    def test_stage_option_only_success_is_cached_without_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = force_false(CODE)[0]
            frozen = root / 'frozen/inputs/A'
            write_text(frozen / 'candidate.rs', code)
            write_text(frozen / 'original.rs', code)
            calls = []
            def verify(path):
                calls.append(path)
                self.assertIn('loop_isolation(false)', path.read_text())
                write_json(path.parent / 'solver/report.json', {'queries': [], 'capture_errors': [], 'new_setting': True})
                return {'success': True, 'error_type': None, 'stdout': '', 'stderr': ''}
            verifier = SimpleNamespace(verify=verify)
            integrity = SimpleNamespace(validate=lambda *a: {'valid': True, 'status': 'valid'})
            for _ in range(2):
                self.assertTrue(study.stage_initial(root, root / 'batch50', {'id': 'A'}, verifier, integrity))
            self.assertEqual(len(calls), 1)
            write_text(root / 'batch50/inputs/A/candidate.rs', 'tampered')
            with self.assertRaisesRegex(ValueError, 'Changed'):
                study.stage_initial(root, root / 'batch50', {'id': 'A'}, verifier, integrity)

    def test_two_repairs_only_and_option_success_separate(self):
        config = self.config()
        checked = {'valid': True, 'status': 'valid', 'reason': '', 'seconds': 0}
        identity = {n: {'path': n, 'sha256': 'sha'} for n in ('verus', 'z3', 'lynette')}
        identity.update(solver_api={}, versions={}, gpu={'name': 'fake'})
        manifest = {'config': config, 'tasks': [{'id': 'A'}, {'id': 'B'}], 'batches': {'batch50': ['A', 'B']},
            'tools': {n: tool_signature(identity[n]) for n in ('verus', 'z3', 'lynette')}, 'solver_api': {}, 'scope': 'test'}
        calls, feedback_calls = [], []
        def verify(path):
            code = path.read_text()
            self.assertIn('loop_isolation(false)', code)
            write_json(path.parent / 'solver/report.json', {'queries': [], 'capture_errors': [], 'new_setting': True})
            success = 'A' in path.parts or 'assert(true)' in code
            return {'success': success, 'error_type': None if success else 'verification', 'stdout': '', 'stderr': ''}
        def generate(messages, config, seed):
            calls.append(seed)
            self.assertIn('at most two localized repair proposals', messages[0]['content'])
            self.assertNotIn('four total proposals', messages[0]['content'])
            result = 'true' if seed == config['seed'] + 2 else 'false'
            return {'text': json.dumps({'site_id': 'R1', 'replacement': 'proof { assert(' + result + '); }'}),
                'input_tokens': 100, 'output_tokens': 10, 'inference_seconds': 0, 'truncated': False}
        def feedback(folder, frozen, original, code, verification, check, progress, engine, config, initial=False, **kw):
            source = frozen / 'initial' if initial else folder
            self.assertTrue(read_json(source / 'solver/report.json')['new_setting'])
            feedback_calls.append(folder)
            return {'internals': {'queries': [{'id': 'fresh', 'quantifiers': []}]}, 'context': source_context(code, verification)}
        with tempfile.TemporaryDirectory() as tmp, patch.object(study, 'validate', return_value=manifest), patch.object(study, 'collect', return_value=identity), patch.object(local, 'feedback', side_effect=feedback), patch.object(study, 'ObligationVerifier', return_value=SimpleNamespace(verify=verify)), patch.object(study, 'IntegrityValidator', return_value=SimpleNamespace(validate=lambda *a: checked)), patch.object(study, 'LocalVLLM', return_value=SimpleNamespace(tokenizer=Tokenizer(), generate=generate)) as engine:
            root = Path(tmp)
            write_json(root / 'manifest.json', {'fixture': True})
            for key in ('A', 'B'):
                code = force_false(CODE)[0]
                write_text(root / 'frozen/inputs' / key / 'original.rs', code)
                write_text(root / 'frozen/inputs' / key / 'candidate.rs', code)
            self.assertEqual(study.run_batch(root, 'batch50'), 0)
            self.assertEqual(study.run_batch(root, 'batch50'), 0)
            self.assertEqual(engine.call_count, 1)
            self.assertEqual(calls, [config['seed'] + 1, config['seed'] + 2])
            self.assertEqual(len(feedback_calls), 2)
            report = read_json(root / 'batch50/comparison.json')
            self.assertEqual((report['setting_only_successes'], report['model_repaired'], report['solved']), (1, 1, 2))
            self.assertEqual(report['solved_by_new_repairs'], {'0': 1, '1': 1, '2': 2})

    def test_aggregate_checks_partition_and_pending_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.config()
            ids = ['T' + str(i) for i in range(105)]
            batches = study.split_ids(ids)
            manifest = {'config': config, 'tasks': [{'id': k} for k in ids], 'batches': batches,
                'implementation': study.implementation(), 'files': {}, 'scope': 'test'}
            write_json(root / 'manifest.json', manifest)
            for key in batches['batch50']:
                write_json(root / 'batch50/with_internals' / key / 'task.json', {'id': key, 'success': True, 'status': 'setting_only_success', 'repairs': []})
            report = study.summarize(root)
            self.assertEqual((report['expected'], report['completed'], report['setting_only_successes']), (105, 50, 50))
            self.assertFalse(report['complete'])
            self.assertEqual(len(report['missing']), 55)
            manifest['batches']['batch55'][0] = manifest['batches']['batch50'][0]
            write_json(root / 'manifest.json', manifest)
            with self.assertRaisesRegex(ValueError, 'partition'):
                study.validate(root)
