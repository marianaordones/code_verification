"""Resume the frozen run; finalize only known malformed-source LexErrors."""
import os
from pathlib import Path
import subprocess

from baseline.prompts import ROOT
from scripts.recover_verusbench_lexerror import recover


def resume(root, launch, recovery, max_recoveries=120):
    for _ in range(max_recoveries + 1):
        code = launch()
        if code == 0:
            return 0
        if recovery(root) == 0:
            print('Stopped: failure is not a recoverable malformed-source LexError.', flush=True)
            return code
    raise RuntimeError('Recovery bound reached; inspect the study')


def main():
    root = ROOT / 'results/verusbench-sonnet20-low-v2'
    for name, relative in [('VB_VERUS_BIN', 'verus/verus'), ('VB_Z3_BIN', 'verus/z3'),
                           ('VB_LYNETTE_BIN', 'lynette')]:
        os.environ.setdefault(name, str(ROOT / '.local-tools/verusbench' / relative))
    def launch():
        return subprocess.run(['bash', 'scripts/run_verusbench_sonnet20.sh', 'run', str(root)], cwd=ROOT).returncode
    return resume(root, launch, recover)


if __name__ == '__main__':
    raise SystemExit(main())
