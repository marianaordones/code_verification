import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from baseline.storage import read_json, write_json, write_text
from solver_needs_study import actions, data, feedback
from solver_needs_study import __main__ as study
from solver_needs_study.download import SOURCE, extract
from solver_needs_study.verify import StudyVerifier


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(text)

    def apply_chat_template(self, messages, **kwargs):
        return self.encode(json.dumps(messages))


class SolverNeedsTests(unittest.TestCase):
    def test_24k_config_only_changes_internal_sample_and_experiment_name(self):
        old = study.configuration()
        new = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals24k.json')
        self.assertEqual({k for k in old if old[k] != new[k]},
                         {'internals_token_budget', 'max_quantifiers', 'experiment'})
        self.assertEqual(new['internals_token_budget'], 24576)
        self.assertEqual(new['max_quantifiers'], 50)
        self.assertEqual(new['max_instances_each'], 3)
        self.assertEqual(new['max_model_len'], 49152)
        self.assertEqual(new['max_tokens'], 4096)

    def test_24k_allows_larger_feedback_but_keeps_output_reserve(self):
        old = study.configuration()
        new = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals24k.json')
        payload = {'queries': [{'sample': 'x' * 16000}]}
        verification = {'stdout': '', 'stderr': ''}
        with patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            self.assertFalse(feedback.fits('', verification, actions.EMPTY, {}, payload, [], Tokenizer(), old))
            self.assertTrue(feedback.fits('', verification, actions.EMPTY, {}, payload, [], Tokenizer(), new))
            self.assertFalse(feedback.fits('x' * 40000, verification, actions.EMPTY, {}, payload, [], Tokenizer(), new))

    def test_24k_selection_caps_fifty_groups_three_instances_each(self):
        config = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals24k.json')
        events = [{'quantifier_smt': f'(forall ((x Int)) (! (= x x) :qid user_candidate_{i}))',
                   'binding_terms_callback_order': [str(j)], 'clause_literals_smt': ['true']}
                  for i in range(55) for j in range(4)]
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            write_json(folder / 'solver/report.json', {'queries': [{'id': 'q', 'file': 'q.smt2', 'result': 'unknown'}],
                                                      'capture_errors': []})
            write_text(folder / 'solver/q.smt2', '(check-sat)')
            output = folder / 'internals/q'
            write_json(output / 'report.json', {'status': 'completed', 'result': 'unknown'})
            write_text(output / 'instantiations.jsonl', '\n'.join(json.dumps(e) for e in events))
            with patch.object(feedback, 'execute', return_value={'returncode': 0, 'timed_out': False}), \
                 patch.object(feedback, 'fits', return_value=True):
                result = feedback.internals(folder, '', {'stdout': '', 'stderr': ''}, actions.EMPTY,
                                            [], Tokenizer(), config)
            groups = result['internals']['queries'][0]['quantifiers']
            self.assertEqual(len(groups), 50)
            self.assertTrue(all(len(g['instances']) == 3 for g in groups))
            saved = read_json(folder / 'feedback.json')
            self.assertEqual(saved, result)

    def test_rust_installation_suppresses_self_update(self):
        script = (study.ROOT / 'scripts/cluster/stage_solver_needs.sh').read_text(encoding='utf-8')
        self.assertIn('export RUSTUP_AUTO_INSTALL=0', script)
        self.assertIn('rustup toolchain install 1.93.0 --profile minimal --no-self-update', script)
        self.assertLess(script.index('export RUSTUP_AUTO_INSTALL=0'), script.index('if ! rustup run'))

    def test_configuration_four_total_attempts(self):
        config = study.configuration()
        self.assertEqual(config['max_attempts'], 4)
        self.assertEqual(config['max_model_len'], 49152)
        self.assertEqual(config['max_tokens'], 4096)

    def test_action_rejects_trusted_and_escaping_code(self):
        for text in ('assume(false);', 'admit();', 'unsafe {}', '} fn bad() {}',
                     'assert(true); }', 'foo!();', '#[verifier::external_body] {}',
                     'assert((true);', 'return;', 'let x = 1; /*'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                actions.validate_statements(text)

    def test_slot_preserves_program_and_wraps_exec_context(self):
        task = {'prefix': 'verus! { fn f() {', 'suffix': '} }', 'proof_context': False}
        action = {**actions.EMPTY, 'statements': 'assert(true);'}
        code = actions.render(task, action)
        self.assertTrue(code.startswith(task['prefix']))
        self.assertTrue(code.endswith(task['suffix']))
        self.assertIn('proof {\nassert(true);\n}', code)
        self.assertEqual(actions.render(task, {**actions.EMPTY, 'nla': True}), actions.render(task, actions.EMPTY))
        self.assertNotIn('proof {', actions.render({**task, 'proof_context': True}, action))

    def test_json_fields_laws_and_types(self):
        fake = SimpleNamespace(LAWS={'law1': 'broadcast proof fn ax() {}'})
        with patch.object(actions, 'upstream', return_value=(None, fake)):
            self.assertEqual(actions.parse_response(json.dumps(actions.EMPTY)), actions.EMPTY)
            for invalid in ({**actions.EMPTY, 'law': 'hidden-answer'},
                            {**actions.EMPTY, 'nla': 1}, {**actions.EMPTY, 'extra': True}):
                with self.assertRaises(ValueError):
                    actions.parse_response(json.dumps(invalid))
            rendered = actions.render({'prefix': 'verus! {', 'suffix': '}', 'proof_context': True},
                                      {**actions.EMPTY, 'law': 'law1'})
            self.assertIn('broadcast use __solver_needs_law::ax;', rendered)
            self.assertIn(fake.LAWS['law1'], rendered)

    def test_only_internals_block_differs_between_first_prompts(self):
        fake = SimpleNamespace(LAWS={'law1': 'checked lemma'})
        args = ('PROGRAM', {'stdout': 'diagnostic', 'stderr': ''}, actions.EMPTY, {}, None, [])
        with patch.object(feedback, 'upstream', return_value=(None, fake)):
            control = feedback.messages(*args)
            treatment = feedback.messages(*args[:4], {'queries': [{'statistics': {'conflicts': 2}}]}, [])
        self.assertEqual(control[0], treatment[0])
        before, block = treatment[1]['content'].split('<solver_internals>\n')
        _, after = block.split('</solver_internals>\n')
        self.assertEqual(before + after, control[1]['content'])
        self.assertNotIn('solver_internals', control[1]['content'])

    def test_no_queries_does_not_execute_replay(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            write_json(folder / 'solver/report.json', {'queries': [], 'capture_errors': []})
            with patch.object(feedback, 'execute') as execute, patch.object(feedback, 'fits', return_value=True):
                result = feedback.internals(folder, '', {'stdout': '', 'stderr': ''}, actions.EMPTY,
                                            [], Tokenizer(), study.configuration())
            execute.assert_not_called()
            self.assertIsNone(result['internals'])
            self.assertEqual(result['availability'], 'unavailable')

    def test_token_budgets_include_reserved_output(self):
        fake = SimpleNamespace(LAWS={})
        with patch.object(feedback, 'upstream', return_value=(None, fake)):
            self.assertFalse(feedback.fits('', {'stdout': '', 'stderr': ''}, actions.EMPTY, {}, None, [],
                                          Tokenizer(), {'max_model_len': 4096, 'max_tokens': 4096}))
            self.assertFalse(feedback.fits('', {}, actions.EMPTY, {}, {'queries': ['too large']}, [],
                                          Tokenizer(), {'internals_token_budget': 1}))

    def test_verifier_flags_nla_without_capture(self):
        result = {'returncode': 0, 'stdout': 'verification results:: 1 verified, 0 errors',
                  'stderr': '', 'timed_out': False, 'seconds': 0.01}
        with tempfile.TemporaryDirectory() as work, patch('solver_needs_study.verify.execute', return_value=result) as execute:
            source = Path(work) / 'candidate.rs'
            write_text(source, 'verus! {}')
            verified = StudyVerifier('verus', 'z3').verify(source, nla=True, capture=False)
            self.assertTrue(verified['success'])
            command = execute.call_args.args[0]
            self.assertIn('--no-auto-recommends-check', command)
            self.assertIn('smt.arith.nl=true', command)
            self.assertEqual(command[command.index('--rlimit') + 1], '10.0')

    def test_archive_path_traversal_rejected(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('root/../escape', 'bad')
        with tempfile.TemporaryDirectory() as work, self.assertRaises(ValueError):
            extract(archive.getvalue(), Path(work))

    def test_initially_verified_is_not_model_success(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            folder = root / 'inputs/example'
            write_json(folder / 'task.json', {})
            write_text(folder / 'candidate.rs', 'unchanged')
            write_json(folder / 'verification.json', {'success': True})
            result = study.run_case(root, 'with_internals', {'id': 'example'}, {}, None, None)
            self.assertFalse(result['success'])
            self.assertTrue(result['initially_verified'])
            self.assertEqual(result['attempts'], [])

    def test_prepare_executes_only_removed_candidates(self):
        rows = [{'id': str(i), 'paper_label': label, 'release_label': label,
                 'corpus': 'VB', 'problem': str(i), 'source_path': str(i)} for i, label in enumerate(data.LABELS)]
        task = {'reference': 'ORIGINAL_ASSERTION', 'prefix': 'verus! { proof fn f() {',
                'suffix': '} }', 'proof_context': True, 'line': 1}
        checked = {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''}
        fake_transformers = SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **kw: Tokenizer()))
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            write_json(root / 'download-receipt.json', {})

            def save_feedback(folder, *args):
                write_json(folder / 'feedback.json', {'context': {}, 'internals': None, 'availability': 'unavailable'})

            with patch.object(study, 'SOURCE', root), patch.object(study, 'source'), \
                 patch.object(study, 'tools', return_value={}), patch.object(study, 'implementation', return_value={}), \
                 patch.object(study, 'selected_cases', return_value=rows), patch.object(study, 'split_task', return_value=task), \
                 patch.object(study, 'internals', side_effect=save_feedback), \
                 patch.object(study, 'prepare_model', return_value='cached-model'), \
                 patch.object(study.importlib.metadata, 'version', return_value='4.51.3'), \
                 patch.dict('sys.modules', {'transformers': fake_transformers}), \
                 patch.object(study, 'StudyVerifier') as verifier:
                verifier.return_value.verify.return_value = checked
                # tools() normally contains pinned binary identities; constructor only needs their paths.
                with patch.object(study, 'tools', return_value={'verus': {'path': 'verus'}, 'z3': {'path': 'z3'}}), \
                     patch.object(study, 'tool_signature', return_value='hash'):
                    study.prepare(SimpleNamespace(study=root / 'study', tasks=6))
                self.assertEqual(verifier.return_value.verify.call_count, 6)
                for call in verifier.return_value.verify.call_args_list:
                    self.assertNotIn('ORIGINAL_ASSERTION', call.args[0].read_text())
                ready = read_json(root / 'study/inputs/0/ready.json')
                self.assertTrue(ready['reference_placebo_restoration_not_rerun'])
                self.assertEqual(read_json(root / 'study/selected_ids.json')['ids'], [r['id'] for r in rows])

    def test_four_failed_proposals_and_resume_without_new_inference(self):
        config = study.configuration()
        checked = {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''}
        task = {'prefix': 'verus! { proof fn f() {', 'suffix': '} }', 'proof_context': True}
        seeds = []

        def generate(prompt, config, seed):
            seeds.append(seed)
            return {'text': json.dumps(actions.EMPTY), 'rendered_prompt': 'prompt', 'input_tokens': 1,
                    'output_tokens': 1, 'truncated': False, 'inference_seconds': 0.1}

        inference = SimpleNamespace(tokenizer=Tokenizer(), generate=generate)
        verifier = SimpleNamespace(verify=lambda *args, **kwargs: dict(checked))
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            frozen = root / 'inputs/example'
            write_json(frozen / 'task.json', task)
            write_text(frozen / 'candidate.rs', actions.render(task, actions.EMPTY))
            write_json(frozen / 'verification.json', checked)
            write_json(frozen / 'feedback.json', {'context': {}, 'internals': None, 'availability': 'unavailable'})
            with patch.object(study, 'fits', return_value=True), \
                 patch.object(study, 'messages', return_value=[{'role': 'user', 'content': 'same'}]), \
                 patch.object(actions, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
                result = study.run_case(root, 'without_internals', {'id': 'example'}, config, inference, verifier)
                self.assertEqual(len(result['attempts']), 4)
                self.assertTrue(all(a['unchanged'] and a['edit_error'] for a in result['attempts']))
                self.assertEqual(seeds, [config['seed'] + i for i in range(1, 5)])
                study.run_case(root, 'without_internals', {'id': 'example'}, config, inference, verifier)
                self.assertEqual(len(seeds), 4)

    @unittest.skipUnless((SOURCE / 'data/essential/essential_verus_z3.json').exists(), 'pinned data not downloaded')
    def test_published_462_assertions_match_source_and_frozen_100_ids(self):
        rows = data.cases()
        self.assertEqual(len(rows), 462)
        for row in rows:
            task = data.split_task(row)
            self.assertEqual(task['prefix'] + row['text'] + task['suffix'], task['reference'])
        selected = data.selected_cases()
        ids = [r['id'] for r in selected]
        self.assertEqual(len(ids), 100)
        self.assertEqual(len(set(ids)), 100)
        self.assertEqual(ids, read_json(data.SELECTION)['ids'])
        self.assertEqual(data.selected_cases(6), selected[:6])
        self.assertEqual(ids, [r['id'] for r in data.ordered_cases(20261018)[:100]])

    @unittest.skipUnless((SOURCE / 'data/essential/essential_verus_z3.json').exists(), 'pinned data not downloaded')
    def test_remaining_ids_are_exact_complement(self):
        path = study.ROOT / 'configs/solver-needs-tasks-remaining362.json'
        remaining = data.selected_cases(362, path)
        first = {r['id'] for r in data.selected_cases()}
        ids = {r['id'] for r in remaining}
        self.assertEqual(len(remaining), 362)
        self.assertEqual(len(ids), 362)
        self.assertFalse(first & ids)
        self.assertEqual(first | ids, {r['id'] for r in data.cases()})
        self.assertEqual(read_json(path)['excluded_ids'], read_json(data.SELECTION)['ids'])


if __name__ == '__main__':
    unittest.main()
