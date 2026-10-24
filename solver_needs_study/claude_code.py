"""Official subscription CLI transport; no tools, automatic retries, or verifier access."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

from baseline.prompts import ROOT
from baseline.provenance import tool_identity
from baseline.storage import digest, read_json, write_json, write_text


def validate_config(config):
    expected = {'model': 'claude-opus-5-5', 'max_attempts': 3,
                'seed': None, 'temperature': None, 'max_tokens': 4096,
                'max_model_len': 49152, 'internals_token_budget': 12288,
                'max_queries': 3, 'max_quantifiers': 20, 'max_instances_each': 3}
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError('Unexpected Claude pilot configuration; expected Opus 5.5/three proposals and frozen feedback')
    if config.get('effort') not in ('low', 'medium'):
        raise ValueError('Expected explicit low or medium effort')
    if config.get('claude_timeout', 0) <= 0:
        raise ValueError('A positive Claude timeout is required')


def cli_env():
    # Preserve normal subscription login files; remove inference overrides.
    forbidden = ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL',
                 'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK',
                 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY')
    if any(os.environ.get(k) for k in forbidden):
        raise ValueError('Remove API/provider/token environment overrides; this runner requires native claude.ai login')
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('ANTHROPIC_', 'CLAUDE_', 'MAX_THINKING_TOKENS'))}
    env['DISABLE_AUTOUPDATER'] = '1'
    env['CLAUDE_CODE_MAX_RETRIES'] = '0'
    return env


def preflight():
    env = cli_env()
    binary = tool_identity('claude')
    with tempfile.TemporaryDirectory(prefix='claude-preflight-') as cwd:
        version = subprocess.run(['claude', '--version'], env=env, cwd=cwd,
                                 capture_output=True, text=True, check=True, timeout=30).stdout.strip()
        auth = subprocess.run(['claude', 'auth', 'status'], env=env, cwd=cwd,
                              capture_output=True, text=True, check=True, timeout=30)
    status = json.loads(auth.stdout)
    if not status.get('loggedIn') or status.get('authMethod') != 'claude.ai' or status.get('subscriptionType') != 'pro':
        raise ValueError('Expected logged-in claude.ai Pro subscription')
    return {'cli': binary, 'version': version, 'auth_method': status['authMethod'],
            'subscription': status['subscriptionType']}


def decode_transcript(stdout, model):
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    initial = [e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init']
    results = [e for e in events if e.get('type') == 'result']
    if len(initial) != 1 or len(results) != 1:
        raise ValueError('Expected one init and one result in CLI transcript')
    init, result = initial[0], results[0]
    if init.get('tools') != [] or init.get('mcp_servers', []) != []:
        raise ValueError('CLI exposed tools or MCP servers; aborting experiment')
    if init.get('model') != model:
        raise ValueError('CLI initialized with a different model')
    if result.get('is_error') or result.get('subtype') != 'success':
        raise ValueError('CLI infrastructure/limit error; inspect claude stdout/stderr and resume after resolving it')
    for event in events:
        if event.get('type') == 'assistant':
            message = event.get('message', {})
            if message.get('model') != model:
                raise ValueError('Assistant model changed during request')
            if message.get('stop_reason') == 'max_tokens':
                result['output_truncated'] = True
            if any(b.get('type') in ('tool_use', 'server_tool_use') for b in message.get('content', [])):
                raise ValueError('Unexpected tool use in CLI transcript')
        if event.get('type') == 'system' and event.get('subtype') == 'compact_boundary':
            raise ValueError('CLI compacted prompt; cannot preserve experimental input')
    models = result.get('modelUsage', {})
    if models and set(models) != {model}:
        raise ValueError('Usage reports additional/different models')
    if not isinstance(result.get('result'), str):
        raise ValueError('CLI did not return response text')
    return result


class ClaudeCode:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def generate_at(self, messages, config, folder):
        if [m['role'] for m in messages] != ['system', 'user']:
            raise ValueError('Expected explicit system and user messages')
        receipt = folder / 'claude-call.json'
        if receipt.exists():
            saved = read_json(receipt)
            if saved.get('state') != 'completed' or saved.get('returncode') != 0:
                raise RuntimeError('Previous CLI call interrupted/failed. Inspect raw files, archive claude-call.json before explicit retry; no automatic resubmission')
            stdout = (folder / 'claude-stdout.jsonl').read_text(encoding='utf-8')
            elapsed = saved['seconds']
        else:
            env = cli_env()
            # Empty working directory: private labels, reference assertion and results
            # never become a workspace the inference client can inspect.
            with tempfile.TemporaryDirectory(prefix='claude-proof-') as work:
                system = Path(work) / 'system.txt'
                write_text(system, messages[0]['content'])
                command = ['claude', '-p', '--safe-mode', '--tools', '',
                           '--disallowedTools', '*', '--strict-mcp-config',
                           '--setting-sources', '', '--no-session-persistence',
                           '--system-prompt-file', str(system), '--model', config['model'],
                           '--effort', config['effort'], '--max-turns', '1',
                           '--output-format', 'stream-json', '--verbose']
                write_json(receipt, {'state': 'started', 'command': command,
                                    'model': config['model'], 'effort': config['effort']})
                started = time.perf_counter()
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, cwd=work, env=env, text=True,
                                           encoding='utf-8', start_new_session=os.name != 'nt')
                timed_out = False
                try:
                    stdout, stderr = process.communicate(messages[1]['content'], timeout=config['claude_timeout'])
                except subprocess.TimeoutExpired:
                    import signal
                    timed_out = True
                    if os.name == 'nt':
                        process.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate()
                elapsed = time.perf_counter() - started
                write_text(folder / 'claude-stdout.jsonl', stdout)
                write_text(folder / 'claude-stderr.txt', stderr)
                write_json(receipt, {'state': 'timed_out' if timed_out else 'completed',
                                    'returncode': process.returncode, 'seconds': elapsed,
                                    'model': config['model'], 'effort': config['effort'],
                                    'command': command})
                if timed_out or process.returncode != 0:
                    raise RuntimeError('Claude CLI failed or timed out; raw response saved; no automatic retry')
        result = decode_transcript(stdout, config['model'])
        usage = result.get('usage', {})
        input_tokens = sum(usage.get(k, 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
        return {'text': result['result'], 'rendered_prompt': json.dumps(messages, ensure_ascii=False, indent=2),
                'input_tokens': input_tokens, 'output_tokens': usage.get('output_tokens', 0),
                'usage': usage, 'model_usage': result.get('modelUsage'),
                'token_count_method': 'Claude CLI usage, input includes cache reads/writes; missing counters recorded in raw usage',
                'truncated': result.get('output_truncated', False), 'inference_seconds': elapsed,
                'seed': None, 'temperature': None, 'effort': config['effort'], 'model': config['model'],
                'hard_output_token_limit': None, 'raw_transcript': 'claude-stdout.jsonl'}


def run_local(root, manifest, identities):
    from .__main__ import compare, load_tokenizer, run_case
    from .feedback import ARMS
    from .verify import StudyVerifier
    config = manifest['config']
    validate_config(config)
    runtime = preflight()  # Local commands only, no model request.
    runtime['versions'] = {p: importlib.metadata.version(p) for p in
                           ('transformers', 'tokenizers', 'huggingface-hub', 'z3-solver', 'numpy')}
    runtime['requirements_sha256'] = digest((ROOT / 'requirements-claude-local.txt').read_bytes())
    runtime['python'] = sys.version
    runtime['platform'] = platform.platform()
    fingerprint = digest(json.dumps(runtime, sort_keys=True).encode())
    if (root / 'run.json').exists() and read_json(root / 'run.json')['fingerprint'] != fingerprint:
        raise ValueError('CLI/runtime changed; use a new study directory')
    write_json(root / 'run.json', {'fingerprint': fingerprint, 'runtime': runtime, 'config': config,
                                 'tools': identities, 'seed_control': False, 'temperature_control': False,
                                 'hard_output_token_limit': None})
    inference = None
    verifier = StudyVerifier(identities['verus']['path'], identities['z3']['path'], config['verification_timeout'])
    try:
        for index, case in enumerate(manifest['cases']):
            initial = read_json(root / 'inputs' / case['id'] / 'verification.json')
            for arm in (ARMS if index % 2 == 0 else ARMS[::-1]):
                if (root / arm / case['id'] / 'task.json').exists():
                    continue
                if not initial['success'] and inference is None:
                    inference = ClaudeCode(load_tokenizer(config))
                try:
                    run_case(root, arm, case, config, inference, verifier)
                except Exception as error:
                    write_json(root / arm / case['id'] / 'error.json',
                               {'error': str(error), 'type': type(error).__name__})
                    raise  # Stop the batch at first quota/transport/infrastructure failure.
    finally:
        report = compare(root)
    return 0 if report['complete'] and report['first_pair_check_passed'] else 1


if __name__ == '__main__':
    print(json.dumps(preflight(), indent=2))
