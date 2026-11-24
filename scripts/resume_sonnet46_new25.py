"""Inspect pending tasks and archive only proven zero-token quota failures.

Never invokes inference. After release-quota, use the unchanged batch runner.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import uuid

from baseline.storage import digest, read_json, write_json
from scripts import run_sonnet46_new25_120s as batch
from scripts.resume_sonnet46_remaining import pending_tasks, provenance


def validate_quota_failure(folder):
    folder = Path(folder)
    if (folder / 'response.json').exists() or (folder / 'result.json').exists():
        raise ValueError('A response/result exists; do not release this call')
    receipt = read_json(folder / 'claude-call.json')
    if receipt.get('state') != 'completed' or receipt.get('returncode') != 1:
        raise ValueError('Not a completed rejected CLI invocation')
    import json
    events = [json.loads(line) for line in (folder / 'claude-stdout.jsonl').read_text().splitlines() if line.strip()]
    results = [e for e in events if e.get('type') == 'result']
    if len(results) != 1:
        raise ValueError('Expected one final quota result')
    result = results[0]
    if not (result.get('is_error') and result.get('api_error_status') == 429 and
            result.get('api_error') == 'usage_limit_reached'):
        raise ValueError('Not the supported usage-limit rejection')
    usage = result.get('usage', {})
    required = ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')
    if any(usage.get(k) != 0 for k in required) or result.get('modelUsage'):
        raise ValueError('Usage is nonzero or unknown; inspect manually')
    if any(e.get('type') == 'assistant' and e.get('message', {}).get('model') != '<synthetic>' for e in events):
        raise ValueError('Actual model output exists; inspect manually')
    if not (folder / 'request.json').is_file():
        raise ValueError('Missing original request')
    return receipt


def archive(root, folder):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    if not folder.is_relative_to(root):
        raise ValueError('Attempt outside study')
    names = ('claude-call.json', 'claude-stdout.jsonl', 'claude-stderr.txt')
    for name in (*names, 'request.json'):
        path = folder / name
        if path.is_symlink() or (path.exists() and path.resolve().parent != folder):
            raise ValueError('Unexpected linked artifact')
    receipt = validate_quota_failure(folder)
    base = folder / 'quota-rejections'
    if base.exists() and (base.is_symlink() or not base.resolve().is_relative_to(folder)):
        raise ValueError('Unexpected archive location')
    target = base / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    target.mkdir(parents=True, exist_ok=False)
    write_json(target / 'release.json', {'reason': 'Explicit release of saved zero-token quota rejection',
        'request_sha256': digest((folder / 'request.json').read_bytes()), 'previous_receipt': receipt})
    for name in names:
        if (folder / name).exists():
            (folder / name).rename(target / name)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'release-quota'), nargs='?', default='check')
    parser.add_argument('--output', type=Path, default=batch.DEFAULT)
    args = parser.parse_args()
    root = args.output.resolve()
    with batch.study.vb.run_lock(root):
        manifest = batch.validate(root)
        pending = pending_tasks(root, manifest)
        print(f'Completed: {len(manifest["selection"]) - len(pending)}; pending: {len(pending)}')
        rejected = []
        for _, task in pending:
            print('Pending:', task['id'])
            for arm in ('shared', *batch.study.vb.ARMS):
                for folder in (root / arm / task['id']).glob('attempt_*'):
                    if (folder / 'claude-call.json').exists() and not (folder / 'response.json').exists() and not (folder / 'result.json').exists():
                        validate_quota_failure(folder)
                        print('Supported zero-token quota rejection:', folder.relative_to(root))
                        rejected.append(folder)
        if args.command == 'release-quota':
            # Only local version/auth checks; no model requests.
            runtime = batch.study.vb.tools()
            plan = read_json(root / 'pilot-plan.json')
            if batch.study.vb.identity(runtime) != manifest['tools'] or provenance() != plan['runtime']:
                raise ValueError('Runtime changed; no calls released')
            for folder in rejected:
                print('Archived:', archive(root, folder))
        print('No Claude inference requests made. Original request and completed results preserved.')


if __name__ == '__main__':
    main()
