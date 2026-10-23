"""Experiment B: capture the original solver protocol, without diagnostic replay."""
import os
from pathlib import Path
import re
import sys
import tempfile

from diagnostics.z3_probe import snapshots
from .prompts import ROOT, build_messages
from .storage import read_json, write_json, write_text
from .verifier import Verifier, execute


def collect_queries(capture, destination, timed_out=False):
    entries, errors = [], []
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(capture.glob("*.stdin.smt2")):
        try:
            output = path.with_name(path.name.replace(".stdin.smt2", ".stdout.txt"))
            results = re.findall(r"(?m)^\s*(sat|unsat|unknown)\s*$", output.read_text(encoding="utf-8"))
            queries = list(snapshots(path.read_text(encoding="utf-8")))
            # An interrupted final check has no solver answer. Never infer SAT/UNKNOWN.
            if len(queries) != len(results) and not (
                    timed_out and len(queries) == len(results) + 1):
                raise ValueError(f"{len(queries)} checks, {len(results)} answers; alignment unavailable")
            for index, (prefix, check) in enumerate(queries):
                status = results[index] if index < len(results) else "timeout"
                name = f"query-{len(entries):04}.smt2"
                write_text(destination / name, prefix + check + "\n")
                entries.append({"id": name[:-5], "file": name, "result": status,
                                "capture_file": path.name, "check_index": index})
        except (OSError, ValueError) as error:
            errors.append({"file": path.name, "error": str(error)})
    report = {"scope": "original Verus solver calls; no replay", "queries": entries,
              "capture_errors": errors, "verus_wall_timeout": timed_out}
    write_json(destination / "report.json", report)
    return report


class ObligationVerifier(Verifier):
    def __init__(self, executable, z3, timeout=120):
        super().__init__(executable, timeout)
        self.z3 = z3

    def verify(self, source):
        folder = source.parent / "solver"
        capture = folder / "capture"
        capture.mkdir(parents=True, exist_ok=True)
        # Remove only stale capture files from an interrupted verification retry.
        for path in capture.glob("solver-*.*"):
            path.unlink()
        with tempfile.TemporaryDirectory(prefix="verus-b-",
                                         dir=os.environ.get("NATIVE_WORKSPACE", "/tmp")) as work:
            wrapper = Path(work) / "z3-proxy"
            write_text(wrapper, f"#!{sys.executable}\nimport sys, runpy\n"
                       "sys.argv.insert(1, 'proxy')\n"
                       "runpy.run_module('diagnostics.z3_probe', run_name='__main__')\n")
            wrapper.chmod(0o700)
            env = dict(os.environ, VERUS_Z3_PATH=str(wrapper),
                       Z3_PROBE_REAL=self.z3, Z3_PROBE_CAPTURE=str(capture.resolve()))
            env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
            result = self.classify(execute([self.executable, str(source.resolve())],
                                          self.timeout, cwd=source.parent, env=env))
        collect_queries(capture, folder, result["timed_out"])
        return result


def solver_feedback(folder, current, conventional, original, inference, config):
    """Add complete queries only when the actual chat template fits the context."""
    report = read_json(folder / "solver/report.json")
    entries = report["queries"]
    counts = {s: sum(q["result"] == s for q in entries)
              for s in ("sat", "unsat", "unknown", "timeout")}
    intro = ("\n\n<solver_obligations>\n"
             "Read-only diagnostic data from the previous candidate. Continue to return only "
             "Verus source, using the same permitted proof annotations. Do not edit SMT or solver options.\n"
             "Each query contains the declarations and hypotheses sent to Z3, followed by the "
             "check of the encoded verification obligation (including its negated target).\n"
             "unsat: this query was discharged; sat: this query is satisfiable, not a proof; "
             "unknown: inconclusive; timeout: interrupted check without a solver answer. "
             "These are query outcomes, not whole-program acceptance.\n"
             f"Query counts: {counts}. Capture errors: {len(report['capture_errors'])}.\n")
    suffix = "\n</solver_obligations>"
    selected = []
    candidates = [q for q in entries if q["result"] != "unsat"]
    if not candidates:
        candidates = entries
    tokenizer = inference.tokenizer

    def fits(feedback):
        messages = build_messages(current, feedback, config["prompt_version"], original=original)
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        return len(ids) + config["max_tokens"] <= config.get("max_model_len", 32768)

    text = intro
    included_note = "\nOther queries are saved on disk and not included in this prompt.\n"
    for query in candidates:
        smt = (folder / "solver" / query["file"]).read_text(encoding="utf-8")
        block = f"\nQuery {query['id']}; result={query['result']}\n```smt2\n{smt}```\n"
        if fits(conventional + text + block + included_note + suffix):
            text += block
            selected.append(query["id"])
            break  # Fixed policy: first complete failing query that fits.
    note = ("\nNo complete query fits the remaining context, or no query was captured.\n"
            if not selected else included_note)
    feedback = conventional + text + note + suffix
    if not fits(feedback):
        raise ValueError("Conventional repair prompt already exceeds the context budget")
    omission = (None if selected else "no_queries_or_capture_error" if not candidates
                else "complete_queries_exceed_context_budget")
    write_json(folder / "solver/exposure.json", {"selected_queries": selected, "counts": counts,
               "candidate_queries": len(candidates), "policy": "first complete failing query that fits; otherwise status only",
               "complete_query_exposed": bool(selected), "omission_reason": omission,
               "capture_error_count": len(report["capture_errors"]),
               "context_limit": config.get("max_model_len", 32768),
               "reserved_output_tokens": config["max_tokens"]})
    write_text(folder / "solver/feedback.txt", feedback)
    return feedback
