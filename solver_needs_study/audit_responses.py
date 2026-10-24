"""Offline application of saved responses, never a counterfactual model trajectory."""
import argparse
from pathlib import Path

from baseline.storage import digest, read_json, write_json, write_text
from .actions import RESPONSE_POLICY, parse_response, render
from .feedback import ARMS
from .verify import StudyVerifier


def audit(study, output, verifier=None):
    study, output = Path(study).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(study) or study.is_relative_to(output):
        raise ValueError('Use a NEW audit directory outside the original study')
    manifest = read_json(study / 'manifest.json')
    # Intentionally do not compare old implementation hashes: the purpose is to
    # audit old responses under a new parser. Frozen experimental inputs must match.
    for name, expected in manifest['files'].items():
        if digest((study / name).read_bytes()) != expected:
            raise ValueError('Original frozen input changed: ' + name)
    if verifier is None:
        from .__main__ import tools
        from baseline.provenance import tool_signature
        identities = tools()
        if {k: tool_signature(v) for k, v in identities.items()} != manifest['tool_hashes']:
            raise ValueError('Audit requires the original verifier and Z3 identities')
        verifier = StudyVerifier(identities['verus']['path'], identities['z3']['path'],
                                 manifest['config']['verification_timeout'])
    output.mkdir(parents=True)
    rows, verified = [], {}
    report = {'policy': RESPONSE_POLICY, 'source_study': str(study),
              'source_manifest_sha256': digest((study / 'manifest.json').read_bytes()),
              'scope': 'offline reapplication of saved responses; NOT rerun trajectories or replacement scores',
              'model_calls': 0, 'complete': False, 'responses': rows}
    write_json(output / 'report.json', report)
    for case in manifest['cases']:
        task = read_json(study / 'inputs' / case['id'] / 'task.json')
        for arm in ARMS:
            for folder in sorted((study / arm / case['id']).glob('attempt_*')):
                if not (folder / 'response.json').exists():
                    continue
                original = read_json(folder / 'result.json') if (folder / 'result.json').exists() else {}
                response = read_json(folder / 'response.json')
                destination = output / arm / case['id'] / folder.name
                info = {'policy': RESPONSE_POLICY}
                row = {'id': case['id'], 'arm': arm, 'attempt': folder.name,
                       'response_sha256': digest((folder / 'response.json').read_bytes()),
                       'original_success': original.get('success'),
                       'original_edit_error': original.get('edit_error'),
                       'format': info, 'accepted_action': False, 'audit_verifies': None}
                try:
                    action = parse_response(response['text'], metadata=info)
                    code = render(task, action)
                except (ValueError, KeyError, TypeError) as error:
                    row['parse_error'] = str(error)
                else:
                    row['accepted_action'] = True
                    row['candidate_sha256'] = digest(code.encode())
                    row['nla'] = action['nla']
                    write_json(destination / 'action.json', action)
                    write_text(destination / 'candidate.rs', code)
                    key = (row['candidate_sha256'], action['nla'])
                    if key in verified:
                        checked, first = verified[key]
                        row['verification_reused_from'] = first
                    else:
                        checked = verifier.verify(destination / 'candidate.rs', nla=action['nla'], capture=False)
                        verified[key] = checked, str(destination.relative_to(output))
                    write_json(destination / 'verification.json', checked)
                    row['audit_verifies'] = checked['success'] if checked['error_type'] != 'verifier_error' else None
                    row['error_type'] = checked['error_type']
                rows.append(row)
                write_json(destination / 'audit.json', row)
                write_json(output / 'report.json', report)
                print(arm, case['id'], folder.name, 'accepted=', row['accepted_action'],
                      'verifies=', row['audit_verifies'], flush=True)
    report['complete'] = True
    report['unique_verifications'] = len(verified)
    write_json(output / 'report.json', report)
    write_text(output / 'README.txt',
               'Offline audit only. Original requests, responses and scores were not modified.\n'
               'Do not interpret this as trajectories under the new extraction policy.\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.study, args.output)
    print('Saved responses:', len(report['responses']), '; unique verifications:', report['unique_verifications'])


if __name__ == '__main__':
    main()
