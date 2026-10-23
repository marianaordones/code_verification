import os
import re
import signal
import subprocess
import time


def execute(command, timeout, cwd=None, env=None):
    started = time.perf_counter()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace", cwd=cwd,
                               start_new_session=os.name != "nt", env=env)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        stderr += "\nVerifier wall-clock timeout exceeded."
    return {"command": command, "returncode": process.returncode, "stdout": stdout,
            "stderr": stderr, "timed_out": timed_out,
            "seconds": time.perf_counter() - started}


class Verifier:
    def __init__(self, executable, timeout=120):
        self.executable = executable
        self.timeout = timeout

    def verify(self, source):
        return self.classify(execute([self.executable, str(source.resolve())], self.timeout, cwd=source.parent))

    @staticmethod
    def classify(result):
        text = result["stdout"] + "\n" + result["stderr"]
        matches = re.findall(r"verification results::\s*(\d+) verified,\s*(\d+) errors", text)
        verified, errors = map(int, matches[-1]) if matches else (0, -1)
        result["success"] = (result["returncode"] == 0 and not result["timed_out"]
                             and verified > 0 and errors == 0)
        lower = text.lower()
        error_headers = "\n".join(line.lower() for line in text.splitlines()
                                  if re.match(r"^error(?:\[|:)", line))
        if result["success"]:
            kind = None
        elif result["timed_out"] or any(x in lower for x in ("resource limit", "timed out", "rlimit")):
            kind = "timeout"
        elif any(x in error_headers for x in ("expected one of", "unexpected token", "unclosed delimiter", "expected `", "expected curly braces")):
            kind = "syntax"
        elif errors > 0 or any(x in lower for x in ("assertion failed", "not satisfied")):
            kind = "verification"
        elif "error" in lower:
            kind = "compilation"
        else:
            kind = "verifier_error"
        result.update(error_type=kind, verified_functions=verified, verification_errors=errors)
        return result
