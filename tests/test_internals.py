import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baseline.__main__ import validate_config
from baseline.internals import internal_feedback, pack, select_events
from baseline.prompts import ROOT, build_messages
from baseline.runner import run_task
from baseline.storage import read_json, write_json, write_text
from diagnostics.z3_internals import api_identity, replay
from test_pipeline import SOURCE, FakeInference, FakeVerifier, FakeIntegrity


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(text[::4])

    def apply_chat_template(self, messages, **kwargs):
        return self.encode(''.join(m['content'] for m in messages))


def event(label='P', term='0'):
    return {'quantifier_smt': f'(forall ((j Int)) ({label} j))',
            'binding_terms_callback_order': [term],
            'clause_literals_smt': [f'(not (forall ((j Int)) ({label} j)))', f'({label} {term})']}


class InternalsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = read_json(ROOT / 'configs/qwen25coder14b-c-internals-150.json')

    def test_protocol_and_prompt_extension_preserve_v4_actions(self):
        validate_config(self.config, 'full')
        before = build_messages(SOURCE, 'diagnostic', 'v4', original=SOURCE)
        after = build_messages(SOURCE, 'diagnostic', 'v4-internals', original=SOURCE)
        self.assertTrue(after[0]['content'].startswith(before[0]['content']))
        self.assertEqual(before[1], after[1])
        self.assertIn('clause_literals_smt is a disjunction', after[0]['content'])
        self.assertNotIn('rope_scaling', self.config)
        self.assertEqual(self.config['max_repairs'], 2)
        self.assertEqual(self.config['internals_token_budget'], 12288)
        invalid = dict(self.config, replay_timeout_ms=100)
        with self.assertRaises(ValueError):
            validate_config(invalid, 'full')

    def test_missing_mismatch_and_missing_statistics_are_explicit(self):
        report = {'queries': [], 'capture_errors': []}
        payload = pack(report, {}, None)
        self.assertEqual(payload['unavailability_reason'], 'no_captured_sat_or_unknown_query')
        self.assertIsNone(payload['statistics']['conflicts'])
        selected = {'id': 'query-0000', 'result': 'unknown'}
        replay_report = {'status': 'completed', 'result': 'sat', 'statistics': {'conflicts': 9}}
        payload = pack(report, replay_report, selected)
        self.assertEqual(payload['unavailability_reason'], 'replay_result_mismatch')
        self.assertIsNone(payload['statistics']['conflicts'])
        self.assertEqual(payload['quantifiers'], [])

    def test_sampling_groups_deduplicates_and_omits_whole_formulas(self):
        payload = pack({'queries': [], 'capture_errors': []}, {}, None)
        events = [event('huge' * 1000)] + [event(f'P{n}', str(t)) for n in range(10) for t in range(4)]
        payload = select_events(payload, events, lambda p: len(json.dumps(p)) < 7000)
        self.assertLessEqual(len(payload['quantifiers']), 10)
        self.assertTrue(all(len(g['instances']) <= 3 for g in payload['quantifiers']))
        self.assertNotIn('huge', json.dumps(payload))
        self.assertNotIn('truncated', json.dumps(payload))
        self.assertIn('(forall', json.dumps(payload))

    def test_expanded_sample_accepts_exactly_ten_groups_and_three_instances(self):
        payload = pack({'queries': [], 'capture_errors': []}, {}, None)
        events = [event(f'P{n}', str(t)) for n in range(12) for t in range(5)]
        payload = select_events(payload, events, lambda _: True)
        self.assertEqual(len(payload['quantifiers']), 10)
        self.assertTrue(all(len(g['instances']) == 3 for g in payload['quantifiers']))
        self.assertEqual(payload['sampling']['instances_in_prompt'], 30)

    def test_twelve_k_feedback_still_respects_total_context_and_output_reserve(self):
        write_json(self.root / 'solver/report.json', {'queries': [
            {'id': 'query-0000', 'result': 'unknown', 'file': 'query-0000.smt2'}], 'capture_errors': []})
        write_text(self.root / 'solver/query-0000.smt2', 'not sent')

        def fake_replay(query, output, timeout_ms):
            write_text(output / 'instantiations.jsonl', json.dumps(event('P' * 6000)) + '\n')
            return {'status': 'completed', 'result': 'unknown', 'timeout_ms': timeout_ms,
                    'statistics': {'quant instantiations': 1}}

        tokenizer = Tokenizer()
        with patch('baseline.internals.replay', side_effect=fake_replay):
            internal_feedback(self.root, SOURCE, 'ordinary', SOURCE,
                              SimpleNamespace(tokenizer=tokenizer), self.config)
            exposure = read_json(self.root / 'internals/exposure.json')
            self.assertTrue(exposure['has_instances'])
            self.assertGreater(exposure['extra_tokens'], 4096)
            self.assertLessEqual(exposure['extra_tokens'], 12288)
            current = 'x' * 90000
            feedback = internal_feedback(self.root, current, 'ordinary', SOURCE,
                                         SimpleNamespace(tokenizer=tokenizer), self.config)
        self.assertFalse(read_json(self.root / 'internals/exposure.json')['has_instances'])
        messages = build_messages(current, feedback, self.config['prompt_version'], original=SOURCE)
        count = len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
        self.assertLessEqual(count + 4096, 32768)

    def test_packaging_omits_query_and_does_not_replay_when_absent(self):
        write_json(self.root / 'solver/report.json', {'queries': [], 'capture_errors': []})
        with patch('baseline.internals.replay') as worker:
            feedback = internal_feedback(self.root, SOURCE, 'ordinary', SOURCE,
                                         SimpleNamespace(tokenizer=Tokenizer()), self.config)
        worker.assert_not_called()
        self.assertIn('<solver_internals>', feedback)
        self.assertNotIn('<solver_obligations>', feedback)
        self.assertNotIn('declare-fun', feedback)

    def test_real_feedback_contains_events_not_query_and_resume_cost_is_once(self):
        root = self.root
        class CapturingVerifier(FakeVerifier):
            def verify(self, source):
                write_json(source.parent / 'solver/report.json', {'queries': [
                    {'id': 'query-0000', 'result': 'unknown', 'file': 'query-0000.smt2'}], 'capture_errors': []})
                write_text(source.parent / 'solver/query-0000.smt2', 'SECRET COMPLETE QUERY')
                return super().verify(source)

        def fake_replay(query, output, timeout_ms):
            self.assertIn('SECRET', query.read_text())
            write_text(output / 'instantiations.jsonl', json.dumps(event()) + '\n')
            return {'status': 'completed', 'result': 'unknown', 'timeout_ms': timeout_ms,
                    'reason_unknown': 'incomplete quantifiers', 'statistics': {'quant instantiations': 1}}

        write_text(root / 'source.rs', SOURCE)
        task = {'id': 'test', 'category': 'Misc', 'file': str(root / 'source.rs')}
        inference = FakeInference()
        inference.tokenizer = Tokenizer()
        with patch('baseline.internals.replay', side_effect=fake_replay) as worker:
            result = run_task(task, self.config, root / 'out', inference, CapturingVerifier(), FakeIntegrity())
            first_calls = len(inference.calls)
            resumed = run_task(task, self.config, root / 'out', inference, CapturingVerifier(), FakeIntegrity())
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(first_calls, len(inference.calls))
        self.assertEqual(result['attempts'], resumed['attempts'])
        user_prompt = inference.calls[1][1]['content']
        self.assertNotIn('SECRET COMPLETE QUERY', user_prompt)
        self.assertIn('binding_terms_callback_order', user_prompt)
        self.assertIn('incomplete quantifiers', user_prompt)
        self.assertGreaterEqual(result['attempts'][0]['solver_feedback_seconds'], 0)


@unittest.skipUnless(os.environ.get('Z3_INTERNALS_PYTHONPATH'), 'Requires isolated Z3 API (cluster)')
class RealInternalsTests(unittest.TestCase):
    def test_isolated_api_replay_reports_instantiations(self):
        self.assertEqual(api_identity()['version'], '4.12.5')
        with tempfile.TemporaryDirectory() as temporary:
            report = replay(ROOT / 'diagnostics/z3/sat_quantified.smt2', Path(temporary) / 'api', 5000)
            self.assertEqual(report.get('result'), 'sat', report)
            self.assertGreater(report['instantiations_saved'], 0)
            self.assertEqual(report['callback_errors'], 0)


if __name__ == '__main__':
    unittest.main()
