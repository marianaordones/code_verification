import os
from pathlib import Path
import sys
import tempfile

from baseline.obligation import collect_queries
from baseline.prompts import ROOT
from baseline.storage import write_text
from baseline.verifier import Verifier, execute


class StudyVerifier:
    def __init__(self, verus, z3, timeout=120):
        self.verus, self.z3, self.timeout = verus, z3, timeout

    def verify(self, source, nla=False, capture=True, rlimit=10.0):
        flags = ['--crate-type=lib', '--rlimit', str(rlimit), '--no-auto-recommends-check']
        if nla:
            flags += ['--smt-option', 'smt.arith.nl=true']
        folder = source.parent / 'solver'
        destination = folder / 'capture'
        env = dict(os.environ, VERUS_Z3_PATH=self.z3)
        with tempfile.TemporaryDirectory(prefix='solver-needs-', dir=os.environ.get('NATIVE_WORKSPACE')) as work:
            if capture:
                destination.mkdir(parents=True, exist_ok=True)
                for old in destination.glob('solver-*.*'):
                    old.unlink()
                proxy = Path(work) / 'z3-proxy'
                write_text(proxy, f'#!{sys.executable}\nimport sys, runpy\nsys.argv.insert(1, "proxy")\n'
                           'runpy.run_module("diagnostics.z3_probe", run_name="__main__")\n')
                proxy.chmod(0o700)
                env.update(VERUS_Z3_PATH=str(proxy), Z3_PROBE_REAL=self.z3,
                           Z3_PROBE_CAPTURE=str(destination.resolve()))
                env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
            result = Verifier.classify(execute([self.verus, str(source.resolve()), *flags],
                                      self.timeout, cwd=source.parent, env=env))
        if capture:
            collect_queries(destination, folder, result['timed_out'])
        result['nla_enabled'] = nla
        result['rlimit'] = rlimit
        return result
