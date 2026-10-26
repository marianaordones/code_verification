import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from scripts.claude_bounded import collect


class StreamTests(unittest.TestCase):
    def collect(self, code, seconds=2, tokens=8192):
        with tempfile.TemporaryDirectory() as work:
            result = collect([sys.executable, '-u', '-c', code], 'test', work,
                             os.environ.copy(), work, seconds, tokens)
            lines = (Path(work) / 'claude-stdout.jsonl').read_text()
            return result, lines

    def test_continuation_stops_without_waiting_for_next_output(self):
        result, lines = self.collect('import time; print(\'{"type":"user","message":{"content":"Output token limit hit"}}\', flush=True); time.sleep(20)')
        self.assertEqual(result['state'], 'automatic_continuation')
        self.assertLess(result['seconds'], 5)
        self.assertIn('Output token limit hit', lines)

    def test_time_budget_without_any_output(self):
        result, _ = self.collect('import time; time.sleep(20)', seconds=0.2)
        self.assertEqual(result['state'], 'time_budget')
        self.assertLess(result['seconds'], 5)

    def test_thinking_cutoff(self):
        result, _ = self.collect('import time; print(\'{"type":"system","subtype":"thinking_tokens","estimated_tokens":8192}\', flush=True); time.sleep(20)')
        self.assertEqual(result['state'], 'thinking_budget')

    def test_normal_stream_saved(self):
        result, lines = self.collect('print(\'{"type":"result","subtype":"success"}\')')
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(json.loads(lines)['type'], 'result')


if __name__ == '__main__':
    unittest.main()
