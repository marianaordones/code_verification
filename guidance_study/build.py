"""Select only archived initial failures with approved, three-action reference repairs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from baseline.integrity import tokens
from baseline.storage import write_json, write_text
from localized_sft.convert import action_for, sha
from .editor import apply, classify, regions


def build(archive, output):
    if output.exists():
        raise ValueError('Use a new output directory')
    output.mkdir(parents=True)
    tasks, audit = [], []
    with ZipFile(archive) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read('verusbench/manifest.json'))
        for task in manifest['tasks']:
            if task['status'] != 'eligible':
                continue
            key = task['id']
            if '/' in key or '\\' in key or key in ('.', '..'):
                raise ValueError('Unsafe task ID')
            prefix = f'verusbench/inputs/{key}/'
            for filename in ('candidate.rs', 'original.rs', 'verification.json'):
                raw = z.read(prefix + filename)
                expected = manifest['frozen_files']['inputs/' + key + '/' + filename]
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise ValueError('Frozen input hash mismatch: ' + key + '/' + filename)
            code = z.read(prefix + 'candidate.rs').decode('utf-8')
            verification = json.loads(z.read(prefix + 'verification.json'))
            if verification['success']:
                raise ValueError('Eligible input was already verified')
            offered = regions(code)
            choices, failures = [], []
            for arm in ('without_internals', 'with_internals'):
                for n in range(1, 4):
                    folder = f'verusbench/{arm}/{key}/proposal_{n:02d}/'
                    if folder + 'result.json' not in names:
                        continue
                    result = json.loads(z.read(folder + 'result.json'))
                    if not result['success']:
                        continue
                    try:
                        gate = json.loads(z.read(folder + 'integrity.json'))
                        verified = json.loads(z.read(folder + 'verification.json'))
                        if not result['accepted'] or gate['status'] != 'valid' or not verified['success']:
                            raise ValueError('Inconsistent successful reference evidence')
                        target = z.read(folder + 'candidate.rs').decode('utf-8')
                        action, old_sites = action_for(code, target)
                        old = {s['id']: s for s in old_sites}
                        mapped, decisions = [], []
                        for e in action['edits']:
                            s = old[e['site_id']]
                            if s['kind'] == 'loop_isolation_option':
                                raise ValueError('Reference requires loop_isolation option outside the three actions')
                            new = next(s2 for s2 in offered if (s2['kind'], s2['start'], s2['end']) == (s['kind'], s['start'], s['end']))
                            label = classify(new, e['replacement'], code)
                            mapped.append({'site_id': new['id'], 'replacement': e['replacement']})
                            decisions.append({'site_id': new['id'], 'action': label})
                        combined = {'edits': mapped}
                        if tokens(apply(code, combined, offered)) != tokens(target):
                            raise ValueError('Reference cannot be reproduced from initial input')
                        choices.append({'arm': arm, 'proposal': n, 'target': target, 'action': combined,
                            'decisions': decisions, 'folder': folder, 'verification': verified, 'integrity': gate})
                    except (ValueError, KeyError, StopIteration) as error:
                        failures.append({'arm': arm, 'proposal': n, 'reason': str(error)})
            if not choices:
                audit.append({'id': key, 'status': 'excluded', 'reasons': failures or ['No saved successful repair']})
                continue
            chosen = min(choices, key=lambda c: (len(c['decisions']), c['proposal'], c['arm']))
            folder = output / 'tasks' / key
            write_text(folder / 'candidate.rs', code)
            write_text(folder / 'original.rs', z.read(prefix + 'original.rs').decode('utf-8'))
            write_json(folder / 'verification.json', verification)
            write_json(folder / 'editable-sites.json', offered)
            # Reference and oracle metadata are privileged: never include the action/replacement in requests.
            private = folder / 'reference'
            write_text(private / 'candidate.rs', chosen['target'])
            write_json(private / 'action.json', chosen['action'])
            write_json(private / 'decisions.json', chosen['decisions'])
            write_json(private / 'verification.json', chosen['verification'])
            write_json(private / 'integrity.json', chosen['integrity'])
            tasks.append({'id': key, 'category': task['category'], 'source_reference': chosen['folder'],
                          'decisions': chosen['decisions']})
            audit.append({'id': key, 'status': 'selected', 'valid_references': len(choices), 'other_references': failures})
    files = {p.relative_to(output).as_posix(): sha(p) for p in output.rglob('*') if p.is_file()}
    counts = Counter(d['action'] for t in tasks for d in t['decisions'])
    result = {'schema': 'verusbench-oracle-guidance-v1', 'source_archive_sha256': sha(archive),
        'source_tools': manifest['tools'], 'tasks': tasks, 'files': files,
        'source_eligible': sum(t['status'] == 'eligible' for t in manifest['tasks']),
        'actions': dict(counts), 'audit': audit,
        'selection_bias': 'Selected because some saved run repaired them. Diagnostic subset, not representative VerusBench rate.',
        'reference_status': 'Archived Verus+integrity success and reproduced reference tokens; revalidate on cluster before inference.'}
    write_json(output / 'manifest.json', result)
    write_json(output / 'selected_ids.json', [t['id'] for t in tasks])
    write_text(output / 'report.md', '# Oracle action/location subset\n\nSelected: ' + str(len(tasks)) +
        '\n\nActions: ' + str(dict(counts)) + '\n\n' + result['selection_bias'] + '\n\n' + result['reference_status'] +
        '\n\nNo lemma repairs are claimed unless the action inventory contains lemmas.\n\n' +
        '\n'.join('- ' + t['id'] for t in tasks) + '\n')
    print('Selected', len(tasks), 'tasks;', dict(counts), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path('data/verusbench-guidance-v1'))
    args = p.parse_args()
    build(args.archive, args.output)


if __name__ == '__main__':
    main()
