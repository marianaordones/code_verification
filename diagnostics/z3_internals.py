"""Bounded API replay for experiment C. Never used to accept a proof."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from baseline.storage import read_json, write_json
from baseline.verifier import execute
from diagnostics.z3_probe import head, snapshots


def api_env():
    env = dict(os.environ)
    if env.get("Z3_INTERNALS_PYTHONPATH"):
        env["PYTHONPATH"] = env["Z3_INTERNALS_PYTHONPATH"] + os.pathsep + env.get("PYTHONPATH", "")
    return env


def identity():
    import builtins
    spec = importlib.util.find_spec("z3")
    if spec is None:
        raise ValueError("Isolated z3-solver package is unavailable")
    library_dir = Path(spec.origin).resolve().parent / "lib"
    extension = "dll" if sys.platform == "win32" else "dylib" if sys.platform == "darwin" else "so"
    library = library_dir / ("libz3." + extension)
    if not library.is_file():
        raise ValueError("Packaged Z3 native library is missing")
    # Supported Z3Py loading hook: force the packaged library before importing z3.
    builtins.Z3_LIB_DIRS = [str(library_dir)]
    import z3
    if z3.get_version()[:3] != (4, 12, 5):
        raise ValueError("Experiment C requires z3-solver 4.12.5.0")
    return {"version": z3.get_version_string(),
            "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest()}


def worker(query_file, output, timeout_ms):
    report = {"status": "unavailable", "scope": "diagnostic_api_replay",
              "timeout_ms": timeout_ms, "instantiations_observed": 0,
              "instantiations_saved": 0, "oversized_events_omitted": 0,
              "callback_errors": 0, "sample_limit": 200}
    output.mkdir(parents=True, exist_ok=True)
    try:
        report["z3"] = identity()
        import z3
        text = query_file.read_text(encoding="utf-8")
        report["query_sha256"] = hashlib.sha256(query_file.read_bytes()).hexdigest()
        checks = list(snapshots(text))
        if len(checks) != 1 or head(checks[0][1]) != "check-sat":
            raise ValueError("Only a single plain check-sat is supported; tactics/assumptions are not approximated")
        solver = z3.Solver()
        solver.from_string(checks[0][0])
        solver.set(timeout=timeout_ms)
        report["option_override"] = {"timeout_ms": timeout_ms}
        with (output / "instantiations.jsonl").open("w", encoding="utf-8") as stream:
            def on_clause(hint, dependencies, clause):
                try:
                    if not z3.is_app(hint) or str(hint.decl().name()) != "inst":
                        return
                    report["instantiations_observed"] += 1
                    if report["instantiations_saved"] >= report["sample_limit"]:
                        return
                    quantifier = hint.arg(0)
                    if not z3.is_quantifier(quantifier):
                        report["callback_errors"] += 1
                        return
                    event = {"quantifier_smt": quantifier.sexpr(),
                             "binding_terms_callback_order": [item.sexpr() for child in hint.children()
                                if z3.is_app(child) and str(child.decl().name()) == "bind"
                                for item in child.children()],
                             "clause_literals_smt": [item.sexpr() for item in clause]}
                    serialized = json.dumps(event, ensure_ascii=False)
                    if len(serialized) > 64000:
                        report["oversized_events_omitted"] += 1
                        return  # Omit whole events, never truncate formulas.
                    stream.write(serialized + "\n")
                    report["instantiations_saved"] += 1
                except Exception:
                    report["callback_errors"] += 1

            callback = z3.OnClause(solver, on_clause)
            started = time.perf_counter()
            result = solver.check()
            report.update(status="completed", result=str(result),
                          reason_unknown=solver.reason_unknown() if result == z3.unknown else None,
                          check_seconds=time.perf_counter() - started,
                          statistics={key: value for key, value in solver.statistics()})
            assert callback is not None
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["instantiations_not_saved"] = report["instantiations_observed"] - report["instantiations_saved"]
    write_json(output / "report.json", report)
    return 0 if report["status"] == "completed" else 1


def replay(query, output, timeout_ms):
    call = execute([sys.executable, "-m", "diagnostics.z3_internals", "worker",
                    "--query", str(query.resolve()), "--output", str(output.resolve()),
                    "--timeout-ms", str(timeout_ms)], timeout_ms / 1000 + 15, env=api_env())
    write_json(output / "process.json", call)
    if not (output / "report.json").exists():
        write_json(output / "report.json", {"status": "unavailable", "scope": "diagnostic_api_replay",
                   "error": "Replay process failed or exceeded its wall-clock limit",
                   "timeout_ms": timeout_ms})
    return read_json(output / "report.json")


def api_identity():
    call = execute([sys.executable, "-m", "diagnostics.z3_internals", "identity"], 30, env=api_env())
    if call["returncode"] != 0:
        raise RuntimeError("Z3 API preflight failed: " + call["stderr"])
    return json.loads(call["stdout"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["worker", "identity", "selftest"])
    parser.add_argument("--query", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-ms", type=int, default=5000)
    args = parser.parse_args()
    if args.command == "identity":
        print(json.dumps(identity()))
        return 0
    if args.command == "selftest":
        with tempfile.TemporaryDirectory(dir=os.environ.get("NATIVE_WORKSPACE")) as temporary:
            query = Path(__file__).parent / "z3/sat_quantified.smt2"
            report = replay(query, Path(temporary) / "replay", 5000)
            if (report.get("result") != "sat" or report.get("instantiations_saved", 0) < 1
                    or report.get("callback_errors", 0) or not report.get("statistics")):
                raise RuntimeError("Z3 internals self-test failed: " + json.dumps(report))
            print("Z3 replay, statistics and instantiation callback: OK")
        return 0
    if args.query is None or args.output is None:
        parser.error("worker requires --query and --output")
    return worker(args.query, args.output, args.timeout_ms)


if __name__ == "__main__":
    raise SystemExit(main())
