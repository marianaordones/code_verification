"""Validate the localized export, then reuse the tested assistant-only QLoRA trainer."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from localized_sft.convert import sha
from localized_sft.editor import FORMAT
from localized_sft.prompt import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--data', type=Path, required=True)
    args, _ = parser.parse_known_args()
    manifest = json.loads((args.data / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('response_format') != FORMAT:
        raise ValueError('Expected the converted multi-edit debugging export')
    for relative, expected in manifest['implementation'].items():
        if sha(ROOT / relative) != expected:
            raise ValueError('Conversion/editor/prompt changed; regenerate export: ' + relative)
    for name, expected in manifest['files_sha256'].items():
        if sha(args.data / name) != expected:
            raise ValueError('Converted export changed: ' + name)
    from scripts.train_safe_sft import main as train
    train()  # Same QLoRA hyperparameters and exact assistant-only next-token loss.


if __name__ == '__main__':
    main()
