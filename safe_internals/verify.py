"""Original Verus/Z3 capture with bounded child processes, no protocol insertion."""
import os
from pathlib import Path
import sys
import tempfile

from baseline.obligation import collect_queries
from baseline.prompts import ROOT
from baseline.storage import write_text
from baseline.verifier import Verifier


def verify(verifier, source):
    from .pipeline import limited
    folder = source.parent / 'solver'
    capture = folder / 'capture'
    capture.mkdir(parents=True, exist_ok=True)
    for old in capture.glob('solver-*.*'):
        old.unlink()
    with tempfile.TemporaryDirectory(prefix='safe-capture-', dir=os.environ.get('NATIVE_WORKSPACE')) as work:
        proxy = Path(work) / 'z3-proxy'
        write_text(proxy, f'#!{sys.executable}\nimport sys, runpy\nsys.argv.insert(1, "proxy")\n'
                          'runpy.run_module("diagnostics.z3_probe", run_name="__main__")\n')
        proxy.chmod(0o700)
        env = dict(os.environ, VERUS_Z3_PATH=str(proxy), Z3_PROBE_REAL=verifier.z3,
                   Z3_PROBE_CAPTURE=str(capture.resolve()))
        env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
        value = Verifier.classify(limited([verifier.executable, str(source.resolve())],
                                          verifier.timeout, verifier.memory_mb, cwd=source.parent, env=env))
    collect_queries(capture, folder, value['timed_out'])
    return value
