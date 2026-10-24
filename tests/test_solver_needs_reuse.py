import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import digest, read_json, write_json, write_text
from solver_needs_study import actions, feedback, reuse
from solver_needs_study import __main__ as study
from solver_needs_study.download import REVISION


class ReuseTests(unittest.TestCase):
    def fixture(self, source):
        old = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals24k.json')
        new = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals32k.json')
        new['system_prompt_text'] = 'frozen original system prompt'
        folder = source / 'inputs/example'
        task = {'prefix': 'verus! { proof fn f() {', 'suffix': '} }', 'proof_context': True}
        code = actions.render(task, actions.EMPTY)
        verification = {'stdout': 'assertion failed', 'stderr': '', 'success': False}
        context = {'operation_families': []}
        write_json(folder / 'task.json', task)
        write_text(folder / 'candidate.rs', code)
        write_json(folder / 'verification.json', verification)
        write_text(folder / 'solver/q.smt2', '(check-sat)')
        sha = digest((folder / 'solver/q.smt2').read_bytes())
        write_json(folder / 'solver/report.json', {'queries': [{'id': 'q', 'file': 'q.smt2', 'result': 'unknown'}], 'capture_errors': []})
        saved = {'context': context, 'internals': {'queries': [{'id': 'q', 'query_sha256': sha, 'quantifiers': []}]}}
        write_json(folder / 'feedback.json', saved)
        write_json(folder / 'internals/q/process.json', {'returncode': 0, 'timed_out': False})
        write_json(folder / 'internals/q/report.json', {'status': 'completed', 'result': 'unknown'})
        event = {'quantifier_smt': '(forall ((x Int)) (! (= x x) :qid user_candidate_test))',
                 'binding_terms_callback_order': ['1'], 'clause_literals_smt': ['true']}
        write_text(folder / 'internals/q/instantiations.jsonl', json.dumps(event))
        common = feedback.messages(code, verification, actions.EMPTY, context, None, [], config=new)
        for arm in ('with_internals', 'without_internals'):
            write_json(source / arm / 'example/task.json', {'attempts': []})
            write_json(source / arm / 'example/attempt_01/request.json', {
                'messages': common, 'candidate_sha256': digest(code.encode()),
                'common_messages_sha256': digest(json.dumps(common, sort_keys=True).encode()),
                'seed': old['seed'] + 1, 'internals_exposed': False})
        manifest = {'revision': REVISION, 'config': old, 'files': {}, 'cases': [{'id': 'example'}]}
        write_json(source / 'manifest.json', manifest)
        return manifest, new

    def test_32k_keeps_fifty_groups_three_instances_and_three_proposals(self):
        old = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals24k.json')
        new = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals32k.json')
        self.assertEqual(new['max_attempts'], 3)
        self.assertEqual(new['internals_token_budget'], 32768)
        self.assertEqual(new['max_quantifiers'], 50)
        self.assertEqual(new['max_instances_each'], 3)
        self.assertEqual(new['seed'], old['seed'])
        self.assertEqual(new['max_model_len'], 49152)
        self.assertTrue(new['reuse_initial_events_required'])

    def test_repackages_saved_events_without_verifier_or_replay(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            source, target = Path(work) / 'old', Path(work) / 'new'
            manifest, config = self.fixture(source)
            previous = (source / 'inputs/example/feedback.json').read_bytes()
            with patch.object(feedback, 'execute', side_effect=AssertionError('No replay permitted')), \
                 patch.object(feedback, 'fits', return_value=True):
                reuse.prepare_case(source, target, 'example', manifest, config, None)
            value = read_json(target / 'inputs/example/feedback.json')
            self.assertEqual(len(value['internals']['queries'][0]['quantifiers']), 1)
            self.assertEqual(read_json(target / 'inputs/example/reuse.json')['new_replays'], 0)
            self.assertEqual((source / 'inputs/example/feedback.json').read_bytes(), previous)
            self.assertEqual((source / 'inputs/example/candidate.rs').read_bytes(),
                             (target / 'inputs/example/candidate.rs').read_bytes())

    def test_missing_event_file_fails_instead_of_replaying(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            source, target = Path(work) / 'old', Path(work) / 'new'
            manifest, config = self.fixture(source)
            (source / 'inputs/example/internals/q/instantiations.jsonl').unlink()
            with patch.object(feedback, 'execute', side_effect=AssertionError('No replay permitted')), \
                 self.assertRaises(FileNotFoundError):
                reuse.prepare_case(source, target, 'example', manifest, config, None)

    def test_seed_difference_is_rejected(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            source, target = Path(work) / 'old', Path(work) / 'new'
            manifest, config = self.fixture(source)
            config['seed'] += 1
            with self.assertRaisesRegex(ValueError, 'seed mismatch'):
                reuse.prepare_case(source, target, 'example', manifest, config, None)

    def test_source_validation_preserves_prompt_and_rejects_setting_change(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            source, target = Path(work) / 'old', Path(work) / 'new'
            manifest, config = self.fixture(source)
            for index in range(99):
                key = str(index)
                manifest['cases'].append({'id': key})
                for arm in ('with_internals', 'without_internals'):
                    write_json(source / arm / key / 'task.json', {})
            write_json(source / 'manifest.json', manifest)
            _, frozen = reuse.inspect_source(source, target, config)
            self.assertEqual(frozen['system_prompt_text'], 'frozen original system prompt')
            with self.assertRaisesRegex(ValueError, 'settings differ'):
                reuse.inspect_source(source, target, {**config, 'temperature': 0.2})

    def test_three_proposal_cap_in_run_case(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            source, target = Path(work) / 'old', Path(work) / 'new'
            manifest, config = self.fixture(source)
            with patch.object(feedback, 'fits', return_value=True):
                reuse.prepare_case(source, target, 'example', manifest, config, None)
            seeds = []
            def generate(prompt, config, seed):
                seeds.append(seed)
                return {'text': json.dumps(actions.EMPTY), 'rendered_prompt': 'saved', 'input_tokens': 1,
                        'output_tokens': 1, 'truncated': False, 'inference_seconds': 0}
            inference = SimpleNamespace(tokenizer=None, generate=generate)
            verifier = SimpleNamespace(verify=lambda *a, **kw: {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''})
            with patch.object(study, 'fits', return_value=True), \
                 patch.object(actions, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
                result = study.run_case(target, 'without_internals', {'id': 'example'}, config, inference, verifier)
            self.assertEqual(len(result['attempts']), 3)
            self.assertEqual(seeds, [config['seed'] + i for i in (1, 2, 3)])
            self.assertFalse((target / 'without_internals/example/attempt_04').exists())

    def test_both_variants_copy_identical_pool_events_and_pack_different_depths(self):
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            source, target_a, target_b, pool = [Path(work) / n for n in ('old', 'a', 'b', 'pool')]
            manifest, _ = self.fixture(source)
            write_json(pool / 'internals/q/process.json', {'returncode': 0, 'timed_out': False})
            write_json(pool / 'internals/q/report.json', {'status': 'completed', 'result': 'unknown'})
            events = [{'quantifier_smt': '(forall ((x Int)) (! (= x x) :qid user_candidate_test))',
                       'binding_terms_callback_order': [str(i)], 'clause_literals_smt': ['true']} for i in range(5)]
            write_text(pool / 'internals/q/instantiations.jsonl', '\n'.join(json.dumps(e) for e in events))
            with patch('solver_needs_study.shared_events.ensure_pool', return_value=pool), \
                 patch.object(feedback, 'fits', return_value=True), \
                 patch.object(feedback, 'execute', side_effect=AssertionError('No extra replay')):
                for target, shape in ((target_a, '80x3'), (target_b, '50x5')):
                    config = study.configuration(study.ROOT / f'configs/solver-needs-qwen14b-internals32k-{shape}.json')
                    config['system_prompt_text'] = 'frozen original system prompt'
                    reuse.prepare_case(source, target, 'example', manifest, config, None,
                                       shared_pool=Path(work) / 'cache')
            a = read_json(target_a / 'inputs/example/feedback.json')['internals']['queries'][0]['quantifiers'][0]
            b = read_json(target_b / 'inputs/example/feedback.json')['internals']['queries'][0]['quantifiers'][0]
            self.assertEqual(len(a['instances']), 3)
            self.assertEqual(len(b['instances']), 5)
            self.assertEqual((target_a / 'inputs/example/internals/q/instantiations.jsonl').read_bytes(),
                             (target_b / 'inputs/example/internals/q/instantiations.jsonl').read_bytes())


if __name__ == '__main__':
    unittest.main()
