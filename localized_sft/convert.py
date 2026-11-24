"""Convert already-filtered SAFE exports; no LLM, Verus or Z3 execution."""
import argparse
from bisect import bisect_left
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re

from baseline.integrity import tokens
from repair_study.regions import spans
from .editor import FORMAT, EditError, apply, overlap, regions
from .prompt import ROOT, messages


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def code_block(text):
    found = list(re.finditer(r'^```(?:rust|verus)?\s*\n(.*?)^```\s*$', text, re.M | re.S))
    if len(found) != 1:
        raise ValueError('Expected exactly one program fence')
    return found[0].group(1)


def parts(row):
    turns = row['messages']
    if [t['role'] for t in turns] != ['system', 'user', 'assistant']:
        raise ValueError('Expected system/user/assistant export')
    user = turns[1]['content']
    def tag(name, required=True):
        found = re.search('<' + name + r'>\s*(.*?)\s*</' + name + '>', user, re.S)
        if found is None and required:
            raise ValueError('Missing tag: ' + name)
        return found.group(1) if found else None
    payload = tag('solver_internals', False)
    diagnostics = tag('verus_diagnostics')
    if row['kind'] == 'repair_frontend':
        diagnostics += '\nNo SMT internals were obtained: compilation/parsing failed before SMT obligations were captured.'
    return code_block(tag('current_program')), code_block(turns[-1]['content']), diagnostics, json.loads(payload) if payload else None


def action_for(source, target, offered=None):
    """Cover token differences with input-only sites; certify by replaying the edits."""
    try:
        sites = regions(source) if offered is None else offered
        ss = spans(source)
    except ValueError as error:
        raise EditError('editor_unparseable', str(error)) from error
    tt = spans(target)
    a, b = [t[0] for t in ss], [t[0] for t in tt]
    if a == b:
        raise EditError('no_effect', 'Source and target have identical tokens')
    starts = [t[1] for t in ss]
    opcodes = SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    changes = [op for op in opcodes if op[0] != 'equal']
    intervals = {}
    for site in sites:
        lo, hi = bisect_left(starts, site['start']), bisect_left(starts, site['end'])
        intervals[site['id']] = (lo, hi)
    def covers(site, op):
        lo, hi = intervals[site['id']]
        _, i, j, _, _ = op
        return lo <= i <= j <= hi and (lo != hi or i == j == lo)
    chosen = {}
    for op in changes:
        options = [s for s in sites if covers(s, op)]
        if not options:
            raise EditError('unrepresentable', 'Token difference outside offered regions at token ' + str(op[1]))
        site = min(options, key=lambda s: (s['end'] - s['start'], s['kind'], s['id']))
        chosen[site['id']] = site
    # Prefer an enclosing offered region over overlapping nested edits.
    while True:
        pairs = [(x, y) for i, x in enumerate(chosen.values()) for y in list(chosen.values())[i + 1:] if overlap(x, y)]
        if not pairs:
            break
        x, y = pairs[0]
        enclosing = [s for s in sites if s['start'] <= min(x['start'], y['start']) and s['end'] >= max(x['end'], y['end'])]
        if not enclosing:
            raise EditError('unrepresentable', 'Differences require overlapping regions')
        parent = min(enclosing, key=lambda s: s['end'] - s['start'])
        chosen.pop(x['id']); chosen.pop(y['id'])
        chosen[parent['id']] = parent
    def boundary(index, right):
        values = []
        for kind, i, j, k, l in opcodes:
            if kind == 'equal' and i <= index <= j:
                values.append(k + index - i)
            elif kind != 'equal':
                if index == i:
                    values.append(k)
                if index == j:
                    values.append(l)
        if not values:
            raise EditError('unrepresentable', 'Region boundary crosses an unmatched token run')
        return max(values) if right else min(values)
    edits = []
    for site in sorted(chosen.values(), key=lambda s: s['start']):
        lo, hi = intervals[site['id']]
        k, l = boundary(lo, False), boundary(hi, True)
        replacement = target[tt[k][1]:tt[l - 1][2]] if k < l else ''
        edits.append({'site_id': site['id'], 'replacement': replacement})
    action = {'edits': edits}
    result = apply(source, action, sites)
    if tokens(result) != b:
        raise EditError('unrepresentable', 'Applied edits do not reproduce reference tokens')
    return action, sites


def convert(source, output, tokenizer, limit=None):
    if output.exists():
        raise ValueError('Use a new output directory; source/results are never overwritten')
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    for name in ('train.jsonl', 'validation.jsonl'):
        if sha(source / name) != manifest['files_sha256'][name]:
            raise ValueError('Source export hash mismatch: ' + name)
    output.mkdir(parents=True)
    counts, omissions, edit_counts, kinds = {}, Counter(), Counter(), Counter()
    families, ids = {}, set()
    max_tokens = 0
    with (output / 'conversion-audit.jsonl').open('w', encoding='utf-8', newline='\n') as audit:
        for split in ('train', 'validation'):
            stats, family_set = Counter(), set()
            with (source / f'{split}.jsonl').open(encoding='utf-8') as stream, (output / f'{split}.jsonl').open('w', encoding='utf-8', newline='\n') as dest:
                for line in stream:
                    row = json.loads(line)
                    stats['source_rows'] += 1
                    if row['id'] in ids:
                        raise ValueError('Duplicate source ID: ' + row['id'])
                    ids.add(row['id'])
                    record = {'id': row['id'], 'split': split, 'source_kind': row['kind']}
                    if row['kind'] not in ('repair_internals', 'repair_frontend'):
                        stats['generation_kept_separate'] += 1
                        continue
                    if limit is not None and stats['repairs_examined'] >= limit:
                        stats['outside_pilot_limit'] += 1
                        continue
                    stats['repairs_examined'] += 1
                    if stats['repairs_examined'] % 100 == 0:
                        print(split, 'repairs examined:', stats['repairs_examined'],
                              'converted so far:', stats['converted'], flush=True)
                    try:
                        code, target, diagnostic, payload = parts(row)
                        action, sites = action_for(code, target)
                        request = messages(code, diagnostic, payload, offered=sites)
                        turns = request + [{'role': 'assistant', 'content': json.dumps(action, ensure_ascii=False)}]
                        length = len(tokenizer.apply_chat_template(turns, tokenize=True, add_generation_prompt=False))
                        prompt_length = len(tokenizer.apply_chat_template(request, tokenize=True, add_generation_prompt=True))
                        if length > 32768 or prompt_length + 4096 > 32768 or length - prompt_length > 4096:
                            raise EditError('context_budget', 'Full training length or inference output reservation exceeded')
                        item = {**row, 'messages': turns, 'response_format': FORMAT,
                            'source_target_sha256': hashlib.sha256(target.encode()).hexdigest(),
                            'conversion': {'edits': len(action['edits']), 'training_tokens': length,
                                'prompt_tokens': prompt_length, 'target_equivalence': 'identical lexer tokens',
                                'reference_validation': 'inherited from filtered SAFE export; no new solver run'}}
                        dest.write(json.dumps(item, ensure_ascii=False) + '\n')
                        family_set.add(row['family_id'])
                        stats['converted'] += 1
                        edit_counts[len(action['edits'])] += 1
                        lookup = {s['id']: s for s in sites}
                        kinds.update(lookup[e['site_id']]['kind'] for e in action['edits'])
                        max_tokens = max(max_tokens, length)
                        record.update(status='converted', **item['conversion'])
                    except (ValueError, KeyError, TypeError, IndexError) as error:
                        category = getattr(error, 'category', 'conversion_error')
                        stats['not_converted'] += 1
                        omissions[category] += 1
                        record.update(status=category, reason=str(error))
                    audit.write(json.dumps(record, ensure_ascii=False) + '\n')
            counts[split], families[split] = dict(stats), family_set
    if families['train'] & families['validation']:
        raise ValueError('Source family split leaked across train/validation')
    implementation = {str(p.relative_to(ROOT)): sha(p) for p in [*Path(__file__).parent.glob('*.py'), ROOT / 'prompts/safe-multiedit.txt', ROOT / 'prompts/safe-internals.txt', ROOT / 'repair_study/regions.py', ROOT / 'repair_study/regions_v2.py', ROOT / 'baseline/integrity.py', ROOT / 'solver_needs_study/actions.py', ROOT / 'scripts/train_safe_sft.py', ROOT / 'scripts/train_safe_multiedit.py']}
    report = {**manifest, 'response_format': FORMAT, 'source_export': str(source.resolve()),
        'source_manifest_sha256': sha(source / 'manifest.json'), 'source_files_sha256': manifest['files_sha256'],
        'counts': counts, 'omissions': dict(omissions), 'edits_per_example': dict(edit_counts),
        'edits_by_kind': dict(kinds), 'max_training_tokens': max_tokens, 'pilot_limit_per_split': limit,
        'implementation': implementation, 'families_preserved': True,
        'reference_validation': 'Inherited validated targets; applied edits reproduce reference lexer tokens. No Verus/Z3 executed.',
        'tokenizer': {'model': 'Qwen/Qwen2.5-Coder-14B-Instruct', 'revision': 'aedcc2d42b622764e023cf882b6652e646b95671'},
        'files_sha256': {f'{s}.jsonl': sha(output / f'{s}.jsonl') for s in counts}}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# SAFE multi-edit conversion', '', 'Only previously accepted debugging rows; original generation rows are not converted.', '',
        '| Split | Repairs examined | Converted | Not converted |', '|---|---|---|---|']
    for split, c in counts.items():
        lines.append(f"| {split} | {c.get('repairs_examined', 0)} | {c.get('converted', 0)} | {c.get('not_converted', 0)} |")
    lines += ['', 'Omissions: ' + str(dict(omissions)), 'Edits per example: ' + str(dict(edit_counts)),
        'Edits by kind: ' + str(dict(kinds)), 'Maximum training tokens: ' + str(max_tokens), report['reference_validation']]
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path('data/safe/sft-enriched-v1'))
    p.add_argument('--output', type=Path, default=Path('data/safe/sft-local-multiedit-v1'))
    p.add_argument('--limit', type=int, help='Optional debugging row limit PER split, for a pilot only')
    args = p.parse_args()
    from safe_internals.pipeline import load_tokenizer
    tokenizer, _ = load_tokenizer()
    convert(args.source, args.output, tokenizer, args.limit)


if __name__ == '__main__':
    main()
