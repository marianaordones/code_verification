"""Deterministic ranking by identifiers and source failure operations, not semantics."""
import re


def qids(formula):
    return re.findall(r':qid\s+([^\s)]+)', formula)


def source_context(source, verification):
    lines = source.splitlines()
    text = verification.get('stderr', '') + '\n' + verification.get('stdout', '')
    errors = []
    current_error = ''
    for line in text.splitlines():
        if re.match(r'^error(?:\[|:)', line):
            current_error = line
        location = re.search(r'candidate\.rs:(\d+):(\d+)', line)
        if location and current_error:
            number = int(location[1])
            if 1 <= number <= len(lines):
                item = {'message': current_error, 'line': number, 'column': int(location[2]),
                        'expression_line': lines[number - 1],
                        'nearby_source': '\n'.join(f'{j + 1}: {lines[j]}'
                                                  for j in range(max(0, number - 4), min(len(lines), number + 3)))}
                if item not in errors:
                    errors.append(item)
    operation_text = '\n'.join(e['nearby_source'] for e in errors) or source
    families = []
    if '[' in operation_text or re.search(r'\.(?:set|push|len|subrange|index)\b', operation_text):
        families += ['vec', 'seq', 'index', 'len', 'update', 'subrange']
    if re.search(r'\b(?:forall|exists)\b', operation_text):
        families += ['quantifier']
    if re.search(r'[%/*+\-]', operation_text):
        families += ['arith', 'mul', 'add', 'sub', 'mod', 'div']
    return {'failures': errors[:4], 'operation_families': sorted(set(families)),
            'source_functions': re.findall(r'\b(?:spec\s+|proof\s+)?fn\s+(\w+)', source),
            'query_to_source_alignment': 'not established; failure locations come from Verus, not qid suffixes'}


def rank(formula, context):
    identifiers = qids(formula)
    name = ' '.join(identifiers).lower()
    if any(q.startswith('user_candidate') for q in identifiers):
        return 0, 'candidate_annotation'
    representation = any(word in name for word in ('box_axiom', 'unbox_axiom', 'raw_ptr', 'fuel', 'has_type'))
    if not representation and any('candidate' in q for q in identifiers):
        return 1, 'candidate_definition'
    if representation:
        return 4, 'representation'
    if any(word in name for word in context.get('operation_families', []) if word != 'quantifier'):
        return 2, 'operation_related_library'
    return 3, 'other_background'
