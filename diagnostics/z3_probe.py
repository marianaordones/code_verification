"""Small, isolated capability probe. No model inference and no benchmark sweep."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json, write_text
from baseline.verifier import execute


def commands(text):
    """Split SMT-LIB commands, respecting comments, strings and quoted symbols."""
    depth = 0
    start = None
    quoted = None
    comment = False
    i = 0
    while i < len(text):
        ch = text[i]
        if comment:
            comment = ch != "\n"
        elif quoted:
            if ch == quoted:
                if quoted == '"' and text[i:i + 2] == '""':
                    i += 1
                else:
                    quoted = None
        elif ch == ";":
            comment = True
        elif ch in ('"', "|"):
            quoted = ch
        elif ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced SMT-LIB input")
            if depth == 0:
                yield text[start:i + 1]
        i += 1
    if depth or quoted:
        raise ValueError("Incomplete SMT-LIB input, possibly interrupted capture")


def head(command):
    match = re.match(r"\(\s*([^\s()]+)", command)
    return match[1] if match else ""


def event_bucket(rule):
    if rule == "assumption":
        return "assumptions"
    if rule == "inst":
        return "instantiations"
    if rule in ("del", "deleted"):
        return "deletions"
    return "other_inferences"


def sample_event(rule, saved, limit):
    """Independent caps prevent the input clauses from starving search events."""
    bucket = event_bucket(rule)
    cap = min(20, limit) if bucket == "assumptions" else limit
    if saved.get(bucket, 0) >= cap:
        return False
    saved[bucket] = saved.get(bucket, 0) + 1
    return True


def snapshots(text):
    """Keep the incremental logical context, not the previous search state."""
    prefix = []
    for command in commands(text):
        name = head(command)
        if name.startswith("check-sat"):
            yield "\n".join(prefix) + "\n", command
        elif name not in ("echo", "exit") and not name.startswith("get-"):
            prefix.append(command)


def proxy(arguments):
    """Transparent tee: do not insert commands into Verus's solver protocol."""
    folder = Path(os.environ["Z3_PROBE_CAPTURE"])
    stem = folder / f"solver-{os.getpid()}-{time.time_ns()}"
    real = os.environ["Z3_PROBE_REAL"]
    write_json(stem.with_suffix(".json"), {"binary": real, "arguments": arguments})
    child = subprocess.Popen([real, *arguments], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def tee(reader, writer, path):
        with path.open("wb") as log:
            try:
                while chunk := reader.read1(16384):
                    log.write(chunk)
                    log.flush()
                    writer.write(chunk)
                    writer.flush()
            except BrokenPipeError:
                pass

    def send():
        tee(sys.stdin.buffer, child.stdin, stem.with_suffix(".stdin.smt2"))
        try:
            child.stdin.close()
        except BrokenPipeError:
            pass

    incoming = threading.Thread(target=send, daemon=True)
    errors = threading.Thread(target=tee, args=(child.stderr, sys.stderr.buffer,
                              stem.with_suffix(".stderr.txt")), daemon=True)
    incoming.start()
    errors.start()
    tee(child.stdout, sys.stdout.buffer, stem.with_suffix(".stdout.txt"))
    code = child.wait()
    errors.join(timeout=2)
    incoming.join(timeout=1)
    return code


def worker(args):
    """Each API replay runs in its own process (OnClause uses global state)."""
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    report = {"mode": args.mode, "scope": "API replay, not the original Verus call",
              "timeout_ms": args.timeout_ms, "forced_rlimit": 1 if args.mode == "api-low-resource" else None,
              "clauses_observed": 0, "instantiations_observed": 0, "events_saved": 0,
              "instantiations_saved": 0,
              "rules_observed": {}, "sampled_buckets": {},
              "callback_errors": 0, "status": "unavailable"}
    try:
        report["phase"] = "import_z3"
        import z3
        report["z3_version"] = z3.get_version_string()
        report["z3_python_path"] = z3.__file__
        if z3.get_version()[:3] != (4, 12, 5):
            raise ValueError("Expected z3-solver 4.12.5.0 in the isolated probe installation")
        query = read_json(args.query)
        check = query["check_command"]
        if head(check) not in ("check-sat", "check-sat-using"):
            raise ValueError("API replay does not support this check command; inspect the CLI replay")
        report["original_tactic_not_reproduced"] = head(check) == "check-sat-using"
        report["candidate_models_enabled"] = args.mode == "api-low-resource"
        if args.mode == "api-low-resource":
            z3.set_param("smt.candidate_models", True)
        solver = z3.Solver()
        report["phase"] = "parse_query"
        solver.from_string(Path(query["prefix_file"]).read_text(encoding="utf-8"))
        solver.set(timeout=args.timeout_ms)
        solver.set("qi.profile", True)
        if args.mode == "api-low-resource":
            solver.set(rlimit=1)
        write_text(out / "assertions.smt2", solver.sexpr())

        def text(expr):
            value = expr.sexpr()
            return {"smt": value[:8000], "truncated": len(value) > 8000}

        with (out / "clauses.jsonl").open("w", encoding="utf-8") as clauses, \
                (out / "instantiations.jsonl").open("w", encoding="utf-8") as instances, \
                (out / "search-inferences.jsonl").open("w", encoding="utf-8") as inferences:
            def on_clause(hint, dependencies, clause):
                try:
                    report["clauses_observed"] += 1
                    rule = str(hint.decl().name()) if z3.is_app(hint) else "unknown"
                    report["rules_observed"][rule] = report["rules_observed"].get(rule, 0) + 1
                    if rule == "inst":
                        report["instantiations_observed"] += 1
                    # Bounded recording; counters continue after the cap.
                    save_clause = sample_event(rule, report["sampled_buckets"], args.max_events)
                    save_instance = rule == "inst" and report["instantiations_saved"] < args.max_events
                    if not save_clause and not save_instance:
                        return
                    event = {"rule": rule, "hint": text(hint), "dependencies": dependencies,
                             "clause": [text(item) for item in clause]}
                    if save_clause:
                        clauses.write(json.dumps(event) + "\n")
                        report["events_saved"] += 1
                        if event_bucket(rule) == "other_inferences":
                            inferences.write(json.dumps(event) + "\n")
                    if save_instance:
                        event["quantifier"] = text(hint.arg(0))
                        event["bindings"] = [text(item) for child in hint.children()
                                             if z3.is_app(child) and str(child.decl().name()) == "bind"
                                             for item in child.children()]
                        instances.write(json.dumps(event) + "\n")
                        report["instantiations_saved"] += 1
                except Exception:
                    report["callback_errors"] += 1

            report["phase"] = "register_callback"
            callback = z3.OnClause(solver, on_clause)
            started = time.perf_counter()
            report["phase"] = "check"
            result = solver.check()
            report.update(status="completed", result=str(result), seconds=time.perf_counter() - started,
                          reason_unknown=solver.reason_unknown() if result == z3.unknown else None,
                          statistics={key: value for key, value in solver.statistics()})
            # Keeping callback alive until after check() is essential.
            assert callback is not None
            report["events_omitted"] = report["clauses_observed"] - report["events_saved"]
            report["instantiations_omitted"] = report["instantiations_observed"] - report["instantiations_saved"]
            if result in (z3.sat, z3.unknown):
                try:
                    model_text = solver.model().sexpr()
                    write_text(out / "model.smt2", model_text)
                    report["model_bytes"] = len(model_text.encode("utf-8"))
                    report["model_status"] = ("sat_model" if result == z3.sat else
                        "unvalidated_candidate_after_unknown" if model_text.strip() else "empty_candidate_after_unknown")
                    if result == z3.sat:
                        model = solver.model()
                        report["assertions_evaluated_true_in_model"] = sum(
                            z3.is_true(model.eval(a, model_completion=False)) for a in solver.assertions())
                        report["assertion_count"] = len(solver.assertions())
                except z3.Z3Exception as error:
                    report["model_status"] = "unavailable"
                    report["model_error"] = str(error)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    if report["status"] == "completed":
        report["phase"] = "finished"
    write_json(out / "report.json", report)
    return 0


def cli_replay(z3, query, folder, timeout_ms):
    prefix = Path(query["prefix_file"]).read_text(encoding="utf-8")
    # All modifications are confined to a separate diagnostic replay.
    values = query.get("inspect_terms", [])
    script = ("(set-option :produce-models true)\n" + prefix
              + f"\n(set-option :timeout {timeout_ms})\n" + query["check_command"]
              + '\n(echo "PROBE_REASON")\n(get-info :reason-unknown)'
                '\n(echo "PROBE_MODEL")\n(get-model)'
                '\n(echo "PROBE_STATISTICS")\n(get-info :all-statistics)\n'
              + ('(echo "PROBE_VALUES")\n(get-value (' + ' '.join(values) + '))\n' if values else '')
              + '(exit)\n')
    write_text(folder / "cli-replay.smt2", script)
    result = execute([z3, "-smt2", str((folder / "cli-replay.smt2").resolve())], timeout_ms / 1000 + 15)
    write_text(folder / "cli.stdout.txt", result["stdout"])
    write_text(folder / "cli.stderr.txt", result["stderr"])
    results = re.findall(r"(?m)^\s*(sat|unsat|unknown)\s*$", result["stdout"])
    sections = re.split(r'(?m)^"?PROBE_(?:REASON|MODEL|STATISTICS|VALUES)"?\s*$', result["stdout"])
    names = ("reason", "model", "statistics", "values") if values else ("reason", "model", "statistics")
    report = {"scope": "same-binary replay; search history is not preserved",
              "result": results[-1] if results else None, "timeout_ms": timeout_ms,
              "timed_out": result["timed_out"], "returncode": result["returncode"],
              "sections_available": len(sections) == len(names) + 1,
              "seconds": result.get("seconds")}
    if report["sections_available"]:
        for name, content in zip(names, sections[1:]):
            write_text(folder / f"cli.{name}.txt", content.strip() + "\n")
            report[name + "_available"] = bool(content.strip()) and "(error" not in content
        report["model_is_confirmed_sat"] = report["model_available"] and report["result"] == "sat"
    write_json(folder / "cli-report.json", report)
    return report


def run(args):
    if sys.platform != "linux":
        raise ValueError("Run the extraction probe on the Linux cluster")
    out = Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a new empty output directory for each probe")
    out.mkdir(parents=True, exist_ok=True)
    work = Path(os.environ["Z3_PROBE_WORK"]).resolve()
    work.mkdir(parents=True, exist_ok=True)
    capture = out / "capture"
    capture.mkdir()
    (out / "verus-logs").mkdir()
    source = Path(args.source).resolve()
    candidate = work / "candidate.rs"
    candidate.write_bytes(source.read_bytes())
    write_text(out / "candidate.rs", candidate.read_text(encoding="utf-8"))
    z3 = str(Path(os.environ["Z3_BIN"]).resolve())
    verus = str(Path(os.environ["VERUS_BIN"]).resolve())
    wrapper = work / "z3-proxy"
    write_text(wrapper, f"#!{sys.executable}\nimport sys, runpy\nsys.argv.insert(1, 'proxy')\n"
                       "runpy.run_module('diagnostics.z3_probe', run_name='__main__')\n")
    wrapper.chmod(0o700)
    os.environ.update(Z3_PROBE_CAPTURE=str(capture), Z3_PROBE_REAL=z3, VERUS_Z3_PATH=str(wrapper))
    command = [verus, "--log", "smt", "--log", "triggers", "--log-dir", str(out / "verus-logs"), str(candidate)]
    verification = execute(command, args.verus_timeout, cwd=work)
    write_json(out / "verus.json", verification)
    write_text(out / "verus.stdout.txt", verification["stdout"])
    write_text(out / "verus.stderr.txt", verification["stderr"])
    report = {"source": str(source), "source_sha256": digest(source.read_bytes()),
              "probe_sha256": digest(Path(__file__).read_bytes()),
              "z3_binary": z3, "z3_sha256": digest(Path(z3).read_bytes()),
              "z3_version": execute([z3, "--version"], 10),
              "verus_version": execute([verus, "--version"], 60),
              "original_call_modified_solver_options": False, "llm_calls": 0,
              "original_verus_wall_timeout_s": args.verus_timeout,
              "query_counts": {"sat": 0, "unsat": 0, "unknown": 0},
              "selected_queries": [], "capture_errors": []}
    for path in sorted(capture.glob("*.stdin.smt2")):
        try:
            stdout_path = path.with_name(path.name.replace(".stdin.smt2", ".stdout.txt"))
            results = re.findall(r"(?m)^\s*(sat|unsat|unknown)\s*$", stdout_path.read_text(encoding="utf-8"))
            queries = list(snapshots(path.read_text(encoding="utf-8")))
            if len(queries) != len(results):
                raise ValueError(f"{len(queries)} checks but {len(results)} results; refusing to guess alignment")
            for index, ((prefix, check), result) in enumerate(zip(queries, results)):
                report["query_counts"][result] += 1
                if result == "unsat" or len(report["selected_queries"]) >= args.max_queries:
                    continue
                folder = out / f"query-{len(report['selected_queries']):02}"
                folder.mkdir()
                write_text(folder / "prefix.smt2", prefix)
                write_text(folder / "query.smt2", prefix + check + "\n")
                query = {"capture_file": str(path), "query_index": index, "original_result": result,
                         "check_command": check, "prefix_file": str(folder / "prefix.smt2"),
                         "original_solver_options": [item for item in commands(prefix)
                                                     if head(item) == "set-option"]}
                write_json(folder / "query.json", query)
                entry = {**query, "folder": str(folder),
                         "cli": cli_replay(z3, query, folder, args.timeout_ms), "api": {}}
                for mode in ("api", "api-low-resource"):
                    destination = folder / mode
                    call = execute([sys.executable, "-m", "diagnostics.z3_probe", "worker",
                                    "--query", str(folder / "query.json"), "--output", str(destination),
                                    "--mode", mode, "--timeout-ms", str(args.timeout_ms),
                                    "--max-events", str(args.max_events)], args.timeout_ms / 1000 + 20)
                    write_json(folder / f"{mode}-process.json", call)
                    entry["api"][mode] = (read_json(destination / "report.json")
                        if (destination / "report.json").exists() else
                        {"status": "unavailable", "reason": "worker exited or timed out; inspect process log"})
                report["selected_queries"].append(entry)
        except Exception as error:
            report["capture_errors"].append({"file": str(path), "error": str(error)})
    total_queries = sum(report["query_counts"].values())
    report["status"] = ("captured" if report["selected_queries"] else
                        "capture_error" if report["capture_errors"] else
                        "no_solver_queries" if total_queries == 0 else "no_sat_or_unknown_query")
    report["verus_returncode"] = verification["returncode"]
    report["verus_timed_out"] = verification["timed_out"]
    write_json(out / "report.json", report)
    lines = ["# Z3 extraction probe", "", "No LLM calls. Original capture and diagnostic replays are separate.",
             f"Status: {report['status']}. Verus exit code: {verification['returncode']}.",
             f"Original query outcomes: {report['query_counts']}",
             f"Selected SAT/UNKNOWN queries: {len(report['selected_queries'])}", "",
             "| Query | Original | CLI replay | API replay | Forced low-resource replay |", "|---|---|---|---|---|"]
    for index, entry in enumerate(report["selected_queries"]):
        a, b = entry["api"]["api"], entry["api"]["api-low-resource"]
        lines.append(f"| {index} | {entry['original_result']} | {entry['cli']['result']} | {a.get('result', a['status'])} | {b.get('result', b['status'])} |")
    if total_queries == 0:
        lines += ["", "NO SOLVER RESULTS WERE CAPTURED. Inspect verus.stderr.txt first.",
                  "Syntax/type errors before SMT solving do not test Z3 extraction capabilities."]
    lines += ["", "See report.json and each query folder for models, statistics, clauses and instantiations.",
              "Samples are capped separately: 20 assumptions and max-events per remaining bucket.",
              "An empty callback log means no recorded events, not that the interface is unsupported.",
              "Low-resource replay deliberately uses rlimit=1. It is not an original UNKNOWN result.",
              "API replay uses a separately packaged Z3 4.12.5 library; it is not the Verus executable build.",
              "Search histories and replay results can differ. No source-variable mapping is inferred."]
    write_text(out / "report.md", "\n".join(lines) + "\n")
    print(f"Probe complete: {out / 'report.md'}", flush=True)
    # Failing verification is expected. Failure to capture any target is not success.
    return 0 if report["selected_queries"] else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "proxy":
        return proxy(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("run")
    capture.add_argument("--source", default=str(ROOT / "diagnostics/z3/failed_proof.rs"))
    capture.add_argument("--output", required=True)
    capture.add_argument("--max-queries", type=int, default=2)
    capture.add_argument("--verus-timeout", type=int, default=120)
    capture.add_argument("--timeout-ms", type=int, default=5000)
    api = sub.add_parser("worker")
    api.add_argument("--query", required=True)
    api.add_argument("--output", required=True)
    api.add_argument("--mode", choices=["api", "api-low-resource"], required=True)
    api.add_argument("--timeout-ms", type=int, default=5000)
    for item in (capture, api):
        item.add_argument("--max-events", type=int, default=200)
    args = parser.parse_args()
    return run(args) if args.command == "run" else worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
