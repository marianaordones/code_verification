import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from missing_opus48 import __main__ as study
from solver_needs_study import actions, feedback


class MissingOpus48Tests(unittest.TestCase):
    def test_model_and_limits_and_exact_user_list(self):
        cfg = study.configuration()
        self.assertEqual((cfg['model'], cfg['effort']), ('claude-opus-4-8', 'low'))
        self.assertEqual((cfg['max_queries'], cfg['max_quantifiers'], cfg['max_instances_each']), (1, 50, 3))
        supplied = read_json(study.USER100)['ids']
        self.assertEqual(supplied, read_json(study.ROOT / 'configs/solver-needs-tasks100.json')['ids'])
        self.assertEqual(read_json(study.SELECTION)['ids'], supplied[:20])
        self.assertEqual(len(set(supplied)), 100)

    def test_packet_limits_fifty_groups_to_three_of_four_available_instances(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            write_json(folder / 'solver/report.json', {'queries': [
                {'id': 'q', 'file': 'q.smt2', 'result': 'unknown'},
                {'id': 'ignored', 'file': 'ignored.smt2', 'result': 'unknown'}], 'capture_errors': []})
            write_text(folder / 'solver/q.smt2', '(check-sat)')
            output = folder / 'internals/q'
            write_json(output / 'report.json', {'status': 'completed', 'result': 'unknown'})
            events = [{'quantifier_smt': f'(forall ((x Int)) (! (= x x) :qid user_candidate_{i:03}))',
                       'binding_terms_callback_order': [str(j)], 'clause_literals_smt': ['true']}
                      for i in range(55) for j in range(4)]
            write_text(output / 'instantiations.jsonl', '\n'.join(json.dumps(e) for e in events))
            with patch.object(feedback, 'execute', return_value={'returncode': 0, 'timed_out': False}) as replay, \
                 patch.object(feedback, 'fits', return_value=True):
                value = study.build_feedback(folder, '', {'stdout': '', 'stderr': ''}, actions.EMPTY,
                                             [], None, study.configuration())
            self.assertEqual(replay.call_count, 1)
            groups = value['internals']['queries'][0]['quantifiers']
            self.assertEqual(len(groups), 50)
            self.assertTrue(all(len(g['instances']) == 3 for g in groups))

    def fixture(self, root):
        task = {'prefix': 'verus! { proof fn f() {', 'suffix': '} }', 'proof_context': True}
        checked = {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''}
        initial = root / 'inputs/case'
        write_json(initial / 'task.json', task)
        write_text(initial / 'candidate.rs', actions.render(task, actions.EMPTY))
        write_json(initial / 'verification.json', checked)
        return checked

    def test_shared_first_action_is_generated_once_and_failed_state_is_identical(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checked = self.fixture(root)
            calls = []
            checks = iter([checked, {**checked, 'success': True, 'error_type': None},
                           {**checked, 'success': True, 'error_type': None}])
            def generate(prompt, cfg, folder):
                calls.append(folder)
                return {'text': json.dumps({**actions.EMPTY, 'statements': f'assert({len(calls)} == {len(calls)});'})}
            inference = SimpleNamespace(tokenizer=SimpleNamespace(encode=lambda *a, **kw: [1]), generate_at=generate)
            check = SimpleNamespace(verify=lambda *a, **kw: next(checks))
            pack = {'context': {}, 'internals': {'queries': [{'quantifiers': []}]}, 'availability': 'available'}
            def build(folder, *a):
                write_json(folder / 'feedback.json', pack)
                return pack
            fake_laws = (None, SimpleNamespace(LAWS={}))
            with patch.object(actions, 'upstream', return_value=fake_laws), \
                 patch.object(feedback, 'upstream', return_value=fake_laws), \
                 patch.object(feedback, 'fits', return_value=True), \
                 patch.object(feedback, 'control_feedback', return_value={'context': {}, 'internals': None}), \
                 patch.object(study, 'build_feedback', side_effect=build):
                for _ in range(2):
                    study.run_case(root, {'id': 'case'}, study.configuration(), inference, check, study.ARMS)
            self.assertEqual(len(calls), 3)
            first = read_json(root / 'shared/case/attempt_01/request.json')
            self.assertFalse(first['internals_exposed'])
            a = read_json(root / 'with_internals/case/attempt_02/request.json')
            b = read_json(root / 'without_internals/case/attempt_02/request.json')
            for key in ('candidate_sha256', 'common_messages_sha256', 'shared_start_sha256', 'config'):
                self.assertEqual(a[key], b[key])
            self.assertTrue(a['internals_exposed'])
            self.assertFalse(b['internals_exposed'])
            self.assertEqual(read_json(root / 'shared/case/attempt_01/action.json'),
                             read_json(root / 'shared/case/attempt_01/result.json')['action'])

    def test_invalid_json_consumes_proposal_and_preserves_previous_settings(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checked = self.fixture(root)
            task = read_json(root / 'inputs/case/task.json')
            code = (root / 'inputs/case/candidate.rs').read_text()
            previous = {**actions.EMPTY, 'nla': True}
            inference = SimpleNamespace(tokenizer=None, generate_at=lambda *a: {'text': 'not json'})
            seen_nla = []
            check = SimpleNamespace(verify=lambda p, nla: seen_nla.append(nla) or checked)
            with patch.object(feedback, 'fits', return_value=True), \
                 patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
                result = study.attempt(root / 'attempt_02', 2, task, code, checked, previous, {},
                                       None, [], study.configuration(), inference, check)
            self.assertFalse(result['success'])
            self.assertTrue(result['edit_error'])
            self.assertEqual(seen_nla, [True])
            self.assertEqual(read_json(root / 'attempt_02/action.json'), previous)

    def test_first_success_never_builds_internals_or_calls_two_arms(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checked = self.fixture(root)
            calls = []
            def generate(*args):
                calls.append(1)
                return {'text': json.dumps({**actions.EMPTY, 'statements': 'assert(true);'})}
            inference = SimpleNamespace(tokenizer=None, generate_at=generate)
            check = SimpleNamespace(verify=lambda *a, **kw: {**checked, 'success': True, 'error_type': None})
            fake_laws = (None, SimpleNamespace(LAWS={}))
            with patch.object(actions, 'upstream', return_value=fake_laws), \
                 patch.object(feedback, 'upstream', return_value=fake_laws), \
                 patch.object(feedback, 'fits', return_value=True), \
                 patch.object(study, 'build_feedback', side_effect=AssertionError('unnecessary replay')):
                for _ in range(2):
                    study.run_case(root, {'id': 'case'}, study.configuration(), inference, check, study.ARMS)
            self.assertEqual(len(calls), 1)
            self.assertFalse((root / 'with_internals').exists())

    def test_conditional_denominator_does_not_credit_initial_successes_to_arms(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            write_json(root / 'shared/easy/task.json', {'initially_verified': False, 'success': True})
            write_json(root / 'shared/hard/task.json', {'initially_verified': False, 'success': False})
            for arm in study.ARMS:
                write_json(root / arm / 'hard/task.json', {'success': True, 'attempts': [
                    {'attempt': 2, 'success': True, 'internals_exposed': arm == 'with_internals'}]})
            with patch.object(study, 'validate', return_value={'cases': [{'id': 'easy'}, {'id': 'hard'}]}):
                report = study.compare(root)
            self.assertEqual(report['shared_first_successes'], 1)
            self.assertEqual(report['summaries']['with_internals']['repair_denominator_so_far'], 1)
            self.assertEqual(report['summaries']['without_internals']['repaired_at_2'], 1)


if __name__ == '__main__':
    unittest.main()
