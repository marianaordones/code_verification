"""Recover one saved malformed proposal without invoking Claude or changing frozen code."""
import argparse
from pathlib import Path

from baseline.storage import digest, read_json, write_json
from scripts import run_sonnet46_new25_120s as batch

RELATIVE = Path('with_internals/misc_deduplicate/attempt_02')


def classify(integrity, verification):
    if not batch.study.known_input_parse_error(integrity):
        raise ValueError('Not the supported Lynette input parse error')
    if (verification.get('success') or verification.get('timed_out') or
            verification.get('returncode') != 1 or
            verification.get('error_type') not in ('syntax', 'compilation')):
        raise ValueError('No matching Verus compilation/syntax rejection')
    stderr = verification.get('stderr', '')
    if not any(marker in stderr for marker in ('unknown start of token', 'expected one of', 'expected item', 'expected expression')):
        raise ValueError('Unsupported compiler diagnostic; inspect manually')
    return {**integrity, 'valid': False, 'status': 'unparseable',
            'recovery': 'Known Lynette input parse error corroborated by Verus syntax/compilation rejection; proposal consumed'}


def recover(root, apply=False):
    root = Path(root).resolve()
    batch.validate(root)
    folder = root / RELATIVE
    if folder.resolve() != folder or folder.is_symlink():
        raise ValueError('Unexpected linked attempt')
    if (folder / 'result.json').exists():
        print('Result already exists; nothing changed.')
        return
    for name in ('candidate.rs', 'integrity.json', 'verification.json', 'request.json', 'response.json'):
        if (folder / name).is_symlink():
            raise ValueError('Unexpected linked artifact')
    integrity = read_json(folder / 'integrity.json')
    # If interrupted after updating integrity, resume from its preserved backup.
    backup = folder / 'integrity-before-syntax-recovery.json'
    original_integrity = read_json(backup) if backup.exists() else integrity
    verification = read_json(folder / 'verification.json')
    fixed = classify(original_integrity, verification)
    if integrity != original_integrity and integrity != fixed:
        raise ValueError('Integrity record changed unexpectedly')
    request, response = read_json(folder / 'request.json'), read_json(folder / 'response.json')
    if response.get('resource_exhausted'):
        raise ValueError('Resource stop; not this syntax recovery')
    source, form = batch.study.vb.extract_source(response['text'])
    if source != (folder / 'candidate.rs').read_text(encoding='utf-8'):
        raise ValueError('Saved candidate differs from original extracted response')
    common = root / 'shared/misc_deduplicate/attempt_01'
    if request['candidate_sha256'] != digest((common / 'candidate.rs').read_text(encoding='utf-8').encode()):
        raise ValueError('Shared starting candidate changed')
    record = {'attempt': 2, 'success': False, 'edit_error': None,
              'integrity_valid': False, 'error_type': verification['error_type'],
              'extraction': form, 'internals_exposed': request['internals_exposed']}
    print('Supported malformed proposal:', RELATIVE)
    print('Recovered result:', record)
    if apply:
        if not backup.exists():
            write_json(backup, original_integrity)
        write_json(folder / 'syntax-recovery.json', {
            'reason': 'Parser-label mismatch: syntax versus compilation; no new model request',
            'candidate_sha256': digest((folder / 'candidate.rs').read_bytes()),
            'response_sha256': digest((folder / 'response.json').read_bytes()),
            'verification_sha256': digest((folder / 'verification.json').read_bytes())})
        write_json(folder / 'integrity.json', fixed)
        write_json(folder / 'result.json', record)
        batch.summary(root)
        print('Applied. Response, candidate and verification preserved; no Claude requests.')
    else:
        print('Check only: no changes or Claude requests.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'apply'), nargs='?', default='check')
    parser.add_argument('--output', type=Path, default=batch.DEFAULT)
    args = parser.parse_args()
    with batch.study.vb.run_lock(args.output.resolve()):
        recover(args.output, args.command == 'apply')


if __name__ == '__main__':
    main()
