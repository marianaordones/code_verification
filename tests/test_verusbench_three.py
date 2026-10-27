import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from baseline import verusbench_three as study
from baseline.runner import run_task
from baseline.storage import write_json, write_text, read_json


class Tokenizer:
    def encode(self, value, **kw):
        return list(value)
    def apply_chat_template(self, messages, **kw):
        return list(json.dumps(messages))


class VerusBenchThreeTests(TestCase):
    def exercise(self, success=False):
        config = read_json(study.CONFIG)
        calls, collections = [], []
        def generate(messages, config, seed):
            calls.append(messages)
            return {'text': 'verus! { proof fn f() {} }', 'rendered_prompt': 'prompt',
                'input_tokens': 100, 'output_tokens': 10, 'reasoning_tokens': 0, 'final_tokens': 10,
                'inference_seconds': 0.01, 'truncated': False, 'seed': seed}
        def verify(path):
            write_json(path.parent / 'solver/report.json', {'queries': [], 'capture_errors': []})
            return {'success': success, 'error_type': None if success else 'verification',
                    'stdout': 'diagnostic', 'stderr': '', 'seconds': 0.01}
        def collect(folder, code, verification, action, history, tokenizer, cfg, **kw):
            path = folder / 'feedback.json'
            if path.exists():
                return read_json(path)
            collections.append(folder)
            value = {'internals': {'queries': [{'id': 'q', 'quantifiers': [{'quantifier_smt': 'BASE_FORMULA'}]}]}, 'context': {}}
            if cfg.get('complement_token_budget'):
                value['complement'] = {'quantifiers_without_observed_events': ['EXTRA_FORMULA']}
            write_json(path, value)
            return value
        with tempfile.TemporaryDirectory() as tmp, patch('solver_needs_study.feedback.internals', side_effect=collect), patch('baseline.internals.internal_feedback', side_effect=AssertionError('legacy path must not run')):
            root = Path(tmp)
            original = root / 'original.rs'
            write_text(original, 'verus! { proof fn f() {} }')
            task = {'id': 'test', 'category': 'Misc', 'file': str(original)}
            write_json(root / 'run.json', {'tasks': [task]})
            engine = SimpleNamespace(tokenizer=Tokenizer(), generate=generate)
            verifier = SimpleNamespace(verify=verify)
            integrity = SimpleNamespace(validate=lambda *a: {'valid': True, 'seconds': 0.01, 'reason': ''})
            shared = root / 'shared' / 'test'
            run_task(task, config, root / 'shared', engine, verifier, integrity, study.Provider('no_internals', shared), max_proposals=1)
            for arm in study.ARMS:
                study.run_arm(task, arm, config, root, engine, verifier, integrity)
            report = study.compare(root)
            self.assertTrue(report['complete'])
            self.assertTrue(report['shared_first_valid'])
            self.assertEqual(len(calls), 1 if success else 7)
            for arm in study.ARMS:
                study.run_arm(task, arm, config, root, engine, verifier, integrity)
            self.assertEqual(len(calls), 1 if success else 7)
            if success:
                self.assertFalse(collections)
                self.assertTrue(all(s['solved_by_proposal'] == {'1': 1, '2': 1, '3': 1} for s in report['summaries'].values()))
                return
            self.assertEqual(len(collections), 3)  # shared initial, one next replay per internal arm
            requests = [read_json(root / a / 'test/attempt_01/request.json') for a in study.ARMS]
            self.assertEqual(requests[0]['messages'][0], requests[1]['messages'][0])
            self.assertEqual(requests[1]['messages'][0], requests[2]['messages'][0])
            self.assertNotIn('BASE_FORMULA', requests[0]['messages'][1]['content'])
            self.assertIn('BASE_FORMULA', requests[1]['messages'][1]['content'])
            self.assertNotIn('EXTRA_FORMULA', requests[1]['messages'][1]['content'])
            self.assertIn('EXTRA_FORMULA', requests[2]['messages'][1]['content'])
            for arm in study.ARMS:
                records = read_json(root / arm / 'test/task.json')['attempts']
                self.assertEqual([r['attempt'] for r in records], [0, 1, 2])
            # Integrity must still gate success in the common runner.
            bad = SimpleNamespace(validate=lambda *a: {'valid': False, 'status': 'invalid', 'seconds': 0.01, 'reason': 'changed code'})
            result = run_task(task, config, root / 'rejected', engine,
                SimpleNamespace(verify=lambda p: {'success': True, 'error_type': None, 'stdout': '', 'stderr': '', 'seconds': 0.01}),
                bad, study.Provider('no_internals', shared), max_proposals=1)
            self.assertFalse(result['success'])

    def test_failed_shared_proposal_two_repairs_and_resume(self):
        self.exercise()

    def test_shared_success_needs_no_repairs_or_replays(self):
        self.exercise(success=True)

    def test_context_guard(self):
        provider = study.Provider('no_internals', Path('.'))
        with self.assertRaisesRegex(ValueError, 'context'):
            provider.validate_prompt([{'content': 'long'}], SimpleNamespace(tokenizer=Tokenizer()), {'max_model_len': 10, 'max_tokens': 9})

    def test_real_packet_builder_uses_full_file_prompt_not_solver_needs_catalogue(self):
        config = read_json(study.CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'base24k/test/attempt_00'
            write_json(folder / 'verification.json', {'stdout': 'failed', 'stderr': ''})
            write_text(folder / 'solver/q.smt2', '(check-sat)')
            write_json(folder / 'solver/report.json', {'queries': [{'id': 'q', 'file': 'q.smt2', 'result': 'unknown'}], 'capture_errors': []})
            def execute(command, *args, **kwargs):
                output = Path(command[command.index('--output') + 1])
                write_json(output / 'report.json', {'status': 'completed', 'result': 'unknown', 'callback_errors': 0,
                    'instantiations_by_exact_formula': {}, 'instantiations_by_outer_qid': {}})
                write_json(output / 'input-quantifiers.json', {'ast_node_limit_hit': False, 'quantifiers_not_saved': 0,
                    'quantifiers': [], 'matching': [], 'quantifiers_found': 0})
                write_text(output / 'instantiations.jsonl', json.dumps({'quantifier_smt': '(forall ((x Int)) (= x x))',
                    'binding_terms_callback_order': ['0'], 'clause_literals_smt': ['true']}) + '\n')
                return {'returncode': 0, 'timed_out': False}
            engine = SimpleNamespace(tokenizer=Tokenizer())
            shared = root / 'shared/test'
            with patch('solver_needs_study.feedback.execute', side_effect=execute) as call, patch('solver_needs_study.feedback.upstream', side_effect=AssertionError('No Solver Needs catalogue')):
                text = study.Provider('base24k', shared).enrich(folder, 'verus! {}', 'failed', 'verus! {}', engine, config)
                extended = study.Provider('base24k_complement12k', shared).enrich(folder, 'verus! {}', 'failed', 'verus! {}', engine, config)
            self.assertEqual(call.call_count, 1)
            self.assertIn('forall', text)
            self.assertNotIn('<complementary_internals>', text)
            self.assertIn('<complementary_internals>', extended)
            prompt = study.messages('verus! {}', extended, original='verus! {}')
            self.assertLessEqual(len(engine.tokenizer.apply_chat_template(prompt)) + 4096, 65536)
