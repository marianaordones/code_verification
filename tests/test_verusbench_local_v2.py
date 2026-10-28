import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from baseline import verusbench_local_v2 as study
from baseline.integrity import lexical_check, tokens
from baseline.storage import read_json, write_json, write_text
from repair_study.regions_v2 import regions, apply_patch
from repair_study.relevance import source_context

CODE = 'verus! {\nproof fn f() {\n    let x = 0;\n}\n}'

class Tokenizer:
    def encode(self, text, **kw):
        return list(text)
    def apply_chat_template(self, messages, **kw):
        return list(json.dumps(messages))

class SafeSitesTests(TestCase):
    def test_contracts_and_spec_bodies_are_excluded_tail_is_offered(self):
        code = """verus! {
spec fn helper(a: Seq<int>) -> bool {
    a.len() > 0
}
fn f(a: Vec<int>) -> (ret: int)
    requires
        a.len() > 0,
    ensures
        a.len() > 0,
    decreases
        a.len(),
{
    a[0]
}
}"""
        sites = regions(code)
        self.assertEqual(len(sites), 1)
        self.assertEqual(code[sites[0]['start']:].splitlines()[0], 'a[0]')
        result, _ = apply_patch(code, json.dumps({'site_id': sites[0]['id'], 'replacement': 'proof { assert(true); }'}), sites)
        self.assertIn('proof { assert(true); }\na[0]', result)
        self.assertTrue(lexical_check(code, result)[0])

    def test_no_sites_inside_loop_annotation_closure_literal_or_pattern(self):
        code = """verus! {
fn f(a: Vec<int>) -> (r: int) {
    let mut i = 0;
    while i < a.len()
        invariant
            a.len() > 0,
    {
        i += 1;
    }
    let closure = |x: int| {
        x.foo()
    };
    let structure = S {
        field: a.len(),
    };
    match a {
        Pattern {
            field: x,
        } => {
            x.foo()
        },
    }
    i
}
}"""
        sites = regions(code)
        lines = {s['line'] for s in sites if s['kind'] == 'insert_proof'}
        for i, line in enumerate(code.splitlines(), 1):
            if line.strip() in ('a.len() > 0,', 'x.foo()', 'field: a.len(),', 'field: x,'):
                self.assertNotIn(i, lines)
        self.assertTrue(any(s['kind'] == 'loop_invariants' for s in sites))
        self.assertTrue(any(code[s['start']:].splitlines()[0] == 'i' for s in sites))

    def test_if_else_tail_expressions_and_proof_restoration(self):
        code = """verus! {
fn f(a: Vec<int>, flag: bool) -> (r: int) {
    if flag {
        a[0]
    } else {
        a[1]
    }
}
}"""
        sites = regions(code)
        offered = [code[s['start']:].splitlines()[0] for s in sites]
        self.assertIn('a[0]', offered)
        self.assertIn('a[1]', offered)
        target = 'verus! {\nfn f(a: Vec<int>) -> (r: int) {\n    proof { assert(true); }\n    a[0]\n}\n}'
        proof = next(s for s in regions(target) if s['kind'] == 'proof_block')
        stripped = target[:proof['start']] + target[proof['end']:]
        options = regions(stripped)
        site = next(s for s in options if stripped[s['start']:].splitlines()[0] == 'a[0]')
        restored, _ = apply_patch(stripped, json.dumps({'site_id': site['id'], 'replacement': proof['existing_text']}), options)
        self.assertEqual(tokens(restored), tokens(target))

    def test_conditional_contract_does_not_hide_function_body(self):
        code = """verus! {
fn f(a: Vec<int>) -> (ret: Option<int>)
    ensures
        if let Some(x) = ret {
            a.len() > 0
        } else {
            a.len() == 0
        },
{
    let x = 0;
    None
}
}"""
        sites = regions(code)
        offered = [code[s['start']:].splitlines()[0] for s in sites]
        self.assertIn('let x = 0;', offered)
        self.assertIn('None', offered)
        self.assertNotIn('a.len() > 0', offered)
        self.assertNotIn('a.len() == 0', offered)

    def test_conditional_loop_annotation_is_not_a_statement_body(self):
        code = """verus! {
fn f(a: Vec<int>, flag: bool) {
    let mut i = 0;
    while i < a.len()
        invariant
            if flag {
                a.len() > 0
            } else {
                a.len() == 0
            },
    {
        i += 1;
    }
}
}"""
        sites = regions(code)
        inserted = [code[s['start']:].splitlines()[0] for s in sites if s['kind'] == 'insert_proof']
        self.assertNotIn('a.len() > 0', inserted)
        self.assertNotIn('a.len() == 0', inserted)
        self.assertIn('i += 1;', inserted)

    def test_preparation_declares_four_proposals_and_separate_initial_statuses(self):
        config = read_json(study.ROOT / 'configs/verusbench-qwen14b-three-arms.json')
        tasks = [{'id': 'T' + str(i), 'category': 'Misc', 'sha256': 'sha', 'file': 'original.rs'} for i in range(150)]
        def read(path):
            if path.name == 'run.json':
                return {'config': config, 'tasks': tasks, 'tools': {}, 'solver_api': {}}
            if path.name == 'request.json':
                return {'input_sha256': 'sha'}
            if path.name == 'response.json':
                return {'text': CODE}
            if path.name == 'verification.json':
                return {'success': False}
            if path.name == 'result.json':
                return {'success': False}
            if path.name == 'integrity.json':
                key = path.parts[-3]
                status = {'T0': 'unparseable', 'T1': 'invalid', 'T2': 'checker_error'}.get(key, 'valid')
                return {'valid': status == 'valid', 'status': status}
            raise AssertionError(str(path))
        written = {}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            write_json(source / 'run.json', {'fixture': True})
            with patch.object(study, 'load_tasks', return_value=tasks), patch.object(study, 'read_json', side_effect=read), patch.object(Path, 'read_text', return_value=CODE), patch.object(study.shutil, 'copytree'), patch.object(study, 'write_text'), patch.object(study, 'write_json', side_effect=lambda path, data: written.update({path.name: data})):
                study.prepare(source, root / 'output')
        manifest = written['manifest.json']
        self.assertEqual(manifest['config']['max_repairs'], 3)
        self.assertEqual(manifest['config']['max_attempts'], 4)
        self.assertEqual([r['status'] for r in manifest['tasks'][:3]], ['initial_unparseable', 'initial_forbidden_change', 'initial_integrity_error'])

    def test_four_proposal_classification_and_three_repairs_resume(self):
        self.assertEqual(study.proposal_status(None, {'valid': False, 'status': 'invalid'}, {'error_type': 'syntax'}), 'forbidden_change')
        config = read_json(study.ROOT / 'configs/verusbench-qwen14b-three-arms.json')
        config.update(max_repairs=3)
        config.pop('complement_token_budget')
        checked = {'success': False, 'error_type': 'verification', 'stdout': 'old diagnostic', 'stderr': ''}
        valid = {'valid': True, 'status': 'valid', 'seconds': 0, 'reason': ''}
        calls, replayed = [], []
        def generate(prompt, config, seed):
            calls.append((prompt, seed))
            if seed == config['seed'] + 1:
                replacement = 'proof { assert(0 <= i as int < n as int); }'
            elif seed == config['seed'] + 2:
                replacement = 'proof { assume(true); }'
            else:
                replacement = 'proof { assert(true); }'
            return {'text': json.dumps({'site_id': 'R1', 'replacement': replacement}), 'input_tokens': 100,
                    'output_tokens': 20, 'truncated': False, 'inference_seconds': .01}
        def verify(path):
            code = path.read_text()
            write_json(path.parent / 'solver/report.json', {'queries': [], 'capture_errors': [], 'marker': 'PROPOSED'})
            if 'as int <' in code:
                return {**checked, 'error_type': 'syntax', 'stderr': 'expected comma near cast'}
            return {**checked, 'success': 'assert(true)' in code, 'error_type': None if 'assert(true)' in code else 'verification'}
        def integrity(original, candidate):
            code = candidate.read_text()
            if 'as int <' in code:
                return {**valid, 'valid': False, 'status': 'unparseable', 'reason': 'expected comma near cast'}
            if 'assume' in code:
                return {**valid, 'valid': False, 'status': 'invalid', 'reason': 'Forbidden trusted/bypass construct: assume'}
            return valid
        def feedback(folder, frozen, original, code, verification, check, progress, inference, config, initial=False, rejected=None):
            if initial:
                write_json(folder / 'solver/report.json', {'queries': [], 'capture_errors': [], 'marker': 'ORIGINAL'})
            else:
                self.assertEqual(read_json(folder / 'solver/report.json')['marker'], 'ORIGINAL')
                self.assertIsNotNone(rejected)
            replayed.append(folder)
            return {'context': source_context(code, verification), 'internals': {'queries': [{'id': 'q', 'quantifiers': []}]}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(study, 'feedback', side_effect=feedback):
            root = Path(tmp)
            frozen = root / 'inputs/test'
            write_text(frozen / 'candidate.rs', CODE)
            write_text(frozen / 'original.rs', CODE)
            write_json(frozen / 'verification.json', checked)
            write_json(frozen / 'integrity.json', valid)
            write_json(frozen / 'initial/solver/report.json', {'queries': [], 'capture_errors': [], 'marker': 'ORIGINAL'})
            row = {'id': 'test', 'status': 'eligible', 'category': 'Misc'}
            inference = SimpleNamespace(tokenizer=Tokenizer(), generate=generate)
            verifier = SimpleNamespace(verify=verify)
            checker = SimpleNamespace(validate=integrity)
            for arm in study.ARMS:
                result = study.run_case(root, arm, row, config, inference, verifier, checker)
                self.assertEqual([r['status'] for r in result['repairs']], ['unparseable', 'forbidden_change', 'verified'])
                self.assertEqual([r['overall_proposal'] for r in result['repairs']], [2, 3, 4])
                for n in (1, 2):
                    self.assertEqual((root / arm / 'test' / f'repair_{n:02}' / 'state.rs').read_text(), CODE)
                request2 = read_json(root / arm / 'test/repair_02/request.json')['messages'][1]['content']
                self.assertIn('<rejected_edit>', request2)
                self.assertIn('expected comma near cast', request2)
                self.assertIn('old diagnostic', request2)
                request3 = read_json(root / arm / 'test/repair_03/request.json')['messages'][1]['content']
                self.assertIn('Forbidden trusted/bypass construct: assume', request3)
                study.run_case(root, arm, row, config, inference, verifier, checker)
            self.assertEqual(len(calls), 6)
            self.assertEqual(len(replayed), 3)
            with patch.object(study, 'validate', return_value={'config': config, 'tasks': [row], 'scope': 'test'}):
                report = study.compare(root)
            self.assertTrue(report['complete'])
            self.assertTrue(report['first_pairs_valid'])
            for arm in study.ARMS:
                self.assertEqual(report['summaries'][arm]['unparseable'], 1)
                self.assertEqual(report['summaries'][arm]['forbidden_changes'], 1)
                self.assertEqual(report['summaries'][arm]['repaired_by_repair'], {'1': 0, '2': 0, '3': 1})
            self.assertIn('Do NOT write 0 <= i as int < N as int', calls[0][0][0]['content'])
