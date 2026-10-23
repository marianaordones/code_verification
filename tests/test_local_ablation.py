import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baseline.storage import digest, read_json, write_json, write_text
from local_ablation.feedback import ARMS, exposed_payload, messages, next_payload, fit_payload
from local_ablation.__main__ import prepare, validate, run_case, compare, run
from repair_study.__main__ import configuration
from repair_study.regions import regions

SOURCE = '''use vstd::prelude::*;
fn main() {}
verus! {
fn f(n: u64) {
    let mut i: u64 = 0;
    while i < n
        invariant
            i <= n,
    {
        i = i + 1;
    }
}
}
'''
VERIFY = {'success': False, 'stdout': '', 'stderr': 'error: invariant not satisfied\n --> /tmp/candidate.rs:9:5',
          'error_type': 'verification'}
CHECK = {'valid': True, 'status': 'valid', 'reason': ''}
PAYLOAD = {'availability': 'available', 'scope': 'diagnostic_replay_not_original_search',
           'source_context': {'failures': [{'expression_line': 'i <= n,'}]},
           'original_result': 'unknown', 'reason_unknown': 'SOLVER_REASON_SENTINEL',
           'statistics': {'conflicts': 654321},
           'sampling': {'selected_groups': 1, 'selected_instances': 1},
           'quantifiers': [{'selection_category': 'candidate_annotation',
                            'quantifier_smt': 'SOLVER_QUANTIFIER_SENTINEL',
                            'instances': [{'binding_terms_callback_order': ['12345'], 'clause_literals_smt': ['P(12345)']}]}]}


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(text[::4])

    def apply_chat_template(self, prompt, **kwargs):
        return self.encode(''.join(m['content'] for m in prompt))


class AblationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.source, self.root = self.parent / 'previous', self.parent / 'ablation'
        self.config = configuration()
        files = {}
        for name, value in [('candidate.rs', SOURCE), ('original.rs', SOURCE),
                            ('verification.json', VERIFY), ('integrity.json', CHECK), ('payload.json', PAYLOAD)]:
            path = self.source / 'inputs/task' / name
            if name.endswith('.json'):
                write_json(path, value)
            else:
                write_text(path, value)
            files['inputs/task/' + name] = digest(path.read_bytes())
        write_json(self.source / 'manifest.json', {'config': self.config, 'tool_hashes': {}, 'files': files,
            'cases': [{'id': 'task', 'category': 'Misc', 'selection_stratum': 'other_smt'}]})

    def prepared(self):
        prepare(SimpleNamespace(study=self.root, source_study=self.source))
        return read_json(self.root / 'manifest.json')['config']

    def test_only_solver_block_differs_and_control_has_no_solver_values(self):
        with_data = messages(SOURCE, SOURCE, VERIFY, CHECK, exposed_payload(ARMS[0], PAYLOAD))
        control = messages(SOURCE, SOURCE, VERIFY, CHECK, exposed_payload(ARMS[1], PAYLOAD))
        self.assertEqual(with_data[0], control[0])
        text = with_data[1]['content']
        block = text[text.index('<solver_internals>'):text.index('</solver_internals>') + len('</solver_internals>\n')]
        self.assertEqual(text.replace(block, ''), control[1]['content'])
        for sentinel in ('SOLVER_REASON_SENTINEL', 'SOLVER_QUANTIFIER_SENTINEL', '654321', 'withheld_by_design'):
            self.assertNotIn(sentinel, control[1]['content'])
        self.assertIn('<source_failure_context>', control[1]['content'])
        self.assertIn('<editable_sites>', control[1]['content'])

    def test_unavailable_internals_give_identical_prompts(self):
        unavailable = dict(PAYLOAD, availability='unavailable', quantifiers=[])
        self.assertEqual(messages(SOURCE, SOURCE, VERIFY, CHECK, exposed_payload(ARMS[0], unavailable)),
                         messages(SOURCE, SOURCE, VERIFY, CHECK, exposed_payload(ARMS[1], unavailable)))

    def test_control_never_replays_and_caches_source_context(self):
        with patch('local_ablation.feedback.build_payload', side_effect=AssertionError('control ran replay')):
            value = next_payload(ARMS[1], self.root, SOURCE, SOURCE, VERIFY, CHECK, Tokenizer(), self.config, '')
            again = next_payload(ARMS[1], self.root, SOURCE, SOURCE, VERIFY, CHECK, Tokenizer(), self.config, '')
        self.assertEqual(value, again)
        self.assertEqual(set(value), {'availability', 'source_context'})

    def test_prepare_reuses_initial_inputs_and_rejects_tampering(self):
        self.prepared()
        self.assertEqual((self.root / 'inputs/task/candidate.rs').read_bytes(), (self.source / 'inputs/task/candidate.rs').read_bytes())
        self.assertFalse((self.root / 'inputs/task/solver').exists())
        self.assertEqual(validate(self.root)['config']['task_count'], 1)
        write_text(self.root / 'inputs/task/candidate.rs', SOURCE + '// changed')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            validate(self.root)

    def test_modified_previous_input_is_rejected_before_run(self):
        write_text(self.source / 'inputs/task/candidate.rs', SOURCE + '// changed')
        with self.assertRaisesRegex(ValueError, 'failed its hash'):
            self.prepared()

    def test_fit_omits_whole_instances_and_reserves_output(self):
        large = copy.deepcopy(PAYLOAD)
        large['quantifiers'][0]['quantifier_smt'] = 'X' * 200000
        fitted = fit_payload(large, SOURCE, SOURCE, VERIFY, CHECK, Tokenizer(), self.config)
        self.assertEqual(fitted['quantifiers'], [])
        prompt = messages(SOURCE, SOURCE, VERIFY, CHECK, fitted)
        self.assertLessEqual(len(Tokenizer().apply_chat_template(prompt)) + self.config['max_tokens'], self.config['max_model_len'])

    def test_paired_repairs_resume_and_report_missing_pairs(self):
        config = self.prepared()
        site = next(s for s in regions(SOURCE) if s['kind'] == 'loop_invariants')
        edit = json.dumps({'site_id': site['id'], 'replacement': 'invariant\n i <= n,\n 0 <= i,\n'})
        calls = []

        class Inference:
            tokenizer = Tokenizer()

            def generate(self, prompt, config, seed):
                calls.append(seed)
                return {'text': edit, 'rendered_prompt': json.dumps(prompt), 'input_tokens': 100,
                        'output_tokens': 20, 'truncated': False, 'inference_seconds': 0.1}

        verifier = SimpleNamespace(verify=lambda path: dict(VERIFY, success=True, error_type=None))
        integrity = SimpleNamespace(validate=lambda *args: CHECK)
        for arm in ARMS:
            run_case(self.root, arm, 'task', config, Inference(), verifier, integrity)
        self.assertEqual(calls, [20261019, 20261019])
        report = compare(self.root)
        self.assertTrue(report['complete'])
        self.assertTrue(report['first_pair_check_passed'])
        self.assertFalse(report['paired'][0]['first_prompts_identical'])
        for arm in ARMS:
            run_case(self.root, arm, 'task', config, Inference(), verifier, integrity)
        self.assertEqual(len(calls), 2)
        (self.root / ARMS[1] / 'task/task.json').unlink()
        self.assertFalse(compare(self.root)['complete'])

    def test_two_repairs_have_same_seeds_and_control_has_no_replay(self):
        config = self.prepared()
        site = next(s for s in regions(SOURCE) if s['kind'] == 'loop_invariants')
        calls = []

        class Inference:
            tokenizer = Tokenizer()

            def generate(self, prompt, config, seed):
                calls.append(seed)
                return {'text': json.dumps({'site_id': site['id'], 'replacement': site['existing_text']}),
                        'rendered_prompt': json.dumps(prompt), 'input_tokens': 100, 'output_tokens': 20,
                        'truncated': False, 'inference_seconds': 0.1}

        verifier = SimpleNamespace(verify=lambda path: VERIFY)
        integrity = SimpleNamespace(validate=lambda *args: CHECK)
        with patch('local_ablation.feedback.build_payload', return_value=PAYLOAD) as replay:
            for arm in ARMS:
                result = run_case(self.root, arm, 'task', config, Inference(), verifier, integrity)
                self.assertEqual(len(result['repairs']), 2)
            self.assertEqual(replay.call_count, 1)
            for arm in ARMS:
                run_case(self.root, arm, 'task', config, Inference(), verifier, integrity)
            self.assertEqual(replay.call_count, 1)
        self.assertEqual(calls, [20261019, 20261020, 20261019, 20261020])

    def test_both_arms_share_one_engine_and_resume_requires_same_gpu_class(self):
        from unittest.mock import Mock
        tool_values = {k: {'path': k} for k in ('verus', 'z3', 'lynette')}
        previous = read_json(self.source / 'manifest.json')
        previous['tool_hashes'] = {k: {} for k in tool_values}
        write_json(self.source / 'manifest.json', previous)
        self.prepared()
        site = next(s for s in regions(SOURCE) if s['kind'] == 'loop_invariants')
        response = {'text': json.dumps({'site_id': site['id'], 'replacement': 'invariant\n i <= n,\n 0 <= i,\n'}),
                    'rendered_prompt': 'fake prompt', 'input_tokens': 100, 'output_tokens': 20,
                    'truncated': False, 'inference_seconds': 0.1}
        engine = SimpleNamespace(tokenizer=Tokenizer(), generate=Mock(return_value=response))
        verifier = SimpleNamespace(verify=lambda path: dict(VERIFY, success=True, error_type=None))
        integrity = SimpleNamespace(validate=lambda *args: CHECK)
        provenance = {'versions': {}, 'dependency_lock_sha256': 'same', 'gpu': {'name': 'L40S'}}
        args = SimpleNamespace(study=self.root)
        with patch('local_ablation.__main__.tools', return_value=tool_values), \
             patch('local_ablation.__main__.collect', return_value=provenance), \
             patch('local_ablation.__main__.LocalVLLM', return_value=engine) as load, \
             patch('local_ablation.__main__.ObligationVerifier', return_value=verifier), \
             patch('local_ablation.__main__.IntegrityValidator', return_value=integrity):
            self.assertEqual(run(args), 0)
            self.assertEqual(load.call_count, 1)
            self.assertEqual(engine.generate.call_count, 2)
            self.assertEqual(run(args), 0)
            self.assertEqual(load.call_count, 1)
            provenance['gpu']['name'] = 'A100'
            with self.assertRaisesRegex(ValueError, 'GPU class changed'):
                run(args)


if __name__ == '__main__':
    unittest.main()
