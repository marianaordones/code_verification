import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from baseline import verusbench_local as study
from baseline.storage import read_json, write_json, write_text, digest
from repair_study.relevance import source_context

CODE = 'verus! {\nproof fn f() {\n    let x = 0;\n}\n}'

class Tokenizer:
    def encode(self, text, **kw):
        return list(text)
    def apply_chat_template(self, messages, **kw):
        return list(json.dumps(messages))

class LocalTests(TestCase):
    def config(self):
        c = read_json(study.ROOT / 'configs/verusbench-qwen14b-three-arms.json')
        c.pop('complement_token_budget')
        return c

    def test_regions_explicitly_report_unavailable(self):
        sites, audit = study.audit_sites('verus! {}')
        self.assertFalse(sites)
        self.assertEqual(audit['status'], 'no_safe_sites')
        sites, audit = study.audit_sites('while (')
        self.assertEqual(audit['status'], 'region_parser_error')

    def test_two_repairs_common_inputs_rejected_edit_retained_and_resume(self):
        config = self.config()
        calls, replay_folders = [], []
        checked = {'success': False, 'error_type': 'verification', 'stdout': 'failed', 'stderr': ''}
        integrity_result = {'valid': True, 'status': 'valid', 'seconds': 0}
        def generate(prompt, config, seed):
            calls.append((prompt, seed))
            edit = {'site_id': 'WRONG' if seed == config['seed'] + 1 else 'R1', 'replacement': 'proof { assert(true); }'}
            return {'text': json.dumps(edit), 'input_tokens': 100, 'output_tokens': 10, 'truncated': False, 'inference_seconds': 0.01}
        def verify(path):
            success = 'assert(true)' in path.read_text()
            write_json(path.parent / 'solver/report.json', {'queries': [], 'capture_errors': []})
            return {**checked, 'success': success, 'error_type': None if success else 'verification'}
        def feedback(folder, frozen, original, code, verification, check, progress, inference, config, initial=False):
            replay_folders.append(folder)
            write_json(folder / 'solver/report.json', {'queries': [], 'capture_errors': []})
            return {'internals': {'queries': [{'id': 'q', 'quantifiers': []}]}, 'context': source_context(code, verification)}
        with tempfile.TemporaryDirectory() as tmp, patch.object(study, 'feedback', side_effect=feedback):
            root = Path(tmp)
            frozen = root / 'inputs/case'
            write_text(frozen / 'candidate.rs', CODE)
            write_text(frozen / 'original.rs', CODE)
            write_json(frozen / 'verification.json', checked)
            write_json(frozen / 'integrity.json', integrity_result)
            write_json(frozen / 'initial/solver/report.json', {'queries': [], 'capture_errors': []})
            row = {'id': 'case', 'category': 'Misc', 'status': 'eligible'}
            engine = SimpleNamespace(tokenizer=Tokenizer(), generate=generate)
            verifier = SimpleNamespace(verify=verify)
            integrity = SimpleNamespace(validate=lambda *a: integrity_result)
            for arm in study.ARMS:
                result = study.run_case(root, arm, row, config, engine, verifier, integrity)
                self.assertTrue(result['success'])
                self.assertEqual(len(result['repairs']), 2)
                self.assertEqual(result['repairs'][0]['status'], 'edit_error')
                self.assertFalse(result['repairs'][0]['retained_proposal'])
                self.assertEqual((root / arm / 'case/repair_01/state.rs').read_text(), CODE)
                study.run_case(root, arm, row, config, engine, verifier, integrity)
            self.assertEqual(len(calls), 4)
            self.assertEqual(len(replay_folders), 2)
            self.assertEqual(replay_folders[1].name, 'state-feedback')
            with patch.object(study, 'validate', return_value={'tasks': [row], 'scope': 'test'}):
                report = study.compare(root)
            self.assertTrue(report['complete'])
            self.assertTrue(report['first_pairs_valid'])
            self.assertEqual(report['summaries']['with_internals']['repaired_by_repair'], {'1': 0, '2': 1})
            self.assertEqual(report['summaries']['with_internals']['proposal_statuses']['edit_error'], 1)

    def test_prepare_freezes_saved_candidates_and_separates_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / 'source', root / 'study'
            original = root / 'original.rs'
            write_text(original, CODE)
            config = self.config()
            tasks = [{'id': 'T' + str(i), 'category': 'Misc', 'sha256': digest(original.read_bytes()), 'file': str(original)} for i in range(150)]
            write_json(source / 'run.json', {'config': config, 'tasks': tasks, 'tools': {}, 'solver_api': {}})
            for i, task in enumerate(tasks):
                folder = source / 'shared' / task['id'] / 'attempt_00'
                code = 'verus! {}' if i == 2 else CODE
                write_text(folder / 'candidate.rs', code)
                write_json(folder / 'request.json', {'input_sha256': task['sha256']})
                write_json(folder / 'response.json', {'text': code})
                success = i >= 3
                write_json(folder / 'verification.json', {'success': success, 'stdout': '', 'stderr': ''})
                write_json(folder / 'integrity.json', {'valid': i != 1})
                write_json(folder / 'result.json', {'success': success})
                write_json(folder / 'solver/report.json', {'queries': [], 'capture_errors': []})
            with patch.object(study, 'load_tasks', return_value=tasks):
                study.prepare(source, output)
            manifest = study.validate(output)
            self.assertEqual([r['status'] for r in manifest['tasks'][:3]], ['eligible', 'initial_integrity_rejected', 'editor_unavailable'])
            self.assertEqual(read_json(output / 'selected_ids.json')['eligible_ids'], ['T0'])
            # Changing a frozen original must be caught before running.
            write_text(output / 'inputs/T0/original.rs', 'changed')
            with self.assertRaisesRegex(ValueError, 'Frozen input'):
                study.validate(output)
