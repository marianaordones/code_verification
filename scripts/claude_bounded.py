"""Streaming CLI transport with local cutoffs; no automatic resubmission."""
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import tempfile
import threading
import time

from baseline.storage import write_json
from solver_needs_study.claude_code import cli_env, decode_transcript

POLICY = {'version': 'bounded-v1', 'output_tokens_per_request': 8192,
          'seconds_per_proposal': 180, 'stop_on_automatic_user_message': True,
          'budget_exhaustion_consumes_proposal': True}


def collect(command, prompt, cwd, env, folder, seconds, token_limit):
    """Persist each line immediately; stop locally on continuation or budget."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=os.name != 'nt')
    events = queue.Queue()

    def read_output(pipe, name, parse):
        with pipe, (folder / name).open('wb', buffering=0) as out:
            for line in iter(pipe.readline, b''):
                out.write(line)
                if parse:
                    events.put(line)
        if parse:
            events.put(None)

    def send_input():
        try:
            process.stdin.write(prompt.encode('utf-8'))
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    readers = [threading.Thread(target=read_output, args=(process.stdout, 'claude-stdout.jsonl', True), daemon=True),
               threading.Thread(target=read_output, args=(process.stderr, 'claude-stderr.txt', False), daemon=True)]
    for thread in readers:
        thread.start()
    threading.Thread(target=send_input, daemon=True).start()
    reason, last_status, thinking, stdout_done = None, 0, 0, False
    try:
        while True:
            elapsed = time.monotonic() - started
            if stdout_done and process.poll() is not None:
                break
            if elapsed >= seconds:
                reason = 'time_budget'
                break
            if elapsed - last_status >= 10:
                print(f'  active {elapsed:.0f}s; thinking estimate={thinking}', flush=True)
                last_status = elapsed
            try:
                line = events.get(timeout=min(0.2, seconds - elapsed))
            except queue.Empty:
                continue
            if line is None:
                stdout_done = True
                continue
            try:
                event = json.loads(line)
            except ValueError:
                reason = 'malformed_stream'
                break
            if event.get('type') == 'user':
                reason = 'automatic_continuation'
                break
            if event.get('subtype') == 'compact_boundary':
                reason = 'unexpected_compaction'
                break
            if event.get('subtype') == 'thinking_tokens':
                thinking = max(thinking, event.get('estimated_tokens', 0))
                if thinking >= token_limit:
                    reason = 'thinking_budget'
                    break
            if event.get('type') == 'assistant':
                msg = event.get('message', {})
                if any(b.get('type') in ('tool_use', 'server_tool_use') for b in msg.get('content', [])):
                    reason = 'unexpected_tool'
                    break
                if msg.get('stop_reason') == 'max_tokens':
                    reason = 'output_budget'
                    break
                if msg.get('usage', {}).get('output_tokens', 0) > token_limit:
                    reason = 'output_budget'
                    break
    finally:
        if reason or process.poll() is None:
            if process.poll() is None:
                if os.name == 'nt':
                    process.kill()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        process.wait()
        for thread in readers:
            thread.join(timeout=5)
    return {'state': reason or 'completed', 'returncode': process.returncode,
            'seconds': time.monotonic() - started, 'thinking_estimate': thinking}


class BoundedClaude:
    def __init__(self, tokenizer, policy=None):
        self.tokenizer = tokenizer
        self.policy = dict(POLICY if policy is None else policy)

    def generate_at(self, messages, config, folder):
        policy = self.policy
        folder = Path(folder)
        receipt = folder / 'claude-call.json'
        if receipt.exists():
            # Normal saved responses are reused by the caller. Incomplete calls
            # require inspection, never another request to the provider.
            raise RuntimeError('Existing call receipt without response: inspect it; no automatic retry')
        env = cli_env()
        env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'] = str(policy['output_tokens_per_request'])
        with tempfile.TemporaryDirectory(prefix='claude-bounded-') as cwd:
            system = Path(cwd) / 'system.txt'
            system.write_text(messages[0]['content'], encoding='utf-8')
            command = ['claude', '-p', '--safe-mode', '--tools', '', '--disallowedTools', '*',
                '--strict-mcp-config', '--setting-sources', '', '--no-session-persistence',
                '--system-prompt-file', str(system), '--model', config['model'],
                '--effort', config['effort'], '--max-turns', '1', '--output-format', 'stream-json', '--verbose']
            write_json(receipt, {'state': 'started', 'policy': policy, 'command': command})
            print('CALL', folder, f"limit={policy['output_tokens_per_request']} output tokens / {policy['seconds_per_proposal']}s", flush=True)
            call = collect(command, messages[1]['content'], cwd, env, folder,
                           policy['seconds_per_proposal'], policy['output_tokens_per_request'])
            write_json(receipt, {**call, 'policy': policy, 'command': command})
        print('END', folder, call['state'], f"{call['seconds']:.1f}s", flush=True)
        exhausted = call['state'] in ('time_budget', 'thinking_budget', 'output_budget', 'automatic_continuation')
        if not exhausted and (call['state'] != 'completed' or call['returncode'] != 0):
            raise RuntimeError('Claude infrastructure failure; inspect stream; no retry')
        if exhausted:
            text, usage, truncated = '', {}, True
        else:
            result = decode_transcript((folder / 'claude-stdout.jsonl').read_text(), config['model'])
            text, usage = result['result'], result.get('usage', {})
            truncated = result.get('output_truncated', False)
            if usage.get('output_tokens', 0) > policy['output_tokens_per_request']:
                raise RuntimeError('Provider reported output above policy; inspect before continuing')
        return {'text': text, 'usage': usage, 'output_tokens': usage.get('output_tokens'),
                'input_tokens': sum(usage.get(k, 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')) if usage else None,
                'model': config['model'], 'effort': config['effort'], 'seed': None, 'temperature': None,
                'truncated': truncated, 'inference_seconds': call['seconds'], 'resource_policy': policy,
                'resource_exhausted': exhausted, 'resource_stop_reason': call['state'],
                'raw_transcript': 'claude-stdout.jsonl', 'rendered_prompt': json.dumps(messages, ensure_ascii=False)}
