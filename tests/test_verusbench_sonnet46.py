import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from verusbench_sonnet46 import __main__ as study
from verusbench_sonnet46 import feedback


class Tokenizer:
    def encode(self, text, **kwargs):
        return [1]

    def apply_chat_template(self, *args, **kwargs):
        return [1]


class Sonnet46Tests(unittest.TestCase):
    def test_exact_user_inventory_and_limits(self):
        selected = study.selected_tasks()
        requested = ('cloverbench_array_append_strong cloverbench_array_concat_strong cloverbench_array_copy_strong '
            'cloverbench_array_product_strong cloverbench_array_sum_strong cloverbench_is_prime cloverbench_two_sum '
            'diffy_brs3 diffy_brs4 diffy_brs5 diffy_condn diffy_ms1 diffy_ms2 diffy_ms3 diffy_ms5 diffy_res1o '
            'diffy_s1if diffy_s1lif diffy_s22if diffy_s32if diffy_s3if diffy_s42if '
            'mbpp_task_id_161 mbpp_task_id_240 mbpp_task_id_262 mbpp_task_id_273 mbpp_task_id_290 '
            'mbpp_task_id_424 mbpp_task_id_445 mbpp_task_id_476 mbpp_task_id_572 mbpp_task_id_616 '
            'mbpp_task_id_618 mbpp_task_id_769 mbpp_task_id_798 mbpp_task_id_94 '
            'misc_basic_nonlinear misc_binary_search misc_bubble misc_conditional_average misc_fib misc_filter '
            'misc_findmax misc_len_intersect misc_linearsearch misc_map misc_remove_all_greater misc_reverse '
            'misc_sum misc_tail_triangle').split()
        self.assertEqual([t['id'] for t in selected], requested)
        self.assertEqual(len(selected), 50)
        self.assertEqual(Counter(t['category'] for t in selected), {'CloverBench': 7, 'Diffy': 15, 'MBPP': 14, 'Misc': 14})
        cfg = study.configuration()
        self.assertEqual((cfg['model'], cfg['effort']), ('claude-sonnet-4-6', 'low'))
        self.assertEqual((cfg['internals_token_budget'], cfg['max_quantifiers'], cfg['max_instances_each']), (14336, 50, 3))

    def create_replay(self, folder, result='unknown'):
        write_json(folder / 'solver/report.json', {'queries': [
            {'id': 'q', 'file': 'q.smt2', 'result': 'unknown'},
            {'id': 'ignored', 'file': 'ignored.smt2', 'result': 'unknown'}]})
        write_text(folder / 'solver/q.smt2', '(check-sat)')
        output = folder / 'relevant-replay'
        write_json(output / 'report.json', {'status': 'completed', 'result': result})
        events = [{'quantifier_smt': f'(forall ((x Int)) (! (= x x) :qid user_candidate_{i:03}))',
                   'binding_terms_callback_order': [str(j)], 'clause_literals_smt': ['true']}
                  for i in range(55) for j in range(4)]
        write_text(output / 'instantiations.jsonl', '\n'.join(json.dumps(e) for e in events))

    def test_fifty_groups_three_instances_from_one_concordant_query(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            self.create_replay(folder)
            with patch.object(feedback, 'execute', return_value={'returncode': 0, 'timed_out': False}) as call:
                value = feedback.build_payload(folder, '', '', {'stdout': '', 'stderr': ''}, {},
                    Tokenizer(), study.configuration(), prompt_builder=lambda *a: [])
            self.assertEqual(call.call_count, 1)
            self.assertEqual(value['sampling']['selected_groups'], 50)
            self.assertEqual(value['sampling']['selected_instances'], 150)
            self.assertTrue(all(len(g['instances']) == 3 for g in value['quantifiers']))

    def test_budget_is_applied_even_when_group_cap_is_not_reached(self):
        class CharTokenizer(Tokenizer):
            def encode(self, text, **kwargs):
                return list(text)
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            self.create_replay(folder)
            token = CharTokenizer()
            with patch.object(feedback, 'execute', return_value={'returncode': 0, 'timed_out': False}):
                value = feedback.build_payload(folder, '', '', {'stdout': '', 'stderr': ''}, {},
                    token, study.configuration(), prompt_builder=lambda *a: [])
            self.assertLessEqual(len(token.encode(feedback.block(value))), 14336)
            self.assertLess(value['sampling']['selected_groups'], 50)

    def test_mismatched_replay_does_not_expose_formulas(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            self.create_replay(folder, result='sat')
            with patch.object(feedback, 'execute', return_value={'returncode': 0, 'timed_out': False}):
                value = feedback.build_payload(folder, '', '', {'stdout': '', 'stderr': ''}, {},
                    Tokenizer(), study.configuration(), prompt_builder=lambda *a: [])
            self.assertEqual(value['availability'], 'unavailable')
            self.assertEqual(value['quantifiers'], [])
            self.assertTrue(all(v is None for v in value['statistics'].values()))

    def fixture(self, root):
        folder = root / 'inputs/case'
        write_text(folder / 'original.rs', 'fn main() {}')
        checked = {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''}
        write_json(folder / 'verification.json', checked)
        write_json(folder / 'integrity.json', {'valid': True})
        return checked

    def test_one_shared_generation_and_identical_fork_inputs(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checked = self.fixture(root)
            calls = []
            def generate(prompt, cfg, folder):
                calls.append(prompt)
                return {'text': f'fn main() {{ let x = {len(calls)}; }}'}
            inference = SimpleNamespace(tokenizer=Tokenizer(), generate_at=generate)
            results = iter([checked, {**checked, 'success': True, 'error_type': None},
                            {**checked, 'success': True, 'error_type': None}])
            verifier = SimpleNamespace(verify=lambda *a: next(results))
            guard = SimpleNamespace(validate=lambda *a: {'valid': True})
            def build(folder, *a, **kw):
                value = {'availability': 'available', 'quantifiers': []}
                write_json(folder / 'payload.json', value)
                return value
            with patch.object(study, 'build_payload', side_effect=build):
                for _ in range(2):
                    study.run_task(root, {'id': 'case'}, study.configuration(), inference, verifier, guard, study.vb.ARMS)
            self.assertEqual(len(calls), 3)
            self.assertNotIn('<solver_internals>', calls[0][1]['content'])
            a = read_json(root / 'with_internals/case/attempt_02/request.json')
            b = read_json(root / 'without_internals/case/attempt_02/request.json')
            for key in ('common_messages_sha256', 'candidate_sha256', 'shared_start_sha256', 'config'):
                self.assertEqual(a[key], b[key])
            self.assertTrue(a['internals_exposed'])
            self.assertFalse(b['internals_exposed'])

    def test_parser_errors_consume_attempt_but_unknown_panics_stop(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checked = self.fixture(root)
            inference = SimpleNamespace(tokenizer=Tokenizer(), generate_at=lambda *a: {'text': 'Need invariants: fn main() {}'})
            parse_error = {'valid': False, 'status': 'checker_error', 'returncode': 1,
                           'timed_out': False, 'stderr': 'error: Syn unable to parse file'}
            guard = SimpleNamespace(validate=lambda *a: parse_error)
            verifier = SimpleNamespace(verify=lambda *a: {**checked, 'error_type': 'compilation'})
            original = root / 'inputs/case/original.rs'
            result = study.attempt(root / 'attempt_01', 1, original, 'fn main() {}', checked, {}, None, [],
                                   study.configuration(), inference, verifier, guard)
            self.assertFalse(result['success'])
            self.assertEqual(read_json(root / 'attempt_01/integrity.json')['status'], 'unparseable')
            self.assertFalse(study.known_input_parse_error({**parse_error, 'stderr': 'arbitrary panic'}))
            self.assertFalse(study.known_input_parse_error({**parse_error, 'timed_out': True}))

    def test_verus_success_without_integrity_is_never_accepted(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checked = self.fixture(root)
            inference = SimpleNamespace(tokenizer=Tokenizer(), generate_at=lambda *a: {'text': 'fn main() { let x = 1; }'})
            guard = SimpleNamespace(validate=lambda *a: {'valid': False, 'status': 'invalid'})
            verifier = SimpleNamespace(verify=lambda *a: {**checked, 'success': True, 'error_type': None})
            result = study.attempt(root / 'attempt_01', 1, root / 'inputs/case/original.rs',
                'fn main() {}', checked, {}, None, [], study.configuration(), inference, verifier, guard)
            self.assertFalse(result['success'])


if __name__ == '__main__':
    unittest.main()
