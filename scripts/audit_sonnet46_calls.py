"""Read-only summary of saved Claude call artifacts (never calls Claude)."""
import collections
import json
from pathlib import Path
import statistics
import sys


def main():
    root = Path(sys.argv[1])
    rows = []
    for path in sorted(root.rglob('claude-call.json')):
        receipt = json.loads(path.read_text())
        raw = path.with_name('claude-stdout.jsonl')
        events, malformed = [], 0
        if raw.exists():
            for line in raw.read_text().splitlines():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    malformed += 1
        counts = collections.Counter((e.get('type'), e.get('subtype')) for e in events)
        thinking = [e.get('estimated_tokens', 0) for e in events if e.get('subtype') == 'thinking_tokens']
        results = [e for e in events if e.get('type') == 'result']
        assistants = [e.get('message', {}) for e in events if e.get('type') == 'assistant']
        row = {'path': str(path.relative_to(root)), 'state': receipt.get('state'),
               'seconds': receipt.get('seconds'), 'thinking_estimate': max(thinking, default=0),
               'results': len(results), 'assistant_messages': len(assistants)}
        segments, peak = [], 0
        for event in events:
            if event.get('subtype') == 'thinking_tokens':
                peak = max(peak, event.get('estimated_tokens', 0))
            if event.get('type') == 'user':
                segments.append(peak)
                peak = 0
        segments.append(peak)
        row['thinking_segment_peaks'] = segments
        row['automatic_user_messages'] = sum(e.get('type') == 'user' for e in events)
        if results:
            row['usage'] = results[-1].get('usage')
        rows.append(row)
        if receipt.get('state') != 'completed':
            request = path.with_name('request.json')
            messages = json.loads(request.read_text()).get('messages', []) if request.exists() else []
            print('INCOMPLETE', json.dumps({**row, 'event_counts': {str(k): v for k, v in counts.items()},
                'session_ids': sorted({e['session_id'] for e in events if e.get('session_id')}),
                'malformed_lines': malformed,
                'message_chars': [(m.get('role'), len(m.get('content', ''))) for m in messages],
                'assistant_blocks': [collections.Counter(b.get('type') for b in m.get('content', [])) for m in assistants],
                'init': [{k: e.get(k) for k in ('model', 'tools', 'mcp_servers', 'permissionMode', 'claude_code_version')} for e in events if e.get('subtype') == 'init']}, ensure_ascii=False))
            print('INCOMPLETE_FLOW', json.dumps([
                {'type': e.get('type'), 'subtype': e.get('subtype'),
                 'stop_reason': e.get('message', {}).get('stop_reason'),
                 'usage': e.get('message', {}).get('usage'),
                 'content': e.get('message', {}).get('content') if e.get('type') == 'user' else None,
                 'rate_limit_info': e.get('rate_limit_info'),
                 'blocks': [{'type': b.get('type'), 'chars': len(b.get('thinking', b.get('text', '')))} for b in e.get('message', {}).get('content', [])] if e.get('type') == 'assistant' else None}
                for e in events if e.get('type') in ('assistant', 'user', 'rate_limit_event')], ensure_ascii=False))
    complete = [r for r in rows if r['state'] == 'completed']
    print('SUMMARY', json.dumps({'receipts': len(rows), 'completed': len(complete),
        'median_seconds': statistics.median([r['seconds'] for r in complete]) if complete else None,
        'longest_calls': sorted(complete, key=lambda r: r['seconds'], reverse=True)[:5]}, ensure_ascii=False))
    print('RESUMPTIONS', json.dumps([json.loads(p.read_text()) for p in sorted((root / 'resumptions').glob('*.json'))], ensure_ascii=False))


if __name__ == '__main__':
    main()
