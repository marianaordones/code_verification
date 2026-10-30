import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baseline.integrity import lexical_check
from baseline.storage import write_json, write_text, read_json
from safe_internals import data, pipeline
from solver_needs_study import feedback


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(text)

    def apply_chat_template(self, messages, **kwargs):
        return list(json.dumps(messages))


def example(index=0):
    source = f'use vstd::prelude::*; verus! {{ proof fn f{index}() {{ assert(true); }} }}\n'
    return {'prompt': 'The provided Verus code contains errors. Debug it.',
            'input': f'Program:\n```rust\n{source}```\nError: assertion failed\n```rust\nassert(false);\n```',
            'output': f'```rust\n{source}```'}


class SafePilotTests(unittest.TestCase):
    def test_capture_unmodified_input_then_validate_original_target_and_keep_failed_row(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            folder = root / 'examples/a'
            row = example()
            row['output'] = row['output'].replace('proof fn', '#[verifier::loop_isolation(false)]\nproof fn')
            code, target = data.codes(row)
            write_json(folder / 'original.json', row)
            write_text(folder / 'candidate.rs', code)
            write_text(folder / 'target/reference.rs', target)
            calls = []
            def verify_input(path):
                calls.append('input')
                self.assertEqual(path.read_text(encoding='utf-8'), code)
                self.assertNotIn('loop_isolation(false)', path.read_text(encoding='utf-8'))
                write_json(folder / 'solver/report.json', {'queries': [], 'capture_errors': []})
                return {'success': False, 'stdout': 'error[E0308]: mismatched types', 'stderr': '',
                        'error_type': 'compilation', 'seconds': 1}
            def verify_target(args, *rest, **kwargs):
                calls.append('target')
                self.assertTrue((folder / 'feedback-20x3.json').exists())
                self.assertTrue((folder / 'feedback-50x3.json').exists())
                self.assertIn('loop_isolation(false)', Path(args[1]).read_text(encoding='utf-8'))
                return {'returncode': 0, 'timed_out': False, 'stdout': 'verification results:: 1 verified, 0 errors',
                        'stderr': '', 'seconds': 1}
            with patch.object(pipeline.PilotVerifier, 'verify', side_effect=verify_input), \
                 patch.object(pipeline, 'limited', side_effect=verify_target), \
                 patch.object(pipeline.IntegrityValidator, 'validate', return_value={'status': 'valid', 'valid': True}):
                result = pipeline.collect_case(root, {'id': 'a'}, read_json(pipeline.CONFIG),
                                               Tokenizer(), 'verus', 'z3', 'lynette')
            self.assertEqual(calls, ['input', 'target'])
            self.assertEqual(result['status'], 'no_captured_failing_queries')
            self.assertTrue(result['target_success'])
            a = read_json(folder / 'messages-20x3.json')
            b = read_json(folder / 'messages-50x3.json')
            self.assertEqual(a, b)
            self.assertEqual(a, read_json(folder / 'messages-baseline.json'))
            self.assertNotIn(target, a[1]['content'])

    def test_program_not_diagnostic_and_selection_does_not_use_target(self):
        rows = [example(i) for i in range(12)]
        rows.append({'prompt': 'Generate a proof', 'input': '', 'output': ''})
        selected = data.select(rows, 8)
        self.assertEqual(selected, data.select(rows, 8))
        source, target = data.codes(rows[0])
        self.assertNotIn('assert(false)', source)
        self.assertEqual(source, target)
        changed = [{**r, 'output': '```rust\nUNRELATED CORRECTED TARGET\n```'} for r in rows]
        self.assertEqual(selected, data.select(changed, 8))
        self.assertEqual(len({c['input_code_sha256'] for c in selected['cases']}), 8)

    def test_assume_tags_ignore_comments_strings_and_isolation_is_not_removed_from_source(self):
        code = '// assume(false);\nlet s = "assume(false)"; /* assume(false) */'
        self.assertFalse(data.code_tags(code)['assume_call'])
        self.assertTrue(data.code_tags(code + '\nassume(true);')['assume_call'])
        source = 'verus! { proof fn f() { assert(true); } }'
        target = source.replace('proof fn', '#[verifier::loop_isolation(false)]\nproof fn')
        comparison, count = data.preservation_target(source, target)
        self.assertEqual(count, 1)
        self.assertTrue(lexical_check(source, comparison)[0])
        self.assertIn('loop_isolation(false)', target)
        unchanged, count = data.preservation_target(target, target)
        self.assertEqual(unchanged, target)
        self.assertEqual(count, 0)
        removed, _ = data.preservation_target(target, source)
        self.assertFalse(lexical_check(target, removed)[0])
        assume_target = source.replace('assert(true)', 'assume(true)')
        comparison, _ = data.preservation_target(source, assume_target)
        self.assertFalse(lexical_check(source, comparison)[0])

    def test_family_components_join_source_target_and_labels(self):
        a, b, c = example(1), example(2), example(3)
        b['output'] = a['output']
        b['label'] = c['label'] = 'same-origin'
        self.assertEqual(len(set(data.families([a, b, c]))), 1)

    def test_two_packages_from_identical_evidence_without_replay_or_catalogue(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            write_json(folder / 'solver/report.json', {'queries': [{'id': 'q', 'file': 'q.smt2', 'result': 'unknown'}], 'capture_errors': []})
            write_text(folder / 'solver/q.smt2', '(check-sat)')
            write_json(folder / 'internals/q/process.json', {'returncode': 0, 'timed_out': False})
            write_json(folder / 'internals/q/report.json', {'status': 'completed', 'result': 'unknown',
                       'statistics': {'arith-conflicts': 7, 'quant instantiations': 32}})
            events = [{'quantifier_smt': f'(forall ((x Int)) (! (> x {i}) :qid user_candidate_{i}))',
                       'binding_terms_callback_order': ['1'], 'clause_literals_smt': ['true']} for i in range(32)]
            write_text(folder / 'internals/q/instantiations.jsonl', ''.join(json.dumps(e) + '\n' for e in events))
            raw = (folder / 'internals/q/instantiations.jsonl').read_bytes()
            outputs = []
            with patch.object(feedback, 'execute', side_effect=AssertionError('No second replay')), \
                 patch.object(feedback, 'upstream', side_effect=AssertionError('No Solver Needs law catalogue')):
                for name, (budget, groups) in pipeline.PACKAGES.items():
                    config = {'system_prompt_text': 'Repair input', 'max_queries': 3, 'normalize_statistics': True,
                              'internals_token_budget': budget, 'max_quantifiers': groups, 'max_instances_each': 3,
                              'max_model_len': 61440, 'max_tokens': 4096}
                    value = feedback.internals(folder, 'proof fn f() {}', {'stdout': '', 'stderr': ''}, {}, [], Tokenizer(),
                                               config, replay=False, message_builder=pipeline.message_builder,
                                               feedback_name=f'feedback-{name}.json')
                    payload = value['internals']
                    outputs.append(sum(len(q['quantifiers']) for q in payload['queries']))
                    self.assertLessEqual(len(Tokenizer().encode(json.dumps(payload, ensure_ascii=False, indent=2))), budget)
                    self.assertEqual(payload['queries'][0]['statistics']['arith conflicts'], 7)
                    self.assertIsNone(payload['queries'][0]['statistics']['time'])
            self.assertEqual(outputs, [20, 32])
            self.assertEqual((folder / 'internals/q/instantiations.jsonl').read_bytes(), raw)

    def test_outcome_mismatch_not_exposed(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            write_json(folder / 'solver/report.json', {'queries': [{'id': 'q', 'file': 'q.smt2', 'result': 'unknown'}], 'capture_errors': []})
            write_json(folder / 'internals/q/process.json', {'returncode': 0, 'timed_out': False})
            write_json(folder / 'internals/q/report.json', {'status': 'completed', 'result': 'sat'})
            config = {'system_prompt_text': 'Repair', 'max_queries': 3, 'max_quantifiers': 20,
                      'max_instances_each': 3, 'internals_token_budget': 12288, 'max_model_len': 61440, 'max_tokens': 4096}
            value = feedback.internals(folder, '', {'stdout': '', 'stderr': ''}, {}, [], Tokenizer(), config,
                                       replay=False, message_builder=pipeline.message_builder)
            self.assertIsNone(value['internals'])

    def test_unavailable_feedback_retains_same_records_targets_and_resume_skips_work(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            cases = [{'id': 'a', 'index': 0, 'paper_label': 'AX'}, {'id': 'b', 'index': 1}]
            write_json(root / 'manifest.json', {'selection': {'cases': cases}})
            for key in ('a', 'b'):
                folder = root / 'examples' / key
                write_json(folder / 'original.json', example())
                write_json(folder / 'metadata.json', {'family_id': 'family', 'input_tags': {'assume_call': False},
                                                     'target_tags': {'assume_call': False}})
            folder = root / 'examples/a'
            packages = {name: {'block_tokens': 0, 'budget': budget, 'input_tokens': 10,
                               'full_training_tokens': 20, 'groups_sent': 0, 'instances_sent': 0,
                               'groups_available_in_saved_events': 0, 'groups_omitted': 0,
                               'candidate_groups_omitted': 0, 'fits_collection_context_with_reserve': True}
                        for name, (budget, _) in pipeline.PACKAGES.items()}
            result = {'id': 'a', 'status': 'no_captured_failing_queries', 'input_error_type': 'compilation',
                      'target_success': False, 'preservation_status': 'unparseable', 'packages': packages, 'seconds': 1,
                      'capture_seconds': 1, 'replay_stage_seconds_this_session': 0,
                      'packing_seconds_this_session': 0, 'target_verification_seconds': 1}
            write_json(folder / 'result.json', result)
            messages = [{'role': 'user', 'content': 'Only input and diagnostics'}]
            for name in ('baseline', *pipeline.PACKAGES):
                write_json(folder / f'messages-{name}.json', messages)
            report = pipeline.summarize(root)
            self.assertFalse(report['complete'])
            self.assertEqual(report['missing'], ['b'])
            self.assertEqual(len((root / 'master.jsonl').read_text().splitlines()), 2)
            views = [json.loads((root / 'exports' / f'{n}.jsonl').read_text()) for n in ('baseline', *pipeline.PACKAGES)]
            self.assertEqual(views[0], views[1])
            self.assertEqual(views[1], views[2])
            with patch.object(pipeline.PilotVerifier, 'verify', side_effect=AssertionError('No repeat verification')):
                self.assertEqual(pipeline.collect_case(root, cases[0], {}, None, '', '', ''), result)


if __name__ == '__main__':
    unittest.main()
