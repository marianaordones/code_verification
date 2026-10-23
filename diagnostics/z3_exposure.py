"""Small exposure study: SAT controls, saved proofs, replay stability and payload sizes."""
import argparse
import json
import os
from pathlib import Path
import sys

from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json, write_text
from baseline.verifier import execute
from .z3_probe import cli_replay, snapshots


# Initial candidates audited in the user's complete v3, not reference solutions.
CASES = [
    ("cloverbench_array_copy_strong", "precondition"),
    ("diffy_condn", "loop invariant"),
    ("mbpp_task_id_3", "postcondition"),
    ("mbpp_task_id_170", "invariant/arithmetic"),
    ("misc_arg_free", "arithmetic/assertion"),
]


def offline_tokenizer():
    model = ROOT / ".cluster/models/Qwen2.5-Coder-14B-Instruct/aedcc2d42b622764e023cf882b6652e646b95671"
    if not model.exists():
        return None, "Local Coder tokenizer not found; no downloads attempted"
    try:
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(str(model), local_files_only=True), None
    except Exception as error:
        return None, str(error)


def excerpt(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit // 2] + "\n[OMITTED MIDDLE; PREVIEW ONLY]\n" + text[-limit // 2:]


def payloads(folder, tokenizer):
    api_path = folder / "api/report.json"
    api = read_json(api_path) if api_path.exists() else {}
    blocks = {"query_smt": (folder / "query.smt2", 6000),
              "model_" + api.get("model_status", "unavailable"): (folder / "api/model.smt2", 3000),
              "quantifier_instances": (folder / "api/instantiations.jsonl", 4000),
              "search_inferences": (folder / "api/search-inferences.jsonl", 4000),
              "statistics": (folder / "cli.statistics.txt", 2000)}
    sizes = {}
    preview = ["Diagnostic preview only. Not sent to an LLM. SMT/JSON excerpts can be incomplete.",
               "No semantic source mapping or auxiliary LLM is used.",
               json.dumps({k: api.get(k) for k in ("result", "reason_unknown", "model_status")}), ""]
    for label, (path, cap) in blocks.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        sizes[label] = {"file": str(path), "available": path.exists(), "characters": len(text),
                        "bytes": len(text.encode("utf-8")),
                        "tokens": len(tokenizer.encode(text, add_special_tokens=False)) if tokenizer else None}
        preview += [f"=== {label} ===", excerpt(text, cap) or "UNAVAILABLE OR EMPTY", ""]
    rendered = "\n".join(preview)
    write_text(folder / "package-preview.txt", rendered)
    sizes["preview"] = {"characters": len(rendered), "bytes": len(rendered.encode("utf-8")),
                        "tokens": len(tokenizer.encode(rendered, add_special_tokens=False)) if tokenizer else None}
    write_json(folder / "payload-sizes.json", sizes)
    return sizes


def api_probe(query_file, destination, timeout_ms, max_events):
    destination = Path(destination)
    call = execute([sys.executable, "-m", "diagnostics.z3_probe", "worker",
                    "--query", str(query_file), "--output", str(destination), "--mode", "api",
                    "--timeout-ms", str(timeout_ms), "--max-events", str(max_events)],
                   timeout_ms / 1000 + 20)
    write_json(destination.parent / "api-process.json", call)
    return read_json(destination / "report.json") if (destination / "report.json").exists() else {
        "status": "unavailable", "error": "Worker failed; inspect api-process.json"}


def repeated_replays(folder, query, z3, args):
    runs = []
    for index in range(args.repeats):
        target = folder / "repeat-cli" / f"run-{index:02}"
        target.mkdir(parents=True)
        runs.append(cli_replay(z3, query, target, args.timeout_ms))
    results = [item["result"] for item in runs]
    report = {"runs": runs, "results": results,
              "consistent_observed_results": bool(results) and None not in results and len(set(results)) == 1,
              "scope": "repeated CLI replays, not identical search traces or validated models"}
    write_json(folder / "stability.json", report)
    return report


def control(name, out, z3, args, tokenizer):
    source = ROOT / "diagnostics/z3" / f"{name}.smt2"
    prefix, check = list(snapshots(source.read_text(encoding="utf-8")))[0]
    folder = out / "controls" / name
    folder.mkdir(parents=True)
    write_text(folder / "prefix.smt2", prefix)
    write_text(folder / "query.smt2", prefix + check + "\n")
    query = {"prefix_file": str(folder / "prefix.smt2"), "check_command": check,
             "scope": "standalone SMT control; not a captured Verus query", "expected_result": "sat",
             "source_sha256": digest(source.read_bytes()),
             "inspect_terms": ["x", "(>= x 0)", "(> x 0)"] if name == "sat_arithmetic" else ["(f 0)"]}
    write_json(folder / "query.json", query)
    cli = cli_replay(z3, query, folder, args.timeout_ms)
    api = api_probe(folder / "query.json", folder / "api", args.timeout_ms, args.max_events)
    stable = repeated_replays(folder, query, z3, args)
    sizes = payloads(folder, tokenizer)
    return {"name": name, "scope": query["scope"], "expected": "sat", "cli": cli, "api": api,
            "stability": stable, "payload_sizes": sizes, "folder": str(folder)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", default="results/qwen25coder14b-v3-150/seed-20261018/full/instruct")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout-ms", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-events", type=int, default=100)
    args = parser.parse_args()
    if args.repeats < 1 or args.max_events < 1 or args.timeout_ms < 1:
        parser.error("Limits and repeats must be positive")
    if sys.platform != "linux":
        parser.error("Run this experiment on the Linux cluster")
    out = Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("Use a new empty output directory")
    out.mkdir(parents=True, exist_ok=True)
    z3 = str(Path(os.environ["Z3_BIN"]).resolve())
    tokenizer, tokenizer_error = offline_tokenizer()
    report = {"llm_calls": 0, "source_run": str(Path(args.source_run).resolve()),
              "z3_binary": z3, "z3_sha256": digest(Path(z3).read_bytes()),
              "z3_version": execute([z3, "--version"], 10),
              "tokenizer_status": "available_offline" if tokenizer else "unavailable",
              "tokenizer_error": tokenizer_error, "controls": [], "cases": []}
    for name in ("sat_arithmetic", "sat_quantified"):
        try:
            report["controls"].append(control(name, out, z3, args, tokenizer))
        except Exception as error:
            report["controls"].append({"name": name, "status": "error", "error": str(error)})

    candidates = [("verus_arithmetic_control", ROOT / "diagnostics/z3/arithmetic_gap.rs", "artificial Verus control")]
    for task_id, kind in CASES:
        source = Path(args.source_run).resolve() / task_id / "attempt_00/candidate.rs"
        candidates.append((task_id, source, kind))
    for name, source, kind in candidates:
        case = {"name": name, "kind": kind, "source": str(source), "queries": []}
        folder = out / "verus-cases" / name
        if not source.is_file():
            case.update(status="missing", reason="Saved candidate not found; no replacement generated")
            report["cases"].append(case)
            continue
        # A child process isolates the transparent proxy's environment per case.
        call = execute([sys.executable, "-m", "diagnostics.z3_probe", "run", "--source", str(source),
                        "--output", str(folder), "--max-queries", "1", "--max-events", str(args.max_events),
                        "--timeout-ms", str(args.timeout_ms)], 360)
        write_json(out / f"{name}-process.json", call)
        if not (folder / "report.json").exists():
            case.update(status="error", reason="Capture failed or process timed out; inspect process log")
        else:
            captured = read_json(folder / "report.json")
            case.update(status=captured["status"], original_counts=captured["query_counts"],
                        capture_errors=captured["capture_errors"])
            for entry in captured["selected_queries"]:
                query_folder = Path(entry["folder"])
                case["queries"].append({"original_result": entry["original_result"], "cli": entry["cli"],
                    "api": entry["api"]["api"], "folder": str(query_folder),
                    "stability": repeated_replays(query_folder, entry, z3, args),
                    "payload_sizes": payloads(query_folder, tokenizer)})
        report["cases"].append(case)
        write_json(out / "progress.json", report)

    arithmetic = next((item for item in report["controls"] if item["name"] == "sat_arithmetic"), {})
    report["sat_control_confirmed"] = arithmetic.get("cli", {}).get("model_is_confirmed_sat", False)
    report["real_cases_available"] = sum(case["name"] != "verus_arithmetic_control" and
                                         case["status"] != "missing" for case in report["cases"])
    write_json(out / "report.json", report)
    lines = ["# Solver exposure study", "", f"Arithmetic SAT model confirmed: {report['sat_control_confirmed']}",
             f"Real saved candidates available: {report['real_cases_available']}/5", "No LLM calls.", "",
             "SAT in a standalone control is not evidence of SAT in a Verus obligation.", "",
             "| Case | Scope | Original/CLI | API | Instantiations | Other search events sampled |",
             "|---|---|---|---|---:|---:|"]
    for item in report["controls"]:
        api = item.get("api", {})
        lines.append(f"| {item['name']} | SMT control | {item.get('cli', {}).get('result', 'error')} | {api.get('result', api.get('status'))} | {api.get('instantiations_observed', 0)} | {api.get('sampled_buckets', {}).get('other_inferences', 0)} |")
    for case in report["cases"]:
        if not case["queries"]:
            lines.append(f"| {case['name']} | {case['kind']} | {case['status']} | unavailable | 0 | 0 |")
        for query in case["queries"]:
            api = query["api"]
            lines.append(f"| {case['name']} | {case['kind']} | {query['original_result']} | {api.get('result', api['status'])} | {api.get('instantiations_observed', 0)} | {api.get('sampled_buckets', {}).get('other_inferences', 0)} |")
    lines += ["", "Inspect cli.values.txt in controls for concrete values and truth values.",
              "Each query has stability.json, payload-sizes.json and package-preview.txt.",
              "Preview excerpts can be incomplete; full data remains in the corresponding files.",
              "Models after UNKNOWN are unvalidated; empty models are labeled separately.",
              "Other search events are raw hints, not automatically classified or validated Verus lemmas."]
    write_text(out / "report.md", "\n".join(lines) + "\n")
    print(f"Study complete: {out / 'report.md'}", flush=True)
    return 0 if report["sat_control_confirmed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
