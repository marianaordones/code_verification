"""Resumable CPU validation of original SAFE generation answers; no LLM/replays."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from safe_internals.data import FENCE, code_tags
from safe_internals.pipeline import limited
from safe_internals.validation import classify, preservation
from baseline.integrity import tokens, FORBIDDEN
from baseline.storage import write_json, write_text
from baseline.provenance import tool_identity, tool_signature, command


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, default=ROOT / 'data/safe/sft_safe_25k.json')
    p.add_argument('--output', type=Path, default=ROOT / 'results/safe-generation-validation')
    a = p.parse_args()
    rows = json.loads(a.dataset.read_text(encoding='utf-8'))
    digest = hashlib.sha256(a.dataset.read_bytes()).hexdigest()
    tool = tool_identity(os.environ['VERUS_BIN'])
    tool['version'] = command([tool['path'], '--version'])
    manifest = {'dataset_sha256': digest, 'verus': tool_signature(tool),
                'z3': tool_signature(tool_identity(os.environ['Z3_BIN'])),
                'lynette': tool_signature(tool_identity(os.environ['LYNETTE_BIN'])),
                'timeout': 120, 'memory_mb': 4096, 'policy': 'safe-proof-attributes-v2'}
    if '33269ac' not in str(tool['version']):
        raise ValueError('Use the historical Verus 33269ac bundle, matching repair collection')
    a.output.mkdir(parents=True, exist_ok=True)
    if (a.output / 'manifest.json').exists() and json.loads((a.output / 'manifest.json').read_text()) != manifest:
        raise ValueError('Validation inputs/tool changed; use another output directory')
    write_json(a.output / 'manifest.json', manifest)
    indices = [i for i, row in enumerate(rows) if 'provided Verus code contains errors' not in row.get('prompt', '')]
    def check(index):
        folder = a.output / f'safe-{index:05d}'
        path = folder / 'result.json'
        if path.exists():
            saved = json.loads(path.read_text())
            if saved.get('error_type') != 'verifier_error':
                return saved
        blocks = FENCE.findall(rows[index]['output'])
        inputs = FENCE.findall(rows[index]['input'])
        if len(blocks) != 1 or len(inputs) != 1:
            result = {'index': index, 'success': False, 'assume_free': False,
                      'preservation_status': 'unparseable', 'error_type': 'unsupported_fences'}
        else:
            code = blocks[0]
            write_text(folder / 'target.rs', code)
            verification = classify(limited([os.environ['VERUS_BIN'], str((folder / 'target.rs').resolve())],
                                            120, 4096, cwd=folder,
                                            env=dict(os.environ, VERUS_Z3_PATH=os.environ['Z3_BIN'])))
            write_json(folder / 'verification.json', verification)
            preserved = preservation(inputs[0], code, folder, os.environ['LYNETTE_BIN'])
            write_json(folder / 'preservation.json', preserved)
            tags = code_tags(code)
            try:
                banned = sorted(set(tokens(code)) & FORBIDDEN)
            except ValueError:
                banned = ['unresolved_lexing']
            result = {'index': index, 'success': verification['success'],
                      'assume_free': tags['assume_call'] is False and not banned,
                      'preservation_status': preserved['status'],
                      'excluded_constructs': banned, 'error_type': verification['error_type']}
        write_json(path, result)
        print(f"Generation safe-{index:05d}: {result['success']}", flush=True)
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(check, indices))
    write_json(a.output / 'validation.json', {'dataset_sha256': digest, 'records': records,
                                            'verified_preserved_assume_free': sum(r['success'] and r['assume_free']
                                                and r['preservation_status'] == 'valid' for r in records)})


if __name__ == '__main__':
    main()
