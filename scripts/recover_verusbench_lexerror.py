"""Finalize saved malformed-source attempts without model calls or hash bypasses.

Only recover the known Lynette input LexError, never arbitrary checker failures.
The study's frozen code, inputs and tools must still validate unchanged.
"""
import argparse
from pathlib import Path

from baseline.storage import read_json, write_json
from verusbench_study import __main__ as vb


def recover_attempt(root, folder, verifier):
    if (folder / 'result.json').exists():
        return False
    check = read_json(folder / 'integrity.json')
    if (check.get('status') != 'checker_error' or check.get('timed_out') or
            check.get('returncode') != 101 or
            'LexError' not in check.get('stderr', '') or
            'Result::unwrap()' not in check.get('stderr', '')):
        return False
    request = read_json(folder / 'request.json')
    response = read_json(folder / 'response.json')
    proposed, form = vb.extract_source(response['text'])
    candidate = (folder / 'candidate.rs').read_text(encoding='utf-8')
    if proposed != candidate:
        raise ValueError('Saved source differs from deterministic extraction; inspect manually')
    # Never remove prose, invent a new answer or accept an unchecked AST.
    result = verifier.verify(folder / 'candidate.rs')
    if result['error_type'] == 'verifier_error':
        raise RuntimeError('Verifier infrastructure failure; cannot finalize attempt')
    if result['success']:
        raise RuntimeError('Candidate verifies despite Lynette LexError; manual investigation required')
    original = folder / 'integrity-before-recovery.json'
    if original.exists() and read_json(original) != check:
        raise ValueError('Recovery backup differs; inspect manually')
    write_json(original, check)
    write_json(folder / 'verification.json', result)
    write_json(folder / 'integrity.json', {**check, 'status': 'unparseable', 'valid': False,
               'recovery': 'saved-source LexError confirmed by failed whole-file Verus; no model call'})
    record = {'attempt': int(folder.name.removeprefix('attempt_')), 'success': False,
              'edit_error': None, 'integrity_valid': False, 'error_type': result['error_type'],
              'extraction': form, 'internals_exposed': request['internals_exposed'],
              'recovery': 'Lynette LexError on malformed model output; original raw error preserved'}
    write_json(folder / 'result.json', record)
    return True


def recover(root):
    root = root.resolve()
    with vb.run_lock(root):
        manifest = vb.validate(root)
        runtime = vb.tools()
        if vb.identity(runtime) != manifest['tools']:
            raise ValueError('Study tools changed; cannot recover')
        verifier, _ = vb.verify_tools(runtime, manifest['config'])
        count = 0
        for task in manifest['selection']:
            for arm in vb.ARMS:
                for folder in sorted((root / arm / task['id']).glob('attempt_*')):
                    if (folder / 'integrity.json').exists() and recover_attempt(root, folder, verifier):
                        count += 1
                        print('Recovered invalid attempt:', folder, flush=True)
        print('Finalized invalid attempts:', count, '; model calls: 0')
        return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    recover(parser.parse_args().study)


if __name__ == '__main__':
    main()
