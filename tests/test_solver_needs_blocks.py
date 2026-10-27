import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from baseline.storage import write_json, write_text, read_json
from solver_needs_study import __main__ as study, actions, feedback
from diagnostics.z3_advanced_pilot import package
from test_solver_needs_advanced import sample, Tokenizer


class BlockTests(TestCase):
    def config(self):
        return study.configuration(study.ROOT / 'configs/solver-needs-qwen14b-blocks12k.json')

    def test_exclusive_packages_and_larger_caps(self):
        c = self.config()
        self.assertEqual(study.study_arms(c), ('matching', 'chains', 'non_inst_clauses'))
        self.assertEqual(c['advanced_token_budget'], 12288)
        for block in c['advanced_blocks']:
            p, s = package(sample(), [{'rule': 'smt', 'clause_literals_smt': ['P']}], {}, len,
                           token_budget=12288, block=block)
            self.assertTrue(p[block])
            self.assertLessEqual(s['actual_tokens'], 12288)
            for other in c['advanced_blocks']:
                if other != block:
                    self.assertFalse(p[other])
            self.assertGreater(s['limits'][block][0], {'matching': 12, 'chains': 6, 'non_inst_clauses': 24}[block])
            if block == 'chains':
                self.assertTrue(p['referenced_matches'])
            if block == 'non_inst_clauses':
                self.assertFalse(p['referenced_matches'])

    def test_three_arms_resume_and_common_first_input(self):
        c = self.config()
        variants = {b: {'payload': {b: [{'id': b}]}, 'selection': {'status': 'budgeted'}} for b in c['advanced_blocks']}
        initial = {'internals': {'queries': [{'id': 'q', 'quantifiers': []}]}, 'complement': {'queries': []},
                   'context': {}, 'availability': 'available', 'advanced_variants': variants}
        checked = {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''}
        task = {'prefix': 'verus! { proof fn f() {', 'suffix': '} }', 'proof_context': True}
        calls = []
        def generate(messages, config, seed):
            calls.append(seed)
            return {'text': json.dumps(actions.EMPTY), 'rendered_prompt': 'prompt', 'input_tokens': 100,
                    'output_tokens': 10, 'truncated': False, 'inference_seconds': 0.01}
        def attach(*args):
            cfg = args[-2]
            b = cfg['advanced_block']
            self.assertIsNone(cfg['advanced_blocks'])
            return {**args[-1], 'advanced': variants[b]['payload'], 'advanced_selection': variants[b]['selection']}
        with tempfile.TemporaryDirectory() as work, patch.object(feedback, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))), patch.object(actions, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))), patch.object(study, 'internals', return_value={k: v for k, v in initial.items() if k != 'advanced_variants'}), patch('solver_needs_study.advanced.attach', side_effect=attach) as collect:
            root = Path(work)
            frozen = root / 'inputs/case'
            write_json(frozen / 'task.json', task)
            write_text(frozen / 'candidate.rs', actions.render(task, actions.EMPTY))
            write_json(frozen / 'verification.json', checked)
            write_json(frozen / 'feedback.json', initial)
            inference = SimpleNamespace(tokenizer=Tokenizer(), generate=generate)
            verifier = SimpleNamespace(verify=lambda *a, **kw: checked)
            for arm in c['advanced_blocks']:
                study.run_case(root, arm, {'id': 'case'}, c, inference, verifier)
                study.run_case(root, arm, {'id': 'case'}, c, inference, verifier)
            self.assertEqual(len(calls), 9)
            self.assertEqual(collect.call_count, 6)
            manifest = {'config': c, 'cases': [{'id': 'case', 'paper_label': 'AX', 'release_label': 'AX'}]}
            with patch.object(study, 'validate', return_value=manifest):
                report = study.compare(root)
            self.assertTrue(report['complete'])
            self.assertTrue(report['first_pair_check_passed'])
            for arm in c['advanced_blocks']:
                self.assertEqual(report['summaries'][arm]['advanced_exposed_attempts'], 3)
