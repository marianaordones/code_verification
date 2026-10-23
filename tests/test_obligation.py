import tempfile
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from baseline.__main__ import validate_config
from baseline.obligation import ObligationVerifier, collect_queries, solver_feedback
from baseline.prompts import ROOT
from baseline.runner import run_task
from baseline.storage import read_json, write_text
from test_pipeline import SOURCE, FakeInference, FakeVerifier, FakeIntegrity


class CharacterTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return list(''.join(m['content'] for m in messages))


class ObligationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = self.root / 'capture'
        self.capture.mkdir()

    def capture_query(self, text, output):
        write_text(self.capture / 'solver-1.stdin.smt2', text)
        write_text(self.capture / 'solver-1.stdout.txt', output)

    def test_original_incremental_checks_and_timeout(self):
        self.capture_query('(declare-const x Int)\n(push 1)\n(assert (> x 0))\n'
                           '(check-sat)\n(pop 1)\n(assert (< x 0))\n(check-sat)', 'sat\n')
        report = collect_queries(self.capture, self.root / 'solver', timed_out=True)
        self.assertEqual([q['result'] for q in report['queries']], ['sat', 'timeout'])
        self.assertEqual(report['capture_errors'], [])
        query = (self.root / 'solver/query-0001.smt2').read_text()
        self.assertIn('(pop 1)', query)
        self.assertIn('(assert (< x 0))', query)

    def test_misaligned_capture_is_not_guessed(self):
        self.capture_query('(check-sat)\n(check-sat)', 'unknown\n')
        report = collect_queries(self.capture, self.root / 'solver')
        self.assertEqual(report['queries'], [])
        self.assertTrue(report['capture_errors'])

    def test_complete_failed_query_and_oversize_omission(self):
        self.capture_query('(declare-const x Int)\n(assert (> x 0))\n(check-sat)', 'unknown\n')
        collect_queries(self.capture, self.root / 'solver')
        config = read_json(ROOT / 'configs/qwen25coder14b-b-150.json')
        engine = SimpleNamespace(tokenizer=CharacterTokenizer())
        feedback = solver_feedback(self.root, SOURCE, 'ordinary diagnostic', SOURCE, engine, config)
        self.assertIn('(assert (> x 0))', feedback)
        self.assertIn('result=unknown', feedback)
        self.assertNotIn('reason_unknown', feedback)
        write_text(self.root / 'solver/query-0000.smt2', '(assert ' + 'x' * 40000 + ')')
        feedback = solver_feedback(self.root, SOURCE, 'ordinary diagnostic', SOURCE, engine, config)
        self.assertIn('No complete query fits', feedback)
        self.assertFalse(read_json(self.root / 'solver/exposure.json')['complete_query_exposed'])
        self.assertNotIn('x' * 100, feedback)

    def test_v4_configuration_and_feedback_resume(self):
        config = read_json(ROOT / 'configs/qwen25coder14b-b-150.json')
        validate_config(config, 'full')
        previous = read_json(ROOT / 'configs/qwen25coder14b-v4-150.json')
        self.assertEqual({k: v for k, v in config.items() if k not in ('experiment', 'solver_feedback')},
                         {k: v for k, v in previous.items() if k != 'experiment'})
        source = self.root / 'original.rs'
        write_text(source, SOURCE)
        task = {'id': 'test', 'category': 'Misc', 'file': str(source)}
        capture = self.capture
        class CapturingVerifier(FakeVerifier):
            def verify(self, source):
                collect_queries(capture, source.parent / 'solver')
                return super().verify(source)
        self.capture_query('(declare-const x Int)\n(assert (> x 0))\n(check-sat)', 'unknown\n')
        inference = FakeInference()
        inference.tokenizer = CharacterTokenizer()
        result = run_task(task, config, self.root / 'out', inference, CapturingVerifier(), FakeIntegrity())
        self.assertEqual(len(inference.calls), 2)
        self.assertNotIn('<solver_obligations>', inference.calls[0][1]['content'])
        self.assertIn('<solver_obligations>', inference.calls[1][1]['content'])
        self.assertIn('(declare-const x Int)', inference.calls[1][1]['content'])
        resumed = FakeInference()
        resumed.tokenizer = CharacterTokenizer()
        again = run_task(task, config, self.root / 'out', resumed, CapturingVerifier(), FakeIntegrity())
        self.assertEqual(again['attempts'], result['attempts'])
        self.assertEqual(resumed.calls, [])


@unittest.skipUnless(os.environ.get('VERUS_BIN') and os.environ.get('Z3_BIN'),
                     'Requires real VERUS_BIN and Z3_BIN (cluster)')
class RealObligationTests(unittest.TestCase):
    def test_original_capture_before_model_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'candidate.rs'
            write_text(source, 'use vstd::prelude::*; fn main() {} verus! { '
                       'proof fn f(x: int) requires x >= 0, ensures x > 0, {} }')
            result = ObligationVerifier(os.environ['VERUS_BIN'], os.environ['Z3_BIN']).verify(source)
            self.assertFalse(result['success'])
            report = read_json(source.parent / 'solver/report.json')
            self.assertEqual(report['capture_errors'], [])
            self.assertTrue(any(q['result'] in ('sat', 'unknown') for q in report['queries']), report)


if __name__ == '__main__':
    unittest.main()
