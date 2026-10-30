"""SAFE-only attribute normalization; executable/contracts checks remain strict."""
import re

from baseline.integrity import IntegrityValidator, group_end, is_trigger_attribute, tokens
from baseline.storage import write_text
from baseline.verifier import Verifier
from repair_study.regions import spans

POLICY = 'safe-proof-attributes-v2'
LOOP_FALSE = ('#', '[', 'verifier', ':', ':', 'loop_isolation', '(', 'false', ')', ']')


def normalize(code):
    ts = spans(code)
    vs = [t[0] for t in ts]
    edits, ignored = [], []
    for i, value in enumerate(vs):
        if value != '#':
            continue
        start = i + 2 if vs[i + 1:i + 2] == ['!'] else i + 1
        if vs[start:start + 1] != ['[']:
            continue
        end = group_end(vs, start)
        item = tuple(vs[i:end])
        if item == LOOP_FALSE or is_trigger_attribute(item):
            edits.append((ts[i][1], ts[end - 1][2]))
            ignored.append({'attribute': ' '.join(item), 'start': ts[i][1], 'end': ts[end - 1][2]})
    for a, b in reversed(edits):
        code = code[:a] + code[b:]
    return code, ignored


def empty_loops(code):
    ts = tokens(code)
    return sum(ts[i:i + 3] == ['loop', '{', '}'] for i in range(len(ts) - 2))


def preservation(source, target, folder, lynette):
    try:
        original, before = normalize(source)
        candidate, after = normalize(target)
        # Explicit guard in addition to the normal AST executable comparison.
        if empty_loops(target) > empty_loops(source):
            return {'valid': False, 'status': 'invalid', 'policy': POLICY,
                    'reason': 'Added executable empty infinite loop; not a proof-only repair'}
        write_text(folder / 'preservation-input.rs', original)
        write_text(folder / 'preservation-copy.rs', candidate)
        result = IntegrityValidator(lynette).validate(folder / 'preservation-input.rs', folder / 'preservation-copy.rs')
        return {**result, 'policy': POLICY, 'ignored_attributes': {'input': before, 'target': after},
                'scope': 'only comparison copies normalized; actual input/target verified unchanged'}
    except (ValueError, IndexError) as error:
        return {'valid': False, 'status': 'unparseable', 'policy': POLICY, 'reason': str(error)}


def classify(result):
    value = Verifier.classify(result)
    headers = '\n'.join(line for line in (value['stdout'] + '\n' + value['stderr']).splitlines()
                        if re.match(r'^error(?:\[|:)', line))
    if not value['success'] and not value['timed_out']:
        if re.search(r'^error\[E\d+\]', headers, re.M):
            value['error_type'] = 'compilation'
        elif any(text in headers.lower() for text in ('expected expression', 'unexpected token', 'unclosed delimiter',
                                                       'expected one of', 'expected `')):
            value['error_type'] = 'syntax'
    return value


def eligibility(result, metadata):
    reasons = []
    if not result['target_success']:
        reasons.append('target_not_verified')
    if result['preservation_status'] != 'valid':
        reasons.append('preservation_' + result['preservation_status'])
    if metadata['target_tags']['assume_call'] is not False:
        reasons.append('target_assume_or_unresolved_lexing')
    if result.get('status') == 'input_already_verified':
        reasons.append('input_already_verified')
    return {'eligible': not reasons, 'reasons': reasons,
            'internals_available': result.get('status') == 'internals_available',
            'scope': 'validated positive SFT candidate; still requires family split/overlap and length checks'}
