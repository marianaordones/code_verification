import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from verusbench_study import __main__ as vb


class VerusBenchTests(unittest.TestCase):
    def test_screening_removes_original_assumptions_before_selection(self):
        cfg = vb.config(vb.ROOT / 'configs/verusbench-sonnet20-v2.json')
        inventory = vb.load_tasks(vb.ROOT / 'data/manifest.json')
        fixed = read_json(vb.selection_path(vb.ROOT / 'configs/verusbench-sonnet20-v2.json'))
        selected = vb.select(inventory, cfg['selection_seed'], 20, fixed['excluded_ids'], True)
        self.assertEqual([t['id'] for t in selected], [t['id'] for t in fixed['tasks']])
        self.assertEqual(len(selected), 20)
        self.assertNotIn('misc_havoc_inline_post', [t['id'] for t in selected])
        self.assertIn('misc_havoc_inline_post', [t['id'] for t in fixed['screened_out_originals']])
        for row in selected:
            source = Path(row['file']).read_text(encoding='utf-8')
            self.assertTrue(vb.lexical_check(source, source)[0])

    def test_twenty_additional_programs_are_fixed_balanced_and_disjoint(self):
        old = read_json(vb.SELECTION)['tasks']
        cfg = vb.config(vb.ROOT / 'configs/verusbench-sonnet20.json')
        fixed = read_json(vb.selection_path(vb.ROOT / 'configs/verusbench-sonnet20.json'))
        self.assertEqual(cfg['model'], 'claude-sonnet-5-5')
        self.assertEqual(cfg['effort'], 'low')
        self.assertEqual(cfg['max_attempts'], 3)
        self.assertEqual(len(fixed['tasks']), 20)
        self.assertEqual(len({t['id'] for t in fixed['tasks']}), 20)
        self.assertFalse({t['id'] for t in old} & {t['id'] for t in fixed['tasks']})
        self.assertFalse({t['sha256'] for t in old} & {t['sha256'] for t in fixed['tasks']})
        self.assertEqual(fixed['category_counts'], {'CloverBench': 5, 'Diffy': 5, 'MBPP': 5, 'Misc': 5})
        regenerated = vb.select(vb.load_tasks(vb.ROOT / 'data/manifest.json'), cfg['selection_seed'], 20, fixed['excluded_ids'])
        self.assertEqual([t['id'] for t in regenerated], [t['id'] for t in fixed['tasks']])

    def test_report_uses_actual_twenty_program_denominator(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            selection = [{'id': str(i), 'category': 'Misc'} for i in range(20)]
            for row in selection:
                write_json(root / 'inputs' / row['id'] / 'verification.json', {'success': False})
            manifest = {'selection': selection, 'config': vb.config(vb.ROOT / 'configs/verusbench-sonnet20.json')}
            with patch.object(vb, 'validate', return_value=manifest):
                result = vb.compare(root)
            self.assertEqual(result['expected'], 20)
            self.assertFalse(result['complete'])
            self.assertIn('0/20', (root / 'comparison.md').read_text())

    def test_sonnet_changes_only_model(self):
        old = vb.config()
        new = vb.config(vb.ROOT / 'configs/verusbench-sonnet5.json')
        self.assertEqual({k for k in old if old[k] != new[k]}, {'model'})
        self.assertEqual(new['model'], 'claude-sonnet-5-5')

    def test_sonnet_imports_inputs_without_model_responses(self):
        from baseline.storage import digest
        with tempfile.TemporaryDirectory() as work:
            source, target = Path(work) / 'opus', Path(work) / 'sonnet'
            write_text(source / 'inputs/case/original.rs', 'fn main() {}')
            write_json(source / 'with_internals/case/attempt_01/response.json', {'text': 'must not copy'})
            files = {'inputs/case/original.rs': digest((source / 'inputs/case/original.rs').read_bytes())}
            prompts = {n: digest((vb.ROOT / n).read_bytes()) for n in
                       ('prompts/v4/system.txt', 'prompts/verusbench-claude/solver-info.txt')}
            selection = read_json(vb.SELECTION)['tasks']
            write_json(source / 'manifest.json', {'config': vb.config(), 'selection': selection,
                       'tools': {}, 'files': files, 'implementation': prompts})
            vb.import_inputs(target, source, vb.config(vb.ROOT / 'configs/verusbench-sonnet5.json'), {},
                             vb.ROOT / 'configs/verusbench-sonnet5.json')
            self.assertEqual((target / 'inputs/case/original.rs').read_bytes(), (source / 'inputs/case/original.rs').read_bytes())
            self.assertFalse((target / 'with_internals').exists())
            self.assertEqual(read_json(target / 'manifest.json')['files'], files)

    def test_selection_uses_original_inputs_and_no_outcomes(self):
        with tempfile.TemporaryDirectory() as work:
            tasks = []
            for i in range(12):
                file = Path(work) / f'{i}.rs'
                file.write_text(f'fn f{i}() {{}}')
                tasks.append({'id': str(i), 'category': str(i % 4), 'file': str(file)})
            chosen = vb.select(tasks, 20261024)
            self.assertEqual(len(chosen), 5)
            self.assertEqual(chosen, vb.select(list(reversed(tasks)), 20261024))
            self.assertEqual(len({t['category'] for t in chosen}), 4)

    def test_source_extraction_and_ambiguous_fences(self):
        source = 'fn main() {}'
        self.assertEqual(vb.extract_source(source), (source, 'direct_source'))
        self.assertEqual(vb.extract_source('Explanation\n```rust\n' + source + '\n```')[0], source)
        for text in ('```rust\nfn x(){}', '```rust\na\n```\n```rust\nb\n```', '```json\n{}\n```'):
            with self.assertRaises(ValueError):
                vb.extract_source(text)

    def test_only_internals_differ_in_initial_prompt(self):
        checked = {'stdout': '', 'stderr': ''}
        control = vb.messages('original', 'current', checked, {}, None, [])
        treatment = vb.messages('original', 'current', checked, {}, {'availability': 'available'}, [])
        block = '<solver_internals>\n' + json.dumps({'availability': 'available'}, indent=2) + '\n</solver_internals>\n'
        self.assertEqual(treatment[0], control[0])
        self.assertEqual(treatment[1]['content'].replace(block, ''), control[1]['content'])

    def test_three_total_proposals_and_resume_without_model_calls(self):
        checked = {'success': False, 'stdout': '', 'stderr': '', 'error_type': 'verification'}
        guard_result = {'valid': True, 'status': 'valid'}
        calls = []
        def generate(prompt, cfg, folder):
            calls.append(folder)
            return {'text': 'fn main() {}'}
        tokenizer = SimpleNamespace(apply_chat_template=lambda *a, **kw: [1])
        inference = SimpleNamespace(tokenizer=tokenizer, generate_at=generate)
        verifier = SimpleNamespace(verify=lambda *a: checked)
        guard = SimpleNamespace(validate=lambda *a: guard_result)
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            frozen = root / 'inputs/case'
            write_text(frozen / 'original.rs', 'fn main() {}')
            write_json(frozen / 'verification.json', checked)
            write_json(frozen / 'integrity.json', guard_result)
            write_json(frozen / 'payload.json', {})
            vb.run_case(root, 'without_internals', {'id': 'case'}, vb.config(), inference, verifier, guard)
            result = read_json(root / 'without_internals/case/task.json')
            self.assertEqual(len(result['attempts']), 3)
            self.assertFalse(result['success'])
            vb.run_case(root, 'without_internals', {'id': 'case'}, vb.config(), inference, verifier, guard)
            self.assertEqual(len(calls), 3)

    def test_verus_success_cannot_override_invalid_integrity(self):
        initial = {'success': False, 'stdout': '', 'stderr': '', 'error_type': 'verification'}
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            frozen = root / 'inputs/case'
            write_text(frozen / 'original.rs', 'fn main() {}')
            write_json(frozen / 'verification.json', initial)
            write_json(frozen / 'integrity.json', {'valid': True})
            write_json(frozen / 'payload.json', {})
            inference = SimpleNamespace(tokenizer=SimpleNamespace(apply_chat_template=lambda *a, **kw: [1]),
                generate_at=lambda *a: {'text': 'fn main() { let x = 1; }'})
            verifier = SimpleNamespace(verify=lambda *a: {**initial, 'success': True, 'error_type': None})
            guard = SimpleNamespace(validate=lambda *a: {'valid': False, 'status': 'invalid'})
            vb.run_case(root, 'without_internals', {'id': 'case'}, vb.config(), inference, verifier, guard)
            self.assertFalse(read_json(root / 'without_internals/case/task.json')['success'])

    def test_treatment_refreshes_payload_after_failed_candidates(self):
        checked = {'success': False, 'stdout': '', 'stderr': '', 'error_type': 'verification'}
        calls = []
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            frozen = root / 'inputs/case'
            write_text(frozen / 'original.rs', 'fn main() {}')
            write_json(frozen / 'verification.json', checked)
            write_json(frozen / 'integrity.json', {'valid': True})
            write_json(frozen / 'payload.json', {'availability': 'available', 'marker': 0})
            def generate(prompt, cfg, folder):
                calls.append(prompt)
                return {'text': f'fn main() {{ let x = {len(calls)}; }}'}
            inference = SimpleNamespace(tokenizer=SimpleNamespace(apply_chat_template=lambda *a, **kw: [1]), generate_at=generate)
            verifier = SimpleNamespace(verify=lambda *a: checked)
            guard = SimpleNamespace(validate=lambda *a: {'valid': True, 'status': 'valid'})
            with patch.object(vb, 'build_payload', side_effect=[{'availability': 'available', 'marker': 1},
                                                              {'availability': 'available', 'marker': 2}]) as refresh:
                vb.run_case(root, 'with_internals', {'id': 'case'}, vb.config(), inference, verifier, guard)
            self.assertEqual(refresh.call_count, 2)
            for index, prompt in enumerate(calls):
                self.assertIn(f'"marker": {index}', prompt[1]['content'])


if __name__ == '__main__':
    unittest.main()
