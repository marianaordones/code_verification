from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from solver_needs_study import __main__ as study
from solver_needs_study import actions, feedback, shared_events


class SampleVariantsTests(unittest.TestCase):
    def test_variants_have_same_generation_and_differ_only_in_sample_shape(self):
        a = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals32k-80x3.json')
        b = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals32k-50x5.json')
        self.assertEqual({k for k in a if a[k] != b[k]}, {'max_quantifiers', 'max_instances_each', 'experiment'})
        self.assertEqual((a['max_quantifiers'], a['max_instances_each']), (80, 3))
        self.assertEqual((b['max_quantifiers'], b['max_instances_each']), (50, 5))
        for config in (a, b):
            self.assertEqual(config['max_attempts'], 3)
            self.assertEqual(config['internals_token_budget'], 32768)
            self.assertEqual(config['max_model_len'], 49152)
            self.assertEqual(config['max_tokens'], 4096)
            self.assertEqual(config['replay_max_instances'], 5)
            self.assertTrue(config['shared_initial_events_required'])

    def test_packing_honors_both_shapes_and_never_replays_second_saved_query(self):
        for limit, depth in ((80, 3), (50, 5)):
            with self.subTest(groups=limit), tempfile.TemporaryDirectory() as work:
                folder = Path(work)
                config = study.configuration(study.ROOT / f'configs/solver-needs-qwen14b-internals32k-{limit}x{depth}.json')
                queries = [{'id': q, 'file': q + '.smt2', 'result': 'unknown'} for q in ('q1', 'q2')]
                write_json(folder / 'solver/report.json', {'queries': queries, 'capture_errors': []})
                for query in queries:
                    q = query['id']
                    write_text(folder / 'solver' / query['file'], '(check-sat)')
                    write_json(folder / f'internals/{q}/process.json', {'returncode': 0, 'timed_out': False})
                    write_json(folder / f'internals/{q}/report.json', {'status': 'completed', 'result': 'unknown'})
                    events = [{'quantifier_smt': f'(forall ((x Int)) (! (= x x) :qid user_candidate_{i}))',
                               'binding_terms_callback_order': [str(j)], 'clause_literals_smt': ['true']}
                              for i in range(45) for j in range(6)]
                    write_text(folder / f'internals/{q}/instantiations.jsonl', '\n'.join(json.dumps(e) for e in events))
                with patch.object(feedback, 'execute', side_effect=AssertionError('Saved data must not replay')), \
                     patch.object(feedback, 'fits', return_value=True):
                    result = feedback.internals(folder, '', {'stdout': '', 'stderr': ''}, actions.EMPTY,
                                                [], None, config, replay=False)
                groups = [g for q in result['internals']['queries'] for g in q['quantifiers']]
                self.assertEqual(len(groups), limit)
                self.assertTrue(all(len(g['instances']) == depth for g in groups))

    def test_new_replays_request_five_saved_instances(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            write_json(folder / 'solver/report.json', {'queries': [{'id': 'q', 'file': 'q.smt2', 'result': 'unknown'}],
                                                      'capture_errors': []})
            write_text(folder / 'solver/q.smt2', '(check-sat)')
            config = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals32k-50x5.json')

            def worker(command, *args, **kwargs):
                self.assertEqual(command[-2:], ['--max-instances-per-group', '5'])
                output = Path(command[command.index('--output') + 1])
                write_json(output / 'report.json', {'status': 'completed', 'result': 'unknown'})
                return {'returncode': 0, 'timed_out': False}

            with patch.object(feedback, 'execute', side_effect=worker), patch.object(feedback, 'fits', return_value=True):
                feedback.internals(folder, '', {'stdout': '', 'stderr': ''}, actions.EMPTY, [], None, config)

    def test_pool_collected_once_and_reused_by_both_shapes(self):
        with tempfile.TemporaryDirectory() as work:
            origin, pool = Path(work) / 'source', Path(work) / 'pool'
            for name, value in [('task.json', {}), ('verification.json', {'success': False}),
                                ('solver/report.json', {'queries': [], 'capture_errors': []})]:
                write_json(origin / name, value)
            write_text(origin / 'candidate.rs', 'same source')
            a = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals32k-80x3.json')
            b = study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-internals32k-50x5.json')
            a['system_prompt_text'] = b['system_prompt_text'] = 'same prompt'

            def collect(folder, *args, **kwargs):
                self.assertTrue(kwargs['replay'])
                config = args[5]
                self.assertEqual(config['replay_max_instances'], 5)
                write_json(folder / 'feedback.json', {'internals': None})

            def lock(folder):
                folder.mkdir(parents=True, exist_ok=True)
                return nullcontext()

            with patch.object(shared_events, 'run_lock', side_effect=lock), \
                 patch.object(shared_events, 'internals', side_effect=collect) as collector:
                self.assertEqual(shared_events.ensure_pool(pool, origin, a, {}, None), pool)
                self.assertEqual(shared_events.ensure_pool(pool, origin, b, {}, None), pool)
                self.assertEqual(collector.call_count, 1)
                write_text(pool / 'candidate.rs', 'modified')
                with self.assertRaisesRegex(ValueError, 'evidence changed'):
                    shared_events.ensure_pool(pool, origin, a, {}, None)


if __name__ == '__main__':
    unittest.main()
