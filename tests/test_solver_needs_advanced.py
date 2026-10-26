import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from solver_needs_study import actions, feedback
from solver_needs_study import __main__ as study
from solver_needs_study.advanced import merge_queries, pack_for_prompt, capture_query


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(text)
    def apply_chat_template(self, messages, **kwargs):
        return list(json.dumps(messages))


def sample():
    match = {'id': 'm1', 'qid': 'user_candidate_q', 'line': 1,
        'inventory_match': 'unique_qid', 'input_formula': 'FORMULA', 'input_formula_sha256': 'hash',
        'trigger': {'trace_id': '#1', 'term': 'P', 'resolved': True}, 'bindings': [],
        'top_level_matched_terms': [], 'instance_count': 1, 'equalities_used': []}
    return {'status': 'parsed', 'matches': [match, {**match, 'id': 'm2', 'line': 2}],
        'chains': [{'events': ['m1', 'm2'], 'edges': [{'from': 'm1', 'to': 'm2', 'term': {'trace_id': '#1'}}]}]}


class AdvancedStudyTests(unittest.TestCase):
    def config(self):
        return study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-advanced64k.json')

    def test_frozen_configuration(self):
        c = self.config()
        self.assertEqual((c['max_model_len'], c['internals_token_budget'], c['complement_token_budget'],
                          c['advanced_token_budget'], c['max_attempts']), (65536, 24576, 12288, 14336, 3))
        self.assertEqual(c['rope_scaling']['factor'], 2)
        self.assertEqual(c['gpu_memory_utilization'], 0.95)

    def test_query_namespaces_and_global_budget(self):
        records = [(sample(), [{'rule': 'smt', 'clause_literals_smt': ['P']}], {'id': q}) for q in ('q1', 'q2', 'q3')]
        data, clauses, queries = merge_queries(records)
        self.assertEqual(len({m['id'] for m in data['matches']}), 6)
        self.assertEqual(len(clauses), 3)
        for chain in data['chains']:
            self.assertTrue(all(key.startswith(chain['query_id'] + ':') for key in chain['events']))
        with patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            value = {'context': {}, 'internals': {'queries': []}, 'complement': {'queries': []}}
            payload, selection = pack_for_prompt(data, clauses, queries, '', {'stdout': '', 'stderr': ''},
                actions.EMPTY, [], value, Tokenizer(), self.config())
        self.assertIsNotNone(payload)
        self.assertEqual(len(payload['queries']), 3)
        self.assertLessEqual(selection['actual_tokens'], 14336)
        self.assertTrue(all('query_id' in m for m in payload['matching']))
        self.assertEqual(len(payload['non_inst_clauses']), 3)  # no cross-query clause deduplication

    def test_context_trim_changes_only_advanced_block(self):
        data, clauses, queries = merge_queries([(sample(), [{'rule': 'smt', 'clause_literals_smt': ['P']}], {'id': 'q'})])
        value = {'context': {}, 'internals': {'queries': []}, 'complement': {'queries': []}}
        original = copy.deepcopy(value)
        c = self.config()
        with patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
            common = feedback.messages('', {'stdout': '', 'stderr': ''}, actions.EMPTY, {}, value['internals'], [],
                                       config=c, complement=value['complement'])
            used = len(Tokenizer().apply_chat_template(common))
            c['max_model_len'] = used + c['max_tokens'] + 2000
            payload, selection = pack_for_prompt(data, clauses, queries, '', {'stdout': '', 'stderr': ''},
                                                actions.EMPTY, [], value, Tokenizer(), c)
            if payload:
                self.assertLessEqual(selection['actual_prompt_tokens'] + c['max_tokens'], c['max_model_len'])
                self.assertLessEqual(selection['token_budget'], 1872)
            c['max_model_len'] = used + c['max_tokens'] + 60
            payload, selection = pack_for_prompt(data, clauses, queries, '', {'stdout': '', 'stderr': ''},
                                                actions.EMPTY, [], value, Tokenizer(), c)
            self.assertIsNone(payload)
        self.assertEqual(value, original)

    def test_capture_error_is_explicit_and_cached(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            write_text(root / 'solver/q.smt2', '(check-sat)')
            write_json(root / 'source-context.json', {})
            failed = {'returncode': 1, 'timed_out': False, 'stderr': 'bad', 'stdout': ''}
            with patch('solver_needs_study.advanced.execute', return_value=failed) as execute:
                result = capture_query(root, {'id': 'q', 'file': 'q.smt2', 'result': 'unknown'}, self.config())
                self.assertIsNone(result[0])
                self.assertEqual(result[2]['reason'], 'worker_failure_or_wall_timeout')
                capture_query(root, {'id': 'q', 'file': 'q.smt2', 'result': 'unknown'}, self.config())
                self.assertEqual(execute.call_count, 1)

    def test_initialization_never_silently_reduces_context(self):
        with tempfile.TemporaryDirectory() as work, patch.object(study, 'LocalVLLM', side_effect=RuntimeError('KV cache insufficient')):
            with self.assertRaisesRegex(RuntimeError, 'fixed 64k'):
                study.initialize_inference(Path(work), self.config())
            self.assertEqual(read_json(Path(work) / 'initialization-error.json')['max_model_len'], 65536)

    def test_three_proposals_both_arms_shared_first_prompt_and_resume(self):
        config = self.config()
        base, extra = {'queries': [{'id': 'q', 'quantifiers': []}]}, {'queries': []}
        advanced = {'queries': [], 'non_inst_clauses': [{'rule': 'smt', 'clause_literals_smt': ['P']}]}
        initial = {'internals': base, 'complement': extra, 'advanced': advanced, 'context': {}, 'availability': 'available'}
        checked = {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''}
        task = {'prefix': 'verus! { proof fn f() {', 'suffix': '} }', 'proof_context': True}
        calls = []
        def generate(messages, config, seed):
            calls.append((messages, seed))
            return {'text': json.dumps(actions.EMPTY), 'rendered_prompt': 'prompt', 'input_tokens': 100,
                    'output_tokens': 10, 'truncated': False, 'inference_seconds': 0.01}
        inference = SimpleNamespace(tokenizer=Tokenizer(), generate=generate)
        with tempfile.TemporaryDirectory() as work, \
             patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))), \
             patch.object(actions, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))), \
             patch.object(study, 'internals', return_value={k: v for k, v in initial.items() if k != 'advanced'}), \
             patch('solver_needs_study.advanced.attach', side_effect=lambda *args: {**args[-1], 'advanced': advanced}) as attach:
            root = Path(work)
            frozen = root / 'inputs/case'
            write_json(frozen / 'task.json', task)
            write_text(frozen / 'candidate.rs', actions.render(task, actions.EMPTY))
            write_json(frozen / 'verification.json', checked)
            write_json(frozen / 'feedback.json', initial)
            verifier = SimpleNamespace(verify=lambda *a, **kw: checked)
            for arm in ('with_internals', 'without_internals'):
                result = study.run_case(root, arm, {'id': 'case'}, config, inference, verifier)
                self.assertEqual(len(result['attempts']), 3)
            self.assertEqual(attach.call_count, 2)  # repairs of treatment only
            a = read_json(root / 'with_internals/case/attempt_01/request.json')
            b = read_json(root / 'without_internals/case/attempt_01/request.json')
            self.assertEqual(a['shared_feedback_sha256'], b['shared_feedback_sha256'])
            self.assertEqual(a['common_messages_sha256'], b['common_messages_sha256'])
            self.assertEqual(a['seed'], b['seed'])
            self.assertTrue(a['advanced_exposed'])
            self.assertFalse(b['advanced_exposed'])
            self.assertTrue(b['complement_exposed'])
            self.assertEqual(a['messages'][0], b['messages'][0])
            block = '<advanced_internals>\n' + json.dumps(advanced, ensure_ascii=False, indent=2) + '\n</advanced_internals>\n'
            self.assertEqual(a['messages'][1]['content'].replace(block, ''), b['messages'][1]['content'])
            for arm in ('with_internals', 'without_internals'):
                study.run_case(root, arm, {'id': 'case'}, config, inference, verifier)
            self.assertEqual(len(calls), 6)
            manifest = {'cases': [{'id': 'case', 'paper_label': 'AX', 'release_label': 'AX'}],
                        'config': config, 'scope': 'test'}
            with patch.object(study, 'validate', return_value=manifest):
                comparison = study.compare(root)
            self.assertTrue(comparison['complete'])
            self.assertTrue(comparison['first_pair_check_passed'])
            self.assertEqual(comparison['summaries']['with_internals']['advanced_exposed_attempts'], 3)
            self.assertEqual(comparison['summaries']['without_internals']['advanced_exposed_attempts'], 0)


if __name__ == '__main__':
    unittest.main()
