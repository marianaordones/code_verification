import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace

from diagnostics.z3_probe import commands, snapshots, cli_replay, run, sample_event
from baseline.storage import write_text, read_json


class Z3ProbeTests(unittest.TestCase):
    def test_assumptions_do_not_starve_inference_samples(self):
        saved = {}
        self.assertEqual(sum(sample_event('assumption', saved, 2) for _ in range(10)), 2)
        self.assertTrue(sample_event('euf', saved, 2))
        self.assertTrue(sample_event('bound', saved, 2))
        self.assertFalse(sample_event('farkas', saved, 2))
        self.assertTrue(sample_event('inst', saved, 2))
        self.assertEqual(saved['assumptions'], 2)
        self.assertEqual(saved['other_inferences'], 2)

    def test_sat_value_queries_are_saved_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            write_text(folder/'prefix.smt2', '(declare-const x Int)\n(assert (= x 0))')
            query = {'prefix_file':str(folder/'prefix.smt2'), 'check_command':'(check-sat)',
                     'inspect_terms':['x', '(> x 0)']}
            result = {'stdout':'sat\nPROBE_REASON\n(:reason-unknown "")\nPROBE_MODEL\n((define-fun x () Int 0))\nPROBE_STATISTICS\n(:rlimit-count 10)\nPROBE_VALUES\n((x 0) ((> x 0) false))\n',
                      'stderr':'', 'returncode':0, 'timed_out':False}
            with patch('diagnostics.z3_probe.execute', return_value=result):
                report = cli_replay('fake', query, folder, 100)
            self.assertTrue(report['model_is_confirmed_sat'])
            self.assertTrue(report['values_available'])
            self.assertIn('(x 0)', (folder/'cli.values.txt').read_text())

    def test_compile_failure_is_reported_as_no_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, binary = root / 'input.rs', root / 'z3'
            source.write_text('INVALID SOURCE')
            binary.write_text('TEST BINARY')
            args = Namespace(source=str(source), output=str(root/'out'), verus_timeout=1,
                             timeout_ms=100, max_queries=2, max_events=1)
            result = {'returncode':1, 'timed_out':False, 'seconds':0,
                      'stdout':'', 'stderr':'error: expected `!`'}
            with patch('diagnostics.z3_probe.sys.platform', 'linux'), \
                    patch.dict(os.environ, {'Z3_BIN':str(binary), 'VERUS_BIN':str(binary),
                                           'Z3_PROBE_WORK':str(root/'work')}), \
                    patch('diagnostics.z3_probe.execute', return_value=result):
                self.assertEqual(run(args), 1)
            report = read_json(root/'out/report.json')
            self.assertEqual(report['status'], 'no_solver_queries')
            self.assertEqual(report['selected_queries'], [])
            self.assertIn('Syntax/type errors', (root/'out/report.md').read_text())

    def test_split_preserves_strings_comments_and_scope(self):
        text = '; (ignored)\n(set-info :source "text ) ; ""quoted""")\n(declare-const |a ( b| Int)\n(push 1)\n(assert (> |a ( b| 0))\n(check-sat)\n(get-model)\n(echo "<<DONE>>")\n(pop 1)\n(check-sat)'
        items = list(commands(text))
        self.assertEqual(len(items), 9)
        queries = list(snapshots(text))
        self.assertEqual(len(queries), 2)
        self.assertIn('(pop 1)', queries[1][0])
        self.assertNotIn('(get-model)', queries[1][0])
        self.assertNotIn('(check-sat)', queries[1][0])
        with self.assertRaises(ValueError):
            list(commands('(assert (and true'))

    def test_cli_marks_unavailable_model_without_inventing_one(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            write_text(folder/'prefix.smt2', '(declare-const x Int)\n(assert (> x 0))')
            query = {'prefix_file':str(folder/'prefix.smt2'), 'check_command':'(check-sat)'}
            result = {'stdout':'unknown\nPROBE_REASON\n(:reason-unknown "timeout")\nPROBE_MODEL\n(error "model is not available")\nPROBE_STATISTICS\n(:rlimit-count 10)\n', 'stderr':'', 'returncode':1, 'timed_out':False}
            with patch('diagnostics.z3_probe.execute', return_value=result):
                report = cli_replay('fake', query, folder, 100)
            self.assertEqual(report['result'], 'unknown')
            self.assertFalse(report['model_available'])
            self.assertTrue(report['statistics_available'])

    def test_proxy_passes_through_and_captures_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'Z3_PROBE_CAPTURE':directory, 'Z3_PROBE_REAL':sys.executable}
            child = 'import sys; text=sys.stdin.read(); print("sat"); print("diagnostic",file=sys.stderr)'
            result = subprocess.run([sys.executable, '-m', 'diagnostics.z3_probe', 'proxy', '-c', child],
                                    input='(check-sat)\n', text=True, capture_output=True, env=env, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'sat\n')
            self.assertIn('diagnostic', result.stderr)
            captured = list(Path(directory).glob('*.stdin.smt2'))
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0].read_text(), '(check-sat)\n')
