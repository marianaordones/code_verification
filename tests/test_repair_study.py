import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from baseline.integrity import tokens
from baseline.prompts import ROOT
from diagnostics.z3_internals import api_env
from baseline.verifier import execute
from repair_study.regions import regions, apply_patch, spans
from repair_study.relevance import rank, source_context
from repair_study.feedback import build_payload, messages
from repair_study.__main__ import configuration, run_case, validate_bundle, implementation, prepare, compare

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


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(text[::4])

    def apply_chat_template(self, messages, **kwargs):
        return self.encode(''.join(m['content'] for m in messages))


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_region_patch_changes_only_offered_annotation(self):
        sites = regions(SOURCE)
        site = next(s for s in sites if s['kind'] == 'loop_invariants')
        code, selected = apply_patch(SOURCE, json.dumps({'site_id': site['id'],
                                    'replacement': 'invariant\n i <= n,\n 0 <= i,\n'}), sites)
        self.assertEqual(code[:site['start']], SOURCE[:site['start']])
        self.assertTrue(code.endswith(SOURCE[site['end']:]))
        self.assertIn('i = i + 1;', code)
        self.assertEqual(selected, site['id'])

    def test_proof_insert_rejects_extra_executable_text_and_unknown_site(self):
        sites = regions(SOURCE)
        site = next(s for s in sites if s['kind'] == 'insert_proof')
        with self.assertRaises(ValueError):
            apply_patch(SOURCE, json.dumps({'site_id': site['id'], 'replacement': 'proof { assert(true); } let x = 0;'}), sites)
        with self.assertRaises(ValueError):
            apply_patch(SOURCE, '{"site_id":"UNKNOWN","replacement":"proof {}"}', sites)
        with self.assertRaises(ValueError):
            apply_patch(SOURCE, '{"edits":[]}', sites)

    def test_comment_and_string_braces_are_not_regions(self):
        text = '// while false { invariant false, }\n' + SOURCE.replace('let mut i:', 'let s = r#"while false {"#;\n    let mut i:')
        self.assertEqual([t[0] for t in spans(text)], tokens(text))
        self.assertEqual(sum(s['kind'] == 'loop_invariants' for s in regions(text)), 1)

    def test_conditional_invariant_block_is_not_guessed_as_loop_body(self):
        text = SOURCE.replace('i <= n,', 'if i == 0 { true } else { i <= n },')
        self.assertFalse(any(s['kind'] == 'loop_invariants' for s in regions(text)))

    def test_relevance_and_source_context(self):
        context = source_context(SOURCE, {'stderr': 'error: assertion failed\n --> /tmp/candidate.rs:10:9', 'stdout': ''})
        self.assertEqual(context['failures'][0]['expression_line'].strip(), 'i = i + 1;')
        self.assertIn('add', context['operation_families'])
        self.assertEqual(rank('(! P :qid user_candidate__f_29)', context)[0], 0)
        self.assertEqual(rank('(! P :qid internal_raw_ptr_Metadata_box_axiom)', context)[0], 4)
        self.assertEqual(rank('(! P :qid prelude_add)', context)[0], 2)

    def test_ranked_payload_is_shared_and_never_contains_whole_query(self):
        folder = self.root / 'case'
        write_json(folder / 'solver/report.json', {'queries': [{'id': 'query-0000', 'file': 'q.smt2', 'result': 'unknown'}], 'capture_errors': []})
        write_text(folder / 'solver/q.smt2', 'COMPLETE_QUERY_MUST_NOT_LEAK')

        def fake_worker(*args, **kwargs):
            dest = folder / 'relevant-replay'
            write_json(dest / 'report.json', {'status': 'completed', 'result': 'unknown', 'statistics': {'conflicts': 3},
                       'instantiations_observed': 21, 'instantiations_saved': 21})
            events = []
            for n in range(20):
                events.append({'quantifier_smt': f'(forall ((x Int)) (! (= x x) :qid internal_box_axiom_{n}))',
                               'binding_terms_callback_order': ['0'], 'clause_literals_smt': ['true']})
            events.append({'quantifier_smt': '(forall ((j Int)) (! (P j) :qid user_candidate__f_29))',
                           'binding_terms_callback_order': ['i'], 'clause_literals_smt': ['(not Q)', '(P i)']})
            write_text(dest / 'instantiations.jsonl', ''.join(json.dumps(e) + '\n' for e in events))
            return {'returncode': 0, 'timed_out': False}

        verification = {'stdout': '', 'stderr': 'error: assertion failed\n --> candidate.rs:10:9'}
        with patch('repair_study.feedback.execute', side_effect=fake_worker):
            payload = build_payload(folder, SOURCE, SOURCE, verification, {'valid': True}, Tokenizer(), configuration())
        self.assertEqual(payload['quantifiers'][0]['selection_category'], 'candidate_annotation')
        self.assertLessEqual(sum(q['selection_category'] == 'representation' for q in payload['quantifiers']), 2)
        for mode in ('full', 'local'):
            prompt = messages(mode, SOURCE, SOURCE, verification, {'valid': True}, payload)
            self.assertIn('user_candidate__f_29', prompt[1]['content'])
            self.assertNotIn('COMPLETE_QUERY_MUST_NOT_LEAK', prompt[1]['content'])
            self.assertLessEqual(len(Tokenizer().apply_chat_template(prompt)) + 4096, 49152)

    def test_both_modes_reuse_saved_responses_and_record_no_progress(self):
        config = configuration()
        for mode in ('full', 'local'):
            root = self.root / mode
            frozen = root / 'inputs/test'
            for name in ('original.rs', 'candidate.rs'):
                write_text(frozen / name, SOURCE)
            verification = {'success': False, 'stdout': '', 'stderr': 'assertion failed', 'error_type': 'verification'}
            write_json(frozen / 'verification.json', verification)
            write_json(frozen / 'integrity.json', {'valid': True})
            write_json(frozen / 'payload.json', {'schema': 'shared', 'quantifiers': []})
            site = next(s for s in regions(SOURCE) if s['kind'] == 'loop_invariants')

            class FakeInference:
                tokenizer = Tokenizer()
                calls = 0

                def generate(self, msgs, config, seed):
                    self.calls += 1
                    text = SOURCE if mode == 'full' else 'invalid JSON'
                    if self.calls == 2:
                        text = (SOURCE.replace('i <= n,', 'i <= n, 0 <= i,') if mode == 'full' else
                                json.dumps({'site_id': site['id'], 'replacement': 'invariant i <= n, 0 <= i,'}))
                    return {'text': text, 'rendered_prompt': str(msgs), 'input_tokens': 100, 'output_tokens': 20,
                            'truncated': False, 'inference_seconds': 0.01}

            class FakeVerifier:
                calls = 0

                def verify(self, source):
                    self.calls += 1
                    write_json(source.parent / 'solver/report.json', {'queries': [], 'capture_errors': []})
                    return dict(verification, success=self.calls == 2)

            class Integrity:
                def validate(self, original, candidate):
                    return {'valid': True}

            def fake_feedback(folder, *args):
                payload = {'schema': 'second', 'quantifiers': []}
                write_json(folder / 'payload.json', payload)
                return payload

            inference, verifier = FakeInference(), FakeVerifier()
            with patch('repair_study.__main__.build_payload', side_effect=fake_feedback) as replay:
                result = run_case(root, root / 'out', 'test', mode, config, inference, verifier, Integrity())
                resumed = run_case(root, root / 'out', 'test', mode, config, inference, verifier, Integrity())
            self.assertEqual(inference.calls, 2)
            self.assertEqual(verifier.calls, 2)
            self.assertEqual(replay.call_count, 1)
            self.assertEqual(result, resumed)
            self.assertTrue(result['repairs'][0]['unchanged'])
            self.assertTrue(result['success'])

    def test_frozen_bundle_detects_file_changes(self):
        write_text(self.root / 'inputs/a/candidate.rs', SOURCE)
        from baseline.storage import digest
        write_json(self.root / 'manifest.json', {'implementation': implementation(),
                   'files': {'inputs/a/candidate.rs': digest(SOURCE.encode())}})
        validate_bundle(self.root)
        write_text(self.root / 'inputs/a/candidate.rs', SOURCE + 'changed')
        with self.assertRaises(ValueError):
            validate_bundle(self.root)

    def test_prepare_and_compare_share_frozen_first_payload(self):
        source, study = self.root / 'source', self.root / 'study'
        original = self.root / 'official.rs'
        write_text(original, SOURCE)
        write_text(source / 'task/attempt_00/candidate.rs', SOURCE)
        write_json(source / 'run.json', {'config': configuration()})
        task = {'id': 'task', 'category': 'Misc', 'original': str(original),
                'source_folder': str(source / 'task/attempt_00'), 'selection_stratum': 'other_smt'}
        verification = {'success': False, 'stdout': '', 'stderr': 'assertion failed', 'error_type': 'verification'}

        class Verifier:
            def __init__(self, *args):
                pass

            def verify(self, path):
                write_json(path.parent / 'solver/report.json', {'queries': [], 'capture_errors': []})
                return verification

        class Integrity:
            def __init__(self, *args):
                pass

            def validate(self, *args):
                return {'valid': True}

        args = SimpleNamespace(study=study, source_run=source, count=1)
        identities = {'verus': {'path': 'verus', 'sha256': 'a'}, 'z3': {'path': 'z3', 'sha256': 'b'},
                      'lynette': {'path': 'lynette', 'sha256': 'c'}, 'solver_api': {'version': '4.12.5'}}
        tokenizer_class = SimpleNamespace(from_pretrained=lambda *args, **kwargs: Tokenizer())
        with patch('repair_study.__main__.tools', return_value=identities), patch(
                'repair_study.__main__.select_candidates', return_value=[task]), patch(
                'repair_study.__main__.ObligationVerifier', Verifier), patch(
                'repair_study.__main__.IntegrityValidator', Integrity), patch.dict(
                'sys.modules', {'transformers': SimpleNamespace(AutoTokenizer=tokenizer_class)}), patch(
                'repair_study.__main__.importlib.metadata.version', return_value='4.51.3'):
            prepare(args)
        manifest = validate_bundle(study)
        self.assertEqual(len(manifest['cases']), 1)
        for mode in ('full', 'local'):
            row = {'id': 'task', 'success': False, 'repairs': []}
            write_json(study / mode / 'task/task.json', row)
            write_json(study / mode / 'task/repair_01/request.json', {'payload_sha256': 'SAME'})
        compare(SimpleNamespace(study=study))
        report = read_json(study / 'comparison.json')
        self.assertTrue(report['first_payload_check_passed'])
        self.assertEqual(report['summaries']['local']['expected_cases'], 1)
        self.assertEqual(report['summaries']['full']['completed_cases'], 1)


@unittest.skipUnless(os.environ.get('Z3_INTERNALS_PYTHONPATH'), 'Requires isolated Z3 API')
class RankedWorkerTests(unittest.TestCase):
    def test_real_ranked_callback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / 'context.json', {'operation_families': [], 'source_functions': []})
            result = execute([__import__('sys').executable, '-m', 'repair_study.worker',
                              '--query', str(ROOT / 'diagnostics/z3/sat_quantified.smt2'),
                              '--context', str(root / 'context.json'), '--output', str(root / 'out')], 20, env=api_env())
            self.assertEqual(result['returncode'], 0, result)
            report = read_json(root / 'out/report.json')
            self.assertEqual(report['result'], 'sat')
            self.assertGreater(report['instantiations_saved'], 0)
            self.assertEqual(report['callback_errors'], 0)


if __name__ == '__main__':
    unittest.main()
