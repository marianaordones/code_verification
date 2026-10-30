"""Deterministic harness-only loop-isolation setting; no global policy relaxation."""
import re
from baseline.integrity import group_end
from repair_study.regions import spans

ATTRIBUTE = '#[verifier::loop_isolation(false)]'
MODES = {'pub', 'proof', 'exec', 'spec', 'open', 'closed', 'broadcast', 'unsafe', 'async', 'const', 'default'}


def force_false(code):
    ts = spans(code)
    vs = [t[0] for t in ts]
    edits, attributes, reverse = [], [], {}
    for i, token in enumerate(vs):
        if token in ('(', '[', '{'):
            reverse[group_end(vs, i) - 1] = i
        if token != '#':
            continue
        start = i + 2 if vs[i + 1:i + 2] == ['!'] else i + 1
        if vs[start:start + 1] != ['[']:
            continue
        end = group_end(vs, start)
        item = vs[start + 1:end - 1]
        if 'loop_isolation' not in item:
            continue
        if len(item) != 7 or item[:5] != ['verifier', ':', ':', 'loop_isolation', '('] or item[-1] != ')' or item[5] not in ('true', 'false'):
            raise ValueError('Unsupported loop_isolation attribute; no silent normalization')
        attributes.append((i, end))
        if item[5] == 'true':
            t = ts[start + 6]
            edits.append((t[1], t[2], 'false'))
    macros = [(i + 2, group_end(vs, i + 2)) for i in range(len(vs) - 2)
              if vs[i:i + 3] == ['verus', '!', '{']]
    functions = []
    for i, token in enumerate(vs):
        if token != 'fn' or i + 1 >= len(vs) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', vs[i + 1]):
            continue
        if not any(a < i < b for a, b in macros):
            continue
        j = i
        while j:
            if vs[j - 1] in MODES:
                j -= 1
            elif vs[j - 1] == ')' and j - 1 in reverse and reverse[j - 1] and vs[reverse[j - 1] - 1] == 'pub':
                j = reverse[j - 1] - 1
            elif vs[j - 1] == ']' and j - 1 in reverse:
                start = reverse[j - 1]
                if start and vs[start - 1] == '#':
                    j = start - 1
                elif start > 1 and vs[start - 2:start] == ['#', '!']:
                    j = start - 2
                else:
                    break
            else:
                break
        # Spec functions have no imperative loop body; leave them alone.
        if 'spec' in vs[j:i]:
            continue
        functions.append(vs[i + 1])
        if not any(j <= a < b <= i for a, b in attributes):
            edits.append((ts[j][1], ts[j][1], ATTRIBUTE + '\n'))
    changed = code
    for start, end, text in sorted(edits, reverse=True):
        changed = changed[:start] + text + changed[end:]
    return changed, {'functions': functions, 'changes': [{'start': a, 'end': b, 'text': t} for a, b, t in edits],
                     'policy': 'fixed harness option; all other preservation rules unchanged'}
