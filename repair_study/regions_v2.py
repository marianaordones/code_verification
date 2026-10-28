"""Conservative body-only sites; legacy editor and old experiments stay unchanged."""
import re

from baseline.integrity import group_end
from .regions import spans, regions as legacy_regions, apply_patch

IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
CONTRACT = {'requires', 'ensures', 'recommends', 'decreases', 'opens_invariants'}
CONTINUATION = {',', ';', '=', '+', '-', '*', '/', '%', '&', '|', '.', ')', ']'}


def regions(source):
    ts = spans(source)
    vs = [t[0] for t in ts]
    if not vs:
        return []
    ends, parents, depths, stack = {}, {}, {}, []
    # Strings/comments are already atomic or skipped by the existing lexer.
    for i, token in enumerate(vs):
        parents[i] = next((j for j in reversed(stack) if vs[j] == '{'), None)
        depths[i] = sum(vs[j] in ('(', '[') for j in stack)
        if token in ('{', '(', '['):
            stack.append(i)
        elif token in ('}', ')', ']'):
            if not stack or {'{': '}', '(': ')', '[': ']'}[vs[stack[-1]]] != token:
                raise ValueError('Unbalanced delimiters')
            ends[stack.pop()] = i + 1
    if stack:
        raise ValueError('Unclosed delimiter')

    def own_line(i):
        return not source[source.rfind('\n', 0, ts[i][1]) + 1:ts[i][1]].strip()

    def find_body(start, header=False):
        j = start
        while j < len(vs):
            if vs[j] in ('(', '['):
                j = ends[j]
                continue
            if vs[j] in (';', '}'):
                return None
            if vs[j] == '{':
                after = ends[j]
                # Braced expressions/closures in contracts/conditions are not bodies.
                if after < len(vs) and (vs[after] in CONTINUATION or vs[after] in CONTRACT or header and vs[after] in ('else', '{')):
                    j = after
                    continue
                if header and any(t in CONTRACT for t in vs[start:j]) and not own_line(j):
                    return None  # Ambiguous inline contract: omit rather than guess.
                return j
            j += 1
        return None

    bodies, headers = [], []
    for i, token in enumerate(vs):
        if token != 'fn' or i + 1 >= len(vs) or not IDENTIFIER.fullmatch(vs[i + 1]):
            continue
        params = next((j for j in range(i + 2, len(vs)) if vs[j] in ('(', ';', '{')), None)
        if params is None or vs[params] != '(':
            continue
        body = find_body(ends[params], header=True)
        if body is None:
            continue
        previous = i - 1
        while previous >= 0 and vs[previous] not in (';', '{', '}'):
            previous -= 1
        if 'spec' not in vs[previous + 1:i]:
            bodies.append(body)
        headers.append((i, body))

    def in_body(i):
        return any(b < i < ends[b] - 1 for b in bodies)

    known = set(bodies)
    statement_ends = set()
    loop_headers = []
    # Only classify control blocks in an already-known statement block. Never
    # descend into a closure, struct literal, match pattern, or contract block.
    for i, token in enumerate(vs):
        if not in_body(i) or parents[i] not in known or depths[i]:
            continue
        if any(a <= i < b for a, b in loop_headers):
            continue
        if token in ('if', 'while', 'for', 'loop'):
            body = find_body(i + 1, header=token in ('while', 'for'))
            if body is not None:
                known.add(body)
                if token in ('while', 'for'):
                    loop_headers.append((i, body))
        elif token == 'match':
            body = find_body(i + 1)
            if body is not None:
                statement_ends.add(ends[body] - 1)  # Allow a following statement, not match patterns.
        elif token == 'else' and i + 1 < len(vs) and vs[i + 1] == '{':
            known.add(i + 1)
        elif token == 'proof' and i + 1 < len(vs) and vs[i + 1] == '{':
            known.add(i + 1)

    def blocked(i):
        return any(a <= i < b for a, b in headers + loop_headers)

    legacy = legacy_regions(source)
    sites = []
    for site in legacy:
        if site['kind'] == 'insert_proof':
            continue
        i = next((i for i, t in enumerate(ts) if t[1] == site['start']), None)
        if i is None or not in_body(i):
            continue
        # Loop invariant lists deliberately lie in the loop annotation header.
        if site['kind'] == 'proof_block' and (blocked(i) or parents[i] not in known):
            continue
        if site['kind'] == 'loop_invariants' and parents[i] not in known:
            continue
        sites.append(dict(site))

    end_to_open = {end - 1: start for start, end in ends.items()}
    for i, (token, start, _) in enumerate(ts):
        if not in_body(i) or parents[i] not in known or depths[i] or blocked(i) or not own_line(i):
            continue
        if (not IDENTIFIER.fullmatch(token) and not token[0].isdigit() and not token.startswith(('"', '\''))) or token in ('else', 'as', 'invariant', 'invariant_except_break', 'invariant_ensures', 'decreases', 'requires', 'ensures'):
            continue
        previous = i - 1
        at_start = previous == parents[i]
        after_semicolon = previous >= 0 and vs[previous] == ';'
        after_block = previous >= 0 and vs[previous] == '}' and (end_to_open.get(previous) in known or previous in statement_ends)
        if not (at_start or after_semicolon or after_block):
            continue
        if any(s['start'] <= start < s['end'] for s in sites):
            continue
        # Includes tail expressions such as arr[i], max, f(x), &x, and if ... .
        sites.append({'kind': 'insert_proof', 'start': start, 'end': start,
                      'line': source.count('\n', 0, start) + 1, 'existing_text': ''})
    sites.sort(key=lambda s: (s['start'], s['end'], s['kind']))
    for i, site in enumerate(sites):
        site['id'] = f'R{i + 1}'
    return sites
