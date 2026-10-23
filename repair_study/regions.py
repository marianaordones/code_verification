"""Conservative text regions; final Verus and Lynette checks remain mandatory."""
import json
import re

from baseline.integrity import group_end, tokens


def spans(source):
    """Use the existing lexer and locate tokens after skipping comments safely."""
    result, pos = [], 0
    for token in tokens(source):
        while pos < len(source):
            if source[pos].isspace():
                pos += 1
            elif source.startswith('//', pos):
                end = source.find('\n', pos)
                pos = len(source) if end < 0 else end + 1
            elif source.startswith('/*', pos):
                depth, pos = 1, pos + 2
                while depth and pos < len(source):
                    if source.startswith('/*', pos):
                        depth, pos = depth + 1, pos + 2
                    elif source.startswith('*/', pos):
                        depth, pos = depth - 1, pos + 2
                    else:
                        pos += 1
            else:
                break
        if not source.startswith(token, pos):
            raise ValueError('Cannot locate source token safely')
        result.append((token, pos, pos + len(token)))
        pos += len(token)
    return result


def regions(source):
    """Offer invariant replacement, proof-block replacement, and proof insertion."""
    ts = spans(source)
    values = [t[0] for t in ts]
    sites = []

    def add(kind, start, end):
        sites.append({'id': f'R{len(sites) + 1}', 'kind': kind, 'start': start, 'end': end,
                      'line': source.count('\n', 0, start) + 1,
                      'existing_text': source[start:end]})

    for i, token in enumerate(values):
        if token == 'proof' and values[i + 1:i + 2] == ['{']:
            end = group_end(values, i + 1)
            add('proof_block', ts[i][1], ts[end - 1][2])
        if token != 'while':
            continue
        # Skip nested parenthesized/bracketed expressions. A brace on a line
        # containing an invariant/if expression is deliberately not guessed.
        j, inv, measure, unsafe = i + 1, None, None, False
        while j < len(ts):
            value = values[j]
            if value in ('(', '['):
                j = group_end(values, j)
                continue
            if value == 'if':
                unsafe = True
            if value == 'invariant' and inv is None:
                inv = j
            if value == 'decreases' and measure is None:
                measure = j
            if value == '{':
                prefix = source[source.rfind('\n', 0, ts[j][1]) + 1:ts[j][1]]
                # Do not confuse a block-valued invariant expression with the loop body.
                if not unsafe and (inv is None or not prefix.strip()):
                    stop = measure if measure is not None else j
                    add('loop_invariants', ts[inv][1] if inv is not None else ts[stop][1], ts[stop][1])
                break
            if value in (';', '}'):
                break
            j += 1
    # Insert only a single proof block before an existing statement, never replace it.
    for i, (token, start, _) in enumerate(ts):
        line_start = source.rfind('\n', 0, start) + 1
        if source[line_start:start].strip():
            continue
        statement = token in ('let', 'return', 'assert') or (
            re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', token) and values[i + 1:i + 2] == ['.'])
        if statement and not any(s['start'] <= start < s['end'] for s in sites):
            add('insert_proof', start, start)
    return sites


def apply_patch(source, text, offered):
    text = text.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines[-1] != '```':
            raise ValueError('Unclosed JSON fence')
        text = '\n'.join(lines[1:-1])
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {'site_id', 'replacement'}:
        raise ValueError('Return exactly site_id and replacement')
    site = next((s for s in offered if s['id'] == value['site_id']), None)
    replacement = value['replacement']
    if site is None or not isinstance(replacement, str) or not replacement.strip():
        raise ValueError('Unknown site or empty replacement')
    ts = tokens(replacement)
    if site['kind'] == 'loop_invariants':
        if not ts or ts[0] != 'invariant':
            raise ValueError('Invariant replacement must start with invariant')
        if 'while' in ts or 'fn' in ts or 'decreases' in ts:
            raise ValueError('Only replace the invariant list')
    elif not (ts[:2] == ['proof', '{'] and group_end(ts, 1) == len(ts)):
        raise ValueError('Replacement must be exactly one proof block')
    result = source[:site['start']] + replacement.rstrip() + '\n' + source[site['end']:]
    if tokens(result) == tokens(source):
        raise ValueError('No effective token change')
    return result, site['id']
