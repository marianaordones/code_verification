"""Resume only incomplete tasks of the frozen 50-task Sonnet 4.6 study.

An orphaned CLI receipt never grants permission for an automatic resubmission.
Use --retry-interrupted to authorize retrying startup receipts without a saved
response or nonempty stdout. All original request bytes remain in place.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys
import uuid

from baseline.storage import digest, read_json, write_json
from verusbench_sonnet46 import __main__ as study


def pending_tasks(root, manifest):
    pending = []
    for index, task in enumerate(manifest['selection']):
        path = root / 'shared' / task['id'] / 'task.json'
        shared = read_json(path) if path.exists() else None
        if shared and (shared.get('initially_verified') or shared.get('success')):
            continue
        if shared and all((root / arm / task['id'] / 'task.json').exists() for arm in study.vb.ARMS):
            continue
        pending.append((index, task))
    return pending


def interrupted_calls(root, pending):
    found = []
    for _, task in pending:
        for arm in ('shared', *study.vb.ARMS):
            for folder in sorted((root / arm / task['id']).glob('attempt_*')):
                receipt = folder / 'claude-call.json'
                if not receipt.exists() or (folder / 'response.json').exists() or (folder / 'result.json').exists():
                    continue
                call = read_json(receipt)
                if call.get('state') == 'completed' and call.get('returncode') == 0:
                    # Existing transport will parse its saved stream, without a call.
                    continue
                found.append(folder)
    return found


def archive_interrupted(root, folders, authorized=False):
    if folders and not authorized:
        raise RuntimeError('Unfinished CLI call found. Inspect it, then use --retry-interrupted to explicitly authorize resubmission')
    root = root.resolve()
    # Validate every path before performing any mutation.
    for folder in folders:
        folder = folder.resolve()
        if not folder.is_relative_to(root):
            raise ValueError('Attempt is outside the study')
        if (folder / 'response.json').exists() or (folder / 'result.json').exists():
            raise ValueError('Response/result appeared; inspect instead of resubmitting')
        raw = folder / 'claude-stdout.jsonl'
        if raw.exists() and raw.read_text(encoding='utf-8').strip():
            raise RuntimeError('Nonempty raw stdout exists; recover/inspect the response before authorizing another call: ' + str(folder))
        if not (folder / 'request.json').is_file():
            raise ValueError('Missing original request')
        for name in ('claude-call.json', 'claude-stdout.jsonl', 'claude-stderr.txt'):
            p = folder / name
            if p.is_symlink() or (p.exists() and p.resolve().parent != folder):
                raise ValueError('Unexpected linked call artifact')
        base = folder / 'interrupted-calls'
        if base.exists() and not base.resolve().is_relative_to(folder):
            raise ValueError('Unexpected archive path')
    records = []
    for folder in folders:
        folder = folder.resolve()
        before = read_json(folder / 'claude-call.json')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        archive = folder / 'interrupted-calls' / stamp
        archive.mkdir(parents=True, exist_ok=False)
        for name in ('claude-call.json', 'claude-stdout.jsonl', 'claude-stderr.txt'):
            p = folder / name
            if p.exists():
                p.rename(archive / name)
        record = {'attempt': str(folder.relative_to(root)), 'previous_call': before,
                  'original_request_sha256': digest((folder / 'request.json').read_bytes()),
                  'retry_explicitly_authorized': True, 'prior_usage_unknown': True,
                  'archive': str(archive.relative_to(root))}
        write_json(archive / 'retry-authorization.json', record)
        records.append(record)
    return records


def provenance():
    return {'cli': study.preflight(), 'python': sys.version,
            'versions': {p: importlib.metadata.version(p) for p in ('transformers', 'tokenizers', 'z3-solver')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'run'), nargs='?', default='check')
    parser.add_argument('--study', type=Path, default=study.DEFAULT)
    parser.add_argument('--retry-interrupted', action='store_true')
    args = parser.parse_args()
    root = args.study.resolve()
    # Same lock as the original runner: never launch alongside it.
    with study.vb.run_lock(root):
        manifest = study.validate(root)
        pending = pending_tasks(root, manifest)
        folders = interrupted_calls(root, pending)
        print(f"Completed tasks: {len(manifest['selection']) - len(pending)}; pending: {len(pending)}", flush=True)
        for _, task in pending:
            print('Pending:', task['id'], flush=True)
        for folder in folders:
            print('Interrupted call:', folder.relative_to(root), flush=True)
        if args.command == 'check':
            print('Check only: no archives changed, no model calls.')
            return 0
        if not pending:
            study.compare(root)
            return 0
        runtime = study.vb.tools()
        if study.vb.identity(runtime) != manifest['tools']:
            raise ValueError('Toolchain changed; cannot resume the frozen study')
        current = provenance()
        if (root / 'runtime.json').exists() and read_json(root / 'runtime.json') != current:
            raise ValueError('CLI/runtime changed; cannot resume the frozen study')
        archived = archive_interrupted(root, folders, args.retry_interrupted)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        write_json(root / 'resumptions' / (stamp + '.json'), {
            'pending_ids': [t['id'] for _, t in pending],
            'completed_ids_not_reexecuted': [t['id'] for i, t in enumerate(manifest['selection']) if i not in {j for j, _ in pending}],
            'archived_interrupted_calls': archived, 'runtime': current})
        write_json(root / 'runtime.json', current)
        inference = study.ClaudeCode(study.load_tokenizer({'provider': 'claude_code'}))
        verifier, guard = study.vb.verify_tools(runtime, manifest['config'])
        try:
            for index, task in pending:
                # Original position preserves the original alternating arm order.
                order = study.vb.ARMS if index % 2 == 0 else study.vb.ARMS[::-1]
                study.run_task(root, task, manifest['config'], inference, verifier, guard, order)
        finally:
            study.compare(root)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
