"""One prompt contract shared by conversion and inference."""
import json
from pathlib import Path

from .editor import FORMAT, regions

ROOT = Path(__file__).resolve().parents[1]


def system():
    instruction = (ROOT / 'prompts/safe-multiedit.txt').read_text(encoding='utf-8')
    guide = (ROOT / 'prompts/safe-internals.txt').read_text(encoding='utf-8').split('\n\n', 1)[1]
    return instruction + '\n\n' + guide


def messages(code, diagnostics, payload=None, rejection=None, offered=None):
    sites = regions(code) if offered is None else offered
    user = '<current_program>\n```rust\n' + code + '\n```\n</current_program>\n'
    user += '<verus_diagnostics>\n' + diagnostics + '\n</verus_diagnostics>\n'
    user += '<editable_sites>\n' + json.dumps(sites, ensure_ascii=False, indent=2) + '\n</editable_sites>\n'
    if rejection:
        user += '<previous_edit_rejection>\n' + rejection + '\n</previous_edit_rejection>\n'
    if payload:
        user += '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>\n'
    return [{'role': 'system', 'content': system()}, {'role': 'user', 'content': user}]
