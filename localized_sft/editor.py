"""Atomic multi-site edits. Sites depend only on the input candidate."""
import json

from baseline.integrity import FORBIDDEN as TRUSTED_BYPASSES, group_end, is_trigger_attribute, tokens
from repair_study.regions import spans
from repair_study.regions_v2 import regions as body_regions
from solver_needs_study.actions import FORBIDDEN as SLOT_FORBIDDEN

FORMAT = 'safe-multiedit-v1'
LOOP_ATTRIBUTE = '#[verifier::loop_isolation(false)]'


class EditError(ValueError):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category


def validate_statements(text):
    values = tokens(text)
    if any(v in TRUSTED_BYPASSES | SLOT_FORBIDDEN for v in values):
        raise ValueError('Forbidden executable/trusted construct in proof edit')
    for i, value in enumerate(values):
        if value == '#':
            start = i + 2 if values[i + 1:i + 2] == ['!'] else i + 1
            if values[start:start + 1] != ['[']:
                raise ValueError('Only checked trigger annotations are allowed')
            end = group_end(values, start)
            if not is_trigger_attribute(tuple(values[i:end])):
                raise ValueError('Only checked trigger annotations are allowed')
        if i + 2 < len(values) and values[i + 1] == '!' and values[i + 2] in ('(', '[', '{') and value not in ('seq', 'set', 'map', '#'):
            raise ValueError('Only collection literal macros are allowed')
    i = 0
    while i < len(values):
        if values[i] in ('(', '[', '{'):
            i = group_end(values, i)
        elif values[i] in (')', ']', '}'):
            raise ValueError('Unmatched closing delimiter')
        else:
            i += 1


def regions(code):
    sites = body_regions(code)
    ts = spans(code)
    vs = [t[0] for t in ts]
    ends = {}
    for i, value in enumerate(vs):
        if value in ('(', '[', '{'):
            ends[group_end(vs, i) - 1] = i
    # A narrowly typed option region, never arbitrary header editing.
    for i, value in enumerate(vs):
        if value != 'fn':
            continue
        j, attributes = i - 1, []
        while j >= 0:
            if vs[j] in ('pub', 'proof', 'exec', 'spec', 'open', 'closed', 'async', 'unsafe'):
                j -= 1
            elif vs[j] == ')' and vs[ends[j] - 1:ends[j]] == ['pub']:
                j = ends[j] - 2
            elif vs[j] == ']' and vs[max(0, ends[j] - 1):ends[j]] == ['#']:
                start = ends[j] - 1
                attributes.append((start, j))
                j = start - 1
            else:
                break
        if 'spec' in vs[j + 1:i]:
            continue
        matches = [(a, b) for a, b in attributes if vs[a:b + 1] == tokens(LOOP_ATTRIBUTE)]
        if len(matches) > 1:
            continue  # Ambiguous duplicate options are not guessed.
        if matches:
            a, b = matches[0]
            start, end = ts[a][1], ts[b][2]
        else:
            start = end = ts[j + 1][1]
        sites.append({'kind': 'loop_isolation_option', 'start': start, 'end': end,
                      'line': code.count('\n', 0, start) + 1, 'existing_text': code[start:end]})
    unique = {(s['start'], s['end'], s['kind']): s for s in sites}
    sites = sorted(unique.values(), key=lambda s: (s['start'], s['end'], s['kind']))
    for i, site in enumerate(sites):
        site['id'] = f'R{i + 1}'
    return sites


def overlap(a, b):
    x, y, u, v = a['start'], a['end'], b['start'], b['end']
    if x == y and u == v:
        return x == u
    if x == y:
        return u <= x < v
    if u == v:
        return x <= u < y
    return max(x, u) < min(y, v)


def _object(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise EditError('json_error', 'Duplicate JSON key: ' + k)
        obj[k] = v
    return obj


def parse(text):
    text = text.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if len(lines) < 3 or lines[0] not in ('```', '```json') or lines[-1] != '```':
            raise EditError('json_error', 'Expected one complete JSON fence')
        text = '\n'.join(lines[1:-1])
    try:
        obj = json.loads(text, object_pairs_hook=_object)
    except json.JSONDecodeError as error:
        raise EditError('json_error', str(error)) from error
    if not isinstance(obj, dict) or set(obj) != {'edits'} or not isinstance(obj['edits'], list):
        raise EditError('json_error', 'Expected exactly an edits array')
    if not obj['edits']:
        raise EditError('no_effect', 'Empty edits array')
    return obj


def apply(code, action, offered=None):
    offered = regions(code) if offered is None else offered
    if isinstance(action, str):
        action = parse(action)
    # Revalidate dictionaries too; no trusted conversion-only bypass.
    action = parse(json.dumps(action))
    lookup = {s['id']: s for s in offered}
    selected, ids = [], set()
    for edit in action['edits']:
        if not isinstance(edit, dict) or set(edit) != {'site_id', 'replacement'}:
            raise EditError('json_error', 'Each edit must have site_id and replacement')
        key, value = edit['site_id'], edit['replacement']
        if not isinstance(key, str) or not isinstance(value, str):
            raise EditError('json_error', 'Edit fields must be strings')
        if key in ids:
            raise EditError('editor_error', 'Repeated site: ' + key)
        ids.add(key)
        if key not in lookup:
            raise EditError('editor_error', 'Unknown site: ' + key)
        site = lookup[key]
        if site['existing_text'] != code[site['start']:site['end']]:
            raise EditError('editor_error', 'Stale region: ' + key)
        try:
            values = tokens(value)
            if site['kind'] != 'loop_isolation_option':
                try:
                    validate_statements(value)
                except ValueError as error:
                    category = 'forbidden_edit' if any(s in str(error) for s in ('Forbidden', 'Only checked', 'Only collection')) else 'editor_error'
                    raise EditError(category, str(error)) from error
            if site['kind'] == 'loop_isolation_option':
                if values not in ([], tokens(LOOP_ATTRIBUTE)):
                    raise EditError('editor_error', 'Only loop_isolation(false) or its removal is allowed')
            elif site['kind'] == 'loop_invariants':
                if values and (values[0] != 'invariant' or any(t in values for t in ('while', 'fn', 'decreases'))):
                    raise EditError('editor_error', 'Expected only the complete invariant list')
            elif site['kind'] == 'insert_proof' and values[:2] != ['proof', '{']:
                if not values:
                    raise EditError('no_effect', 'Empty insertion')
                validate_statements(value)
            elif site['kind'] == 'proof_block' and not values:
                pass  # Removing an existing proof block still requires the gate and Verus.
            elif not (values[:2] == ['proof', '{'] and group_end(values, 1) == len(values)):
                raise EditError('editor_error', 'Expected exactly one proof block')
            if values == tokens(site['existing_text']):
                raise EditError('no_effect', 'Unchanged region: ' + key)
        except EditError:
            raise
        except (ValueError, IndexError) as error:
            raise EditError('editor_error', str(error)) from error
        if any(overlap(site, old) for old, _ in selected):
            raise EditError('editor_error', 'Overlapping regions')
        selected.append((site, value))
    result = code
    for site, value in sorted(selected, key=lambda p: p[0]['start'], reverse=True):
        result = result[:site['start']] + value.rstrip() + '\n' + result[site['end']:]
    if tokens(result) == tokens(code):
        raise EditError('no_effect', 'No effective token change')
    return result
