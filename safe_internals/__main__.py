import argparse
from contextlib import contextmanager
from pathlib import Path
import sys

from .pipeline import prepare, collect, summarize


@contextmanager
def lock(root):
    if sys.platform != 'linux':
        raise ValueError('Collection/submission requires Linux; run unit tests locally')
    import fcntl
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.lock').open('w') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another collector is using this output directory') from None
        yield


def main():
    parser = argparse.ArgumentParser(description='CPU-only SAFE internals pilot; no LLM')
    parser.add_argument('command', choices=['prepare', 'collect', 'report'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        parser.error('This pilot supports one or two concurrent examples')
    if args.command == 'prepare' and args.dataset is None:
        parser.error('prepare requires --dataset')
    with lock(args.output):
        if args.command == 'prepare':
            prepare(args.dataset.resolve(), args.output.resolve())
            return 0
        if args.command == 'report':
            summarize(args.output.resolve())
            return 0
        return collect(args.output.resolve(), args.workers)


if __name__ == '__main__':
    raise SystemExit(main())
