import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from baseline.storage import read_json, write_json, write_text
from solver_needs_study import __main__ as study
from solver_needs_study import actions
from solver_needs_study.claude_code import ClaudeCode, cli_env, decode_transcript


MODEL = 'claude-opus-5-5'


def transcript(text='{}', tools=None, model=MODEL, error=False):
    return '\n'.join(json.dumps(e) for e in [
        {'type': 'system', 'subtype': 'init', 'tools': tools or [], 'model': model, 'mcp_servers': []},
        {'type': 'assistant', 'message': {'model': model, 'content': [{'type': 'text', 'text': text}]}},
        {'type': 'result', 'subtype': 'success', 'is_error': error, 'result': text,
         'usage': {'input_tokens': 3, 'cache_read_input_tokens': 5, 'output_tokens': 7},
         'modelUsage': {model: {}}}])


class ClaudeTests(unittest.TestCase):
    def config(self):
        return study.configuration(study.ROOT / 'configs/solver-needs-claude-local.json')

    def test_transport_rejects_tools_fallback_and_limit_errors(self):
        for raw in (transcript(tools=['Read']), transcript(model='other-model'), transcript(error=True)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode_transcript(raw, MODEL)
        events = [json.loads(line) for line in transcript().splitlines()]
        events[1]['message']['content'] = [{'type': 'tool_use', 'name': 'Read'}]
        with self.assertRaises(ValueError):
            decode_transcript('\n'.join(json.dumps(e) for e in events), MODEL)

    def test_rejects_compaction_and_additional_model_usage(self):
        with self.assertRaises(ValueError):
            decode_transcript(transcript() + '\n' + json.dumps({'type': 'system', 'subtype': 'compact_boundary'}), MODEL)
        events = [json.loads(line) for line in transcript().splitlines()]
        events[-1]['modelUsage']['other'] = {}
        with self.assertRaises(ValueError):
            decode_transcript('\n'.join(json.dumps(e) for e in events), MODEL)

    def test_does_not_silently_use_api_credentials(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'not-a-real-key'}, clear=True):
            with self.assertRaises(ValueError):
                cli_env()
        with patch.dict(os.environ, {'CLAUDE_CODE_EFFORT_LEVEL': 'high'}, clear=True):
            env = cli_env()
            self.assertEqual(env['CLAUDE_CODE_MAX_RETRIES'], '0')
            self.assertNotIn('CLAUDE_CODE_EFFORT_LEVEL', env)

    def test_downloads_tokenizer_not_weights(self):
        fake = SimpleNamespace(model_max_length=0)
        loader = SimpleNamespace(from_pretrained=lambda *a, **kw: fake)
        with patch.dict('sys.modules', {'transformers': SimpleNamespace(AutoTokenizer=loader)}), \
             patch.object(study.importlib.metadata, 'version', return_value='4.51.3'), \
             patch.object(study, 'prepare_model', side_effect=AssertionError('must not download model')):
            self.assertIs(study.load_tokenizer(self.config()), fake)

    def test_successful_saved_cli_response_is_reused_without_submission(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            write_json(folder / 'claude-call.json', {'state': 'completed', 'returncode': 0, 'seconds': 1})
            write_text(folder / 'claude-stdout.jsonl', transcript())
            with patch('solver_needs_study.claude_code.subprocess.Popen', side_effect=AssertionError('resubmitted')):
                result = ClaudeCode(None).generate_at([{'role': 'system', 'content': 's'},
                                                      {'role': 'user', 'content': 'u'}], self.config(), folder)
            self.assertEqual(result['input_tokens'], 8)
            self.assertIsNone(result['seed'])
            self.assertIsNone(result['hard_output_token_limit'])

    def test_interrupted_call_never_automatically_resubmits(self):
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            write_json(folder / 'claude-call.json', {'state': 'started'})
            with patch('solver_needs_study.claude_code.subprocess.Popen', side_effect=AssertionError('resubmitted')):
                with self.assertRaises(RuntimeError):
                    ClaudeCode(None).generate_at([{'role': 'system'}, {'role': 'user'}], self.config(), folder)

    def test_request_uses_isolated_cli_and_explicit_medium(self):
        process = SimpleNamespace(returncode=0, communicate=lambda *a, **kw: (transcript(), ''))
        with tempfile.TemporaryDirectory() as work:
            folder = Path(work)
            with patch('solver_needs_study.claude_code.cli_env', return_value={}), \
                 patch('solver_needs_study.claude_code.subprocess.Popen', return_value=process) as popen:
                ClaudeCode(None).generate_at([{'role': 'system', 'content': 's'},
                                             {'role': 'user', 'content': 'u'}], self.config(), folder)
            command = popen.call_args.args[0]
            self.assertEqual(command[command.index('--effort') + 1], 'medium')
            self.assertEqual(command[command.index('--tools') + 1], '')
            self.assertEqual(command[command.index('--disallowedTools') + 1], '*')
            self.assertIn('--safe-mode', command)
            self.assertIn('--system-prompt-file', command)
            self.assertNotEqual(popen.call_args.kwargs['cwd'], str(study.ROOT))

    def test_three_invalid_proposals_and_resume_without_inference(self):
        checked = {'success': False, 'error_type': 'verification', 'stdout': '', 'stderr': ''}
        task = {'prefix': 'verus! { proof fn f() {', 'suffix': '} }', 'proof_context': True}
        calls = []

        def generate_at(prompt, config, folder):
            calls.append(folder)
            return {'text': 'invalid json', 'rendered_prompt': 'prompt', 'input_tokens': 1,
                    'output_tokens': 1, 'truncated': False, 'inference_seconds': 0.1}

        inference = SimpleNamespace(tokenizer=None, generate_at=generate_at)
        verifier = SimpleNamespace(verify=lambda *a, **kw: dict(checked))
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            frozen = root / 'inputs/example'
            write_json(frozen / 'task.json', task)
            write_text(frozen / 'candidate.rs', actions.render(task, actions.EMPTY))
            write_json(frozen / 'verification.json', checked)
            write_json(frozen / 'feedback.json', {'context': {}, 'internals': None, 'availability': 'unavailable'})
            with patch.object(study, 'fits', return_value=True), \
                 patch.object(study, 'messages', return_value=[{'role': 'user', 'content': 'same'}]), \
                 patch.object(actions, 'upstream', return_value=(None, SimpleNamespace(LAWS={}))):
                result = study.run_case(root, 'without_internals', {'id': 'example'}, self.config(), inference, verifier)
                self.assertEqual(len(result['attempts']), 3)
                self.assertTrue(all(a['edit_error'] for a in result['attempts']))
                self.assertIsNone(read_json(calls[0] / 'request.json')['seed'])
                study.run_case(root, 'without_internals', {'id': 'example'}, self.config(), inference, verifier)
                self.assertEqual(len(calls), 3)


if __name__ == '__main__':
    unittest.main()
