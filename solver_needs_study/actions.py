"""Only one proof slot, one checked catalogue law, and the NLA toggle are editable."""
import json
import re

from baseline.integrity import group_end, tokens
from .data import LABELS, upstream

FORBIDDEN = {'assume', 'admit', 'axiom', 'external', 'external_body', 'unsafe',
             'fn', 'mod', 'use', 'impl', 'trait', 'struct', 'enum', 'macro_rules',
             'return', 'break', 'continue', 'static', 'const', 'exec', 'loop', 'while', 'for'}

RESPONSE_POLICY = 'single-json-action-v2'


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON field: ' + key)
        value[key] = item
    return value


def extract_response(text):
    """Select one JSON payload; never fix JSON or choose among multiple blocks."""
    text = text.strip().replace('\r\n', '\n')
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
        return value, {'policy': RESPONSE_POLICY, 'strict_json': True, 'extraction': 'direct_json'}
    except json.JSONDecodeError:
        pass
    fences = list(re.finditer(r'^[ \t]*(?:`{3,}|~{3,})[^\r\n]*$', text, re.MULTILINE))
    if len(fences) != 2:
        raise ValueError('Expected direct JSON or exactly one JSON fenced block')
    opening, closing = fences
    label = opening.group().strip()
    if label not in ('```json', '```') or closing.group().strip() != '```':
        raise ValueError('Expected a json fenced block (or a standalone unlabelled block)')
    before, after = text[:opening.start()].strip(), text[closing.end():].strip()
    if label == '```' and (before or after):
        raise ValueError('Unlabelled fences must contain the entire response')
    if any(char in before + after for char in '{}'):
        raise ValueError('Ambiguous JSON/object content outside fenced action')
    payload = text[opening.end():closing.start()].strip()
    value = json.loads(payload, object_pairs_hook=_unique_object)
    return value, {'policy': RESPONSE_POLICY, 'strict_json': False,
                   'extraction': 'single_json_fence' if label == '```json' else 'standalone_unlabelled_fence',
                   'surrounding_prose': bool(before or after)}


def validate_statements(text):
    ts = tokens(text)
    if any(t in FORBIDDEN for t in ts):
        raise ValueError('Forbidden executable/trusted construct in proof slot')
    for i, t in enumerate(ts):
        if t == '#' and ts[i:i + 4] != ['#', '[', 'trigger', ']']:
            raise ValueError('Only #[trigger] annotations are allowed')
        if i + 2 < len(ts) and ts[i + 1] == '!' and ts[i + 2] in ('(', '[', '{') and t not in ('seq', 'set', 'map'):
            raise ValueError('Only collection literal macros are allowed')
    i = 0
    while i < len(ts):
        if ts[i] in ('(', '[', '{'):
            i = group_end(ts, i)
        elif ts[i] in (')', ']', '}'):
            raise ValueError('Unmatched closing delimiter')
        else:
            i += 1


def parse_response(text, *, metadata=None):
    value, info = extract_response(text)
    if metadata is not None:
        metadata.update(info)
    if not isinstance(value, dict) or set(value) != {'mechanism', 'statements', 'law', 'nla'}:
        raise ValueError('Expected exactly mechanism, statements, law, nla')
    if value['mechanism'] not in LABELS or not isinstance(value['statements'], str) or type(value['nla']) is not bool:
        raise ValueError('Invalid response field type/value')
    _, laws = upstream()
    if value['law'] is not None and (not isinstance(value['law'], str) or value['law'] not in laws.LAWS):
        raise ValueError('Unknown law ID')
    validate_statements(value['statements'])
    return value


def render(task, action):
    statements = action['statements'].strip()
    validate_statements(statements)
    if statements:
        slot = '\n' + statements + '\n' if task['proof_context'] else 'proof {\n' + statements + '\n}'
    else:
        slot = '/* proof hint absent */'
    slot = '/* REPAIR_SLOT_BEGIN */' + slot + '/* REPAIR_SLOT_END */'
    code = task['prefix'] + slot + task['suffix']
    if action['law'] is not None:
        _, laws = upstream()
        if '__solver_needs_law' in code:
            raise ValueError('Reserved law module name collides with source')
        head = re.search(r'\bverus\s*!\s*\{', code)
        if not head:
            raise ValueError('No Verus module')
        code = code[:head.end()] + '\nbroadcast use __solver_needs_law::ax;\n' + code[head.end():]
        code += '\nmod __solver_needs_law { use vstd::prelude::*; verus! {\n' + laws.LAWS[action['law']] + '\n} }\n'
    return code


EMPTY = {'mechanism': 'Other', 'statements': '', 'law': None, 'nla': False}
