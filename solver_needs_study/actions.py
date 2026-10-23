"""Only one proof slot, one checked catalogue law, and the NLA toggle are editable."""
import json
import re

from baseline.integrity import group_end, tokens
from .data import LABELS, upstream

FORBIDDEN = {'assume', 'admit', 'axiom', 'external', 'external_body', 'unsafe',
             'fn', 'mod', 'use', 'impl', 'trait', 'struct', 'enum', 'macro_rules',
             'return', 'break', 'continue', 'static', 'const', 'exec', 'loop', 'while', 'for'}


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


def parse_response(text):
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    value = json.loads(text)
    if set(value) != {'mechanism', 'statements', 'law', 'nla'}:
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
