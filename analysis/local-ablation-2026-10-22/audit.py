"""Audit saved ZIP artifacts only. Does not run inference, Verus or Z3."""
import argparse
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import statistics
import zipfile

from baseline.integrity import tokens


def audit(archive, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        base = next(n[:-len('comparison.json')] for n in z.namelist()
                    if n.endswith('/comparison.json') and 'localized-internals-ablation' in n)
        def read(name):
            return json.loads(z.read(base + name))
        manifest, comparison = read('manifest.json'), read('comparison.json')
        counts, differences, cases, successes = Counter(), [], [], []
        for name, expected in manifest['files'].items():
            assert hashlib.sha256(z.read(base + name)).hexdigest() == expected, name
            counts['frozen_input_hashes_checked'] += 1
        for case in manifest['cases']:
            task = case['id']
            initial = read(f'inputs/{task}/payload.json')
            available = initial['availability'] == 'available'
            annotations = any(q['selection_category'] == 'candidate_annotation' for q in initial.get('quantifiers', []))
            candidate_groups = any(q['selection_category'].startswith('candidate') for q in initial.get('quantifiers', []))
            counts['initial_annotation_cases'] += annotations
            counts['initial_any_candidate_group_cases'] += candidate_groups
            requests, responses, codes = [], [], []
            row = {'id': task, 'initial_available': available, 'initial_annotation': annotations}
            for arm in ('with_internals', 'without_internals'):
                folder = f'{arm}/{task}/repair_01/'
                requests.append(read(folder + 'request.json'))
                responses.append(read(folder + 'response.json')['text'])
                codes.append(z.read(base + folder + 'candidate.rs').decode())
                result = read(f'{arm}/{task}/task.json')
                row[arm] = result['success']
                if result['success']:
                    repair = next(a for a in result['repairs'] if a['success'])['repair']
                    folder = f'{arm}/{task}/repair_{repair:02}/'
                    assert read(folder + 'verification.json')['success']
                    assert read(folder + 'integrity.json')['valid']
                    payload = read(folder + 'payload-used.json')
                    successes.append({'id': task, 'arm': arm, 'repair': repair,
                        'internals_available': payload['availability'] == 'available'})
                    before = z.read(base + f'inputs/{task}/candidate.rs').decode()
                    after = z.read(base + folder + 'candidate.rs').decode()
                    dest = output / 'examples' / task / arm
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / 'before.rs').write_text(before, encoding='utf-8')
                    (dest / 'after.rs').write_text(after, encoding='utf-8')
                    (dest / 'change.diff').write_text(''.join(difflib.unified_diff(
                        before.splitlines(True), after.splitlines(True), fromfile='before.rs', tofile='after.rs')), encoding='utf-8')
                last = result['repairs'][-1]
                row[arm + '_final_error'] = last['error_type']
                if annotations:
                    counts[arm + '_success_on_initial_annotation_cases'] += result['success']
            a, b = requests
            expected = hashlib.sha256(z.read(base + f'inputs/{task}/candidate.rs')).hexdigest()
            assert a['candidate_sha256'] == b['candidate_sha256'] == expected
            assert a['seed'] == b['seed']
            assert a['parameters'] == b['parameters']
            assert a['offered_sites'] == b['offered_sites']
            assert a['messages'][0] == b['messages'][0]
            with_text, control = a['messages'][1]['content'], b['messages'][1]['content']
            assert '<solver_internals>' not in control
            if available:
                start = with_text.index('<solver_internals>')
                end = with_text.index('</solver_internals>') + len('</solver_internals>\n')
                assert with_text[:start] + with_text[end:] == control
            else:
                assert a['messages'] == b['messages']
            counts['actual_first_pairs_validated'] += 1
            label = 'available' if available else 'unavailable'
            counts[label + '_first_responses_identical'] += responses[0] == responses[1]
            counts[label + '_first_codes_identical'] += tokens(codes[0]) == tokens(codes[1])
            if not available and responses[0] != responses[1]:
                differences.append(task)
            cases.append(row)
        arms = {}
        for arm in ('with_internals', 'without_internals'):
            c, statuses, types, syntax, exposed = Counter(), Counter(), set(), set(), set()
            times, input_sizes, groups, instances = [], [], [], []
            for name in z.namelist():
                if not (name.startswith(base + arm + '/') and name.endswith('/result.json')):
                    continue
                folder = name[:-len('result.json')]
                result = json.loads(z.read(name))
                task = folder.split('/')[-3]
                payload = json.loads(z.read(folder + 'payload-used.json'))
                verification = json.loads(z.read(folder + 'verification.json'))
                check = json.loads(z.read(folder + 'integrity.json'))
                statuses[check['status']] += 1
                c['E0308_attempts'] += 'E0308' in verification['stderr']
                if 'E0308' in verification['stderr']:
                    types.add(task)
                if result['error_type'] == 'syntax':
                    syntax.add(task)
                available = payload['availability'] == 'available'
                c['exposed_unchanged'] += available and result['unchanged']
                if available:
                    exposed.add(task)
                    c['result_' + str(payload['original_result'])] += 1
                    c['reason_' + str(payload['reason_unknown'])] += 1
                    if payload['statistics'].get('time') is not None:
                        times.append(payload['statistics']['time'])
                groups.append(len(payload.get('quantifiers', [])))
                instances.append(sum(len(q['instances']) for q in payload.get('quantifiers', [])))
                input_sizes.append(result['input_tokens'])
            arms[arm] = {'counts': dict(c), 'integrity_statuses': dict(statuses),
                'E0308_problems': len(types), 'syntax_problems': len(syntax),
                'distinct_exposed_problems': len(exposed), 'max_input_tokens': max(input_sizes),
                'groups_total': sum(groups), 'groups_max': max(groups),
                'instances_total': sum(instances), 'instances_max': max(instances),
                'replay_time_min_median_max': [min(times), statistics.median(times), max(times)] if times else None}
        result = {'scope': 'saved artifacts only; no solver or inference execution',
                  'counts': dict(counts), 'identical_prompt_different_response_cases': differences,
                  'arms': arms, 'successes': successes, 'paired': cases,
                  'comparison': comparison}
        (output / 'audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps({'counts': dict(counts), 'arms': arms}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    audit(args.archive, args.output)
