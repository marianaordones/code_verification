"""Three action families; proof helpers have isolated, typed insertion sites."""
import json
from baseline.integrity import group_end, tokens
from localized_sft.editor import EditError, apply as body_apply, regions as body_regions, validate_statements
from repair_study.regions import spans

ACTIONS = ('loop_invariants', 'assertions_and_proof', 'lemmas')


def regions(code):
    sites = [s for s in body_regions(code) if s['kind'] != 'loop_isolation_option']
    ts = spans(code)
    vs = [t[0] for t in ts]
    for i in range(len(vs) - 2):
        if vs[i:i + 3] == ['verus', '!', '{']:
            end = group_end(vs, i + 2) - 1
            sites.append({'kind': 'lemma_definitions', 'start': ts[end][1], 'end': ts[end][1],
                          'line': code.count('\n', 0, ts[end][1]) + 1, 'existing_text': ''})
    sites.sort(key=lambda s: (s['start'], s['end'], s['kind']))
    for i, s in enumerate(sites):
        s['id'] = f'R{i + 1}'
    return sites


def validate_lemmas(text, source):
    ts = spans(text)
    vs = [t[0] for t in ts]
    i, names = 0, set()
    source_tokens = tokens(source)
    while i < len(vs):
        if vs[i:i + 2] != ['proof', 'fn'] or i + 3 >= len(vs):
            raise EditError('editor_error', 'Lemma site accepts only proof fn definitions, without attributes')
        name = vs[i + 2]
        if name in names or any(source_tokens[j:j + 2] == ['fn', name] for j in range(len(source_tokens) - 1)):
            raise EditError('editor_error', 'Duplicate/colliding lemma name')
        names.add(name)
        j = i + 3
        while j < len(vs) and vs[j] != '{':
            if vs[j] in ('(', '['):
                j = group_end(vs, j)
            elif vs[j] in (';', '}'):
                raise EditError('editor_error', 'Ambiguous lemma header')
            else:
                j += 1
        if j == len(vs):
            raise EditError('editor_error', 'Missing lemma body')
        end = group_end(vs, j)
        # All restrictions from the old proof guard apply; only this top-level fn is exempt.
        fragment = text[ts[i][1]:ts[end - 1][2]]
        fn_offset = ts[i + 1][1] - ts[i][1]
        validate_statements(fragment[:fn_offset] + 'lemma_definition' + fragment[fn_offset + 2:])
        i = end
    if not names:
        raise EditError('no_effect', 'Empty lemma insertion')


def apply(code, response, offered=None):
    from localized_sft.editor import parse, overlap
    sites = regions(code) if offered is None else offered
    action = parse(response) if isinstance(response, str) else parse(json.dumps(response))
    lookup = {s['id']: s for s in sites}
    chosen, body, helpers = [], [], []
    for e in action['edits']:
        if not isinstance(e, dict) or set(e) != {'site_id', 'replacement'} or not isinstance(e['site_id'], str) or not isinstance(e['replacement'], str):
            raise EditError('json_error', 'Expected site_id/replacement strings')
        if e['site_id'] not in lookup:
            raise EditError('editor_error', 'Unknown site')
        s = lookup[e['site_id']]
        if any(s['id'] == t['id'] or overlap(s, t) for t in chosen):
            raise EditError('editor_error', 'Repeated or overlapping sites')
        chosen.append(s)
        if s['kind'] == 'lemma_definitions':
            validate_lemmas(e['replacement'], code)
            helpers.append((s, e['replacement']))
        else:
            body.append(e)
    # Validate all ordinary edits atomically against original positions.
    if body:
        body_apply(code, {'edits': body}, sites)
    result = code
    edits = [(lookup[e['site_id']], e['replacement']) for e in body] + helpers
    for s, replacement in sorted(edits, key=lambda pair: pair[0]['start'], reverse=True):
        result = result[:s['start']] + replacement.rstrip() + '\n' + result[s['end']:]
    if tokens(result) == tokens(code):
        raise EditError('no_effect', 'No effective token change')
    return result


def classify(site, replacement, source):
    if site['kind'] == 'loop_invariants':
        return 'loop_invariants'
    if site['kind'] == 'lemma_definitions':
        return 'lemmas'
    values = tokens(replacement)
    if 'assert' in values:
        return 'assertions_and_proof'
    source_values = tokens(source)
    names = {source_values[i + 2] for i in range(len(source_values) - 2) if source_values[i:i + 2] == ['proof', 'fn']}
    if any(v in names or v.startswith('lemma_') for v in values):
        return 'lemmas'
    raise EditError('unsupported_action', 'No assertion or identifiable lemma call in this proof edit')
