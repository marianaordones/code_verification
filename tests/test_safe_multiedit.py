import json
from pathlib import Path
import tempfile
import unittest

from baseline.integrity import tokens
from localized_sft.editor import LOOP_ATTRIBUTE, EditError, apply, regions
from localized_sft.convert import action_for, parts, convert, sha


SOURCE = '''verus! {
fn f(n: usize) -> (r: usize)
    ensures r == n,
{
    let mut i = 0;
    while i < n
        invariant
            i <= n,
    {
        i = i + 1;
    }
    proof { assert(i <= n); }
    i
}
}
'''


class MultiEditTests(unittest.TestCase):
    def test_atomic_offsets_and_round_trip(self):
        sites = regions(SOURCE)
        inv = next(s for s in sites if s['kind'] == 'loop_invariants')
        proof = next(s for s in sites if s['kind'] == 'proof_block')
        action = {'edits': [{'site_id': inv['id'], 'replacement': 'invariant i <= n, i >= 0,'},
                            {'site_id': proof['id'], 'replacement': 'proof { assert(i == n); }'}]}
        target = apply(SOURCE, action)
        converted, offered = action_for(SOURCE, target)
        self.assertEqual(tokens(apply(SOURCE, converted, offered)), tokens(target))
        self.assertEqual(len(converted['edits']), 2)
        self.assertEqual(SOURCE, SOURCE[:])

    def test_option_and_proof_change(self):
        target = SOURCE.replace('fn f', LOOP_ATTRIBUTE + '\nfn f').replace('assert(i <= n)', 'assert(i == n)')
        action, sites = action_for(SOURCE, target)
        self.assertEqual(tokens(apply(SOURCE, action, sites)), tokens(target))
        self.assertEqual(len(action['edits']), 2)
        back, sites = action_for(target, SOURCE)
        self.assertEqual(tokens(apply(target, back, sites)), tokens(SOURCE))

    def test_new_invariant_and_new_proof(self):
        source = SOURCE.replace('        invariant\n            i <= n,\n', '')
        target = source.replace('while i < n\n', 'while i < n\ninvariant i <= n,\n')
        action, _ = action_for(source, target)
        self.assertEqual(tokens(apply(source, action)), tokens(target))
        insertion = next(s for s in regions(SOURCE) if s['kind'] == 'insert_proof' and s['existing_text'] == '')
        action = {'edits': [{'site_id': insertion['id'], 'replacement': 'proof { assert(n >= 0); }'}]}
        target = apply(SOURCE, action)
        converted, _ = action_for(SOURCE, target)
        self.assertEqual(tokens(apply(SOURCE, converted)), tokens(target))

    def test_reject_duplicate_unknown_overlap_and_noop(self):
        sites = regions(SOURCE)
        proof = next(s for s in sites if s['kind'] == 'proof_block')
        edit = {'site_id': proof['id'], 'replacement': 'proof { assert(i == n); }'}
        for action in ({'edits': [edit, edit]}, {'edits': [{'site_id': 'BAD', 'replacement': ''}]},
                       {'edits': []}, {'edits': [{'site_id': proof['id'], 'replacement': proof['existing_text']}]}):
            with self.assertRaises(EditError):
                apply(SOURCE, action)
        fake = dict(proof, id='INNER', start=proof['start'] + 1, end=proof['end'] - 1,
                    existing_text=SOURCE[proof['start'] + 1:proof['end'] - 1])
        with self.assertRaises(EditError):
            apply(SOURCE, {'edits': [edit, {'site_id': 'INNER', 'replacement': 'proof {}'}]}, sites + [fake])
        with self.assertRaises(EditError):
            apply(SOURCE, '{"edits": [], "edits": []}')

    def test_no_target_derived_sites_or_contract_edits(self):
        target = SOURCE.replace('ensures r == n', 'ensures r <= n')
        with self.assertRaises(EditError):
            action_for(SOURCE, target)
        source_sites = regions(SOURCE)
        action_for(SOURCE, SOURCE.replace('assert(i <= n)', 'assert(i == n)'))
        self.assertEqual(source_sites, regions(SOURCE))
        option = next(s for s in source_sites if s['kind'] == 'loop_isolation_option')
        with self.assertRaises(EditError):
            apply(SOURCE, {'edits': [{'site_id': option['id'], 'replacement': '#[verifier::external_body]'}]})
        proof = next(s for s in source_sites if s['kind'] == 'proof_block')
        for value in ('proof { assume(false); }', 'proof { loop {} }', 'proof { admit(); }'):
            with self.assertRaises(EditError) as caught:
                apply(SOURCE, {'edits': [{'site_id': proof['id'], 'replacement': value}]})
            self.assertEqual(caught.exception.category, 'forbidden_edit')

    def test_plain_assert_insertion_roundtrip(self):
        site = next(s for s in regions(SOURCE) if s['kind'] == 'insert_proof')
        target = apply(SOURCE, {'edits': [{'site_id': site['id'], 'replacement': 'assert(n >= 0);'}]})
        action, _ = action_for(SOURCE, target)
        self.assertEqual(tokens(apply(SOURCE, action)), tokens(target))

    def test_legitimate_trigger_forms_are_retained(self):
        site = next(s for s in regions(SOURCE) if s['kind'] == 'proof_block')
        for annotation in ('#[trigger]', '#[trigger(0)]', '#![auto]'):
            code = 'proof { assert(forall|x: int| ' + annotation + ' p(x)); }'
            changed = apply(SOURCE, {'edits': [{'site_id': site['id'], 'replacement': code}]})
            self.assertIn(annotation, changed)

    def test_saved_export_parsing(self):
        user = '<current_program>\n```rust\n' + SOURCE + '```\n</current_program>\n<verus_diagnostics>error</verus_diagnostics>\n<solver_internals>{"queries": []}</solver_internals>'
        row = {'kind': 'repair_internals', 'messages': [{'role': 'system', 'content': ''},
            {'role': 'user', 'content': user}, {'role': 'assistant', 'content': '```rust\n' + SOURCE + '```'}]}
        source, target, diag, packet = parts(row)
        self.assertEqual(tokens(source), tokens(target))
        self.assertEqual(diag, 'error')
        self.assertEqual(packet, {'queries': []})

    def test_conversion_preserves_splits_packets_and_rejections(self):
        class Tokenizer:
            def apply_chat_template(self, turns, tokenize, add_generation_prompt):
                return [1] * sum(len(t['content']) // 10 for t in turns)
        def row(key, family, target):
            user = '<current_program>\n```rust\n' + SOURCE + '```\n</current_program>\n<verus_diagnostics>saved error</verus_diagnostics>\n<solver_internals>{"queries":[{"id":"q1"}]}</solver_internals>'
            return {'id': key, 'family_id': family, 'kind': 'repair_internals', 'messages': [
                {'role': 'system', 'content': 'OLD FULL FILE INSTRUCTION'}, {'role': 'user', 'content': user},
                {'role': 'assistant', 'content': '```rust\n' + target + '```'}]}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'; source.mkdir()
            train = [row('a', 'family-a', SOURCE.replace('assert(i <= n)', 'assert(i == n)')),
                     row('bad', 'family-b', SOURCE.replace('ensures r == n', 'ensures r <= n')),
                     {'id': 'gen', 'kind': 'generation', 'family_id': 'family-g', 'messages': []}]
            val = [row('v', 'family-v', SOURCE.replace('assert(i <= n)', 'assert(i == n)'))]
            for split, rows in [('train', train), ('validation', val)]:
                (source / f'{split}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
            (source / 'manifest.json').write_text(json.dumps({'files_sha256': {
                s + '.jsonl': sha(source / (s + '.jsonl')) for s in ('train', 'validation')}}))
            output = Path(folder) / 'converted'
            convert(source, output, Tokenizer())
            converted = json.loads((output / 'train.jsonl').read_text())
            self.assertEqual(converted['id'], 'a')
            self.assertEqual(converted['family_id'], 'family-a')
            self.assertIn('"q1"', converted['messages'][1]['content'])
            self.assertNotIn('OLD FULL', converted['messages'][0]['content'])
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['counts']['train']['converted'], 1)
            self.assertEqual(manifest['counts']['train']['not_converted'], 1)
            self.assertEqual(manifest['counts']['train']['generation_kept_separate'], 1)
            self.assertEqual(manifest['files_sha256']['train.jsonl'], sha(output / 'train.jsonl'))


if __name__ == '__main__':
    unittest.main()
