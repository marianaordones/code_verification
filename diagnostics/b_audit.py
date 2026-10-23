"""Offline audit of experiment B: missing queries and complete-prompt token budgets."""
import argparse
from collections import Counter
import copy
import csv
import hashlib
import json
from pathlib import Path
import re
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "results/qwen25coder14b-b-150/seed-20261018/full/instruct"
DEFAULT_TOKENIZER = ROOT / ".cluster/models/Qwen2.5-Coder-14B-Instruct/aedcc2d42b622764e023cf882b6652e646b95671"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def csv_rows(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def classify_missing(folder, report):
    verification = read(folder / "verification.json")
    integrity = read(folder / "integrity.json") if (folder / "integrity.json").exists() else {}
    text = verification.get("stdout", "") + "\n" + verification.get("stderr", "")
    headers = [line for line in text.splitlines() if re.match(r"^error(?:\[|:)", line)]
    codes = sorted(set(re.findall(r"error\[(E\d+)\]", text)))
    kind = verification.get("error_type")
    if report["capture_errors"]:
        category = "capture_error"
    elif verification.get("timed_out"):
        category = "verus_wall_timeout"
    elif kind == "syntax":
        category = "syntax"
    elif "E0308" in codes:
        category = "type_mismatch_E0308"
    elif kind == "compilation":
        category = "other_compilation"
    elif verification.get("success"):
        category = "verus_success_without_queries"
    elif kind == "verification":
        category = "verification_failure_without_queries"
    else:
        category = "other_or_unclassified"
    candidate = folder / "candidate.rs"
    return {"problem": folder.parent.name, "attempt": folder.name, "category": category,
            "verus_error_type": kind, "rust_error_codes": ";".join(codes),
            "empty_candidate": not candidate.read_text(encoding="utf-8").strip() if candidate.exists() else None,
            "integrity_status": integrity.get("status"),
            "repair_feedback_prepared": (folder / "solver/exposure.json").exists(),
            "diagnostic_headers": " | ".join(headers[:8]),
            "verification_file": str(folder / "verification.json")}


def replace_obligation(messages, block):
    messages = copy.deepcopy(messages)
    matches = 0
    for message in messages:
        content = message["content"]
        if "<solver_obligations>" in content:
            if content.count("<solver_obligations>") != 1 or content.count("</solver_obligations>") != 1:
                raise ValueError("Ambiguous saved solver feedback")
            before, rest = content.split("<solver_obligations>", 1)
            _, after = rest.split("</solver_obligations>", 1)
            message["content"] = before + block + after
            matches += 1
    if matches != 1:
        raise ValueError("Expected exactly one solver block in saved next repair request")
    return messages


def measure_feedback(folder, report, tokenizer, contexts):
    index = int(folder.name.split("_")[-1])
    next_folder = folder.parent / f"attempt_{index + 1:02}"
    request = read(next_folder / "request.json")
    messages = request["messages"]
    content = next(m["content"] for m in messages if "<solver_obligations>" in m["content"])
    block = content.split("<solver_obligations>", 1)[1].split("</solver_obligations>", 1)[0]
    counts_line = re.search(r"Query counts: [^\n]*\n", block)
    if not counts_line:
        raise ValueError("Saved solver intro not recognized; refusing approximate reconstruction")
    intro = "<solver_obligations>" + block[:counts_line.end()]
    reserve = request["parameters"]["max_tokens"]
    candidates = [q for q in report["queries"] if q["result"] != "unsat"] or report["queries"]
    actual = len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    response_file = next_folder / "response.json"
    if response_file.exists():
        recorded = read(response_file).get("input_tokens")
        if recorded is not None and recorded != actual:
            raise ValueError(f"Tokenizer/template mismatch: saved input_tokens={recorded}, recounted={actual}")
    rows = []
    for query in candidates:
        path = folder / "solver" / query["file"]
        smt = path.read_text(encoding="utf-8")
        proposed = (intro + f"\nQuery {query['id']}; result={query['result']}\n```smt2\n{smt}```\n"
                    "\nOther queries are saved on disk and not included in this prompt.\n"
                    "\n</solver_obligations>")
        full = replace_obligation(messages, proposed)
        tokens = len(tokenizer.apply_chat_template(full, tokenize=True, add_generation_prompt=True))
        rows.append({"problem": folder.parent.name, "attempt": folder.name, "query": query["id"],
                     "result": query["result"], "prompt_tokens": tokens, "reserved_output_tokens": reserve,
                     "required_context_tokens": tokens + reserve,
                     "query_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    minimum = min((r["required_context_tokens"] for r in rows), default=None)
    measured = {"problem": folder.parent.name, "attempt": folder.name,
                "saved_request_prompt_tokens": actual, "candidate_queries": len(rows),
                "minimum_required_context": minimum,
                "original_omission_reason": read(folder / "solver/exposure.json").get("omission_reason")}
    for size in contexts:
        first = next((r["query"] for r in rows if r["required_context_tokens"] <= size), None)
        measured[f"selected_query_at_{size}"] = first
    return rows, measured


def audit(run, out, tokenizer, contexts):
    paths = sorted(run.glob("*/attempt_*/solver/report.json"))
    if not paths:
        raise ValueError("No solver reports found in " + str(run))
    missing, queries, feedbacks, errors = [], [], [], []
    prepared = without_queries = 0
    for number, path in enumerate(paths, 1):
        folder = path.parent.parent
        try:
            report = read(path)
            if not report["queries"]:
                missing.append(classify_missing(folder, report))
            if (folder / "solver/exposure.json").exists():
                prepared += 1
                without_queries += not report["queries"]
                if tokenizer is not None:
                    rows, measurement = measure_feedback(folder, report, tokenizer, contexts)
                    queries.extend(rows)
                    feedbacks.append(measurement)
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            errors.append({"file": str(path), "error": str(error)})
        if number % 20 == 0:
            print(f"Analyzed {number}/{len(paths)} reports", flush=True)
    summary = {"source_run": str(run), "llm_calls": 0, "solver_calls": 0,
               "reports_found": len(paths), "attempts_without_queries": len(missing),
               "missing_query_categories": dict(Counter(r["category"] for r in missing)),
               "missing_query_categories_for_repair_feedbacks": dict(Counter(
                   r["category"] for r in missing if r["repair_feedback_prepared"])),
               "repair_feedbacks_prepared": prepared, "repair_feedbacks_without_queries": without_queries,
               "measured_feedbacks": len(feedbacks), "context_coverage": {}, "errors": errors,
               "scope": "Offline token fit only, using saved next-repair requests and unchanged complete queries. "
                        "Does not establish model context support, GPU memory feasibility, or repair success. "
                        "Saved queries and future model responses may differ in a new run."}
    for size in contexts:
        fit = [r for r in feedbacks if r[f"selected_query_at_{size}"] is not None]
        recovered = [r for r in fit if r["original_omission_reason"] == "complete_queries_exceed_context_budget"]
        summary["context_coverage"][str(size)] = {
            "feedbacks_with_complete_query": len(fit),
            "additional_feedbacks_previously_omitted_for_size": len(recovered),
            "problems_with_complete_query": len({r["problem"] for r in fit}),
            "percent_of_measured_feedbacks": 100 * len(fit) / len(feedbacks) if feedbacks else None}
    values = sorted(r["minimum_required_context"] for r in feedbacks if r["minimum_required_context"] is not None)
    summary["minimum_required_context_distribution"] = (
        {"min": values[0], "median": median(values), "max": values[-1]} if values else None)
    csv_rows(out / "missing-queries.csv", missing)
    csv_rows(out / "query-token-budgets.csv", queries)
    csv_rows(out / "repair-context-coverage.csv", feedbacks)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, default=DEFAULT_TOKENIZER)
    parser.add_argument("--contexts", nargs="+", type=int, default=[32768, 49152, 65536, 98304, 131072])
    parser.add_argument("--skip-tokenization", action="store_true", help="Only classify missing queries")
    args = parser.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    if run == out or run in out.parents or out in run.parents:
        parser.error("Use an output directory separate from the original results")
    if out.exists() and any(out.iterdir()):
        parser.error("Use a new empty output directory")
    if not args.contexts or min(args.contexts) <= 0:
        parser.error("Contexts must be positive")
    out.mkdir(parents=True, exist_ok=True)
    tokenizer, tokenizer_error = None, None
    if not args.skip_tokenization:
        try:
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer.resolve()), local_files_only=True)
            tokenizer.model_max_length = 10**12  # Count whole inputs without truncation warnings.
        except Exception as error:
            tokenizer_error = str(error)
    try:
        summary = audit(run, out, tokenizer, sorted(set(args.contexts)))
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    summary.update(tokenizer_directory=str(args.tokenizer.resolve()),
                   tokenizer_status="available_offline" if tokenizer else "skipped" if args.skip_tokenization else "unavailable",
                   tokenizer_error=tokenizer_error)
    save(out / "summary.json", summary)
    lines = ["# Experiment B audit", "", "No model inference, solver execution, or changes to saved queries.",
             f"Attempts without queries: {summary['attempts_without_queries']}",
             f"Categories: {summary['missing_query_categories']}",
             f"Categories among prepared repair feedbacks: {summary['missing_query_categories_for_repair_feedbacks']}",
             f"Tokenizer: {summary['tokenizer_status']}", f"Measured feedbacks: {summary['measured_feedbacks']}", "",
             "| Context tokens | Feedbacks with a complete query | Recovered size omissions | Distinct problems |",
             "|---|---|---|---|"]
    for size, row in summary["context_coverage"].items():
        lines.append(f"| {size} | {row['feedbacks_with_complete_query']} | "
                     f"{row['additional_feedbacks_previously_omitted_for_size']} | {row['problems_with_complete_query']} |")
    lines += ["", "Token fit is not a guarantee of model support, GPU feasibility, or improved proofs.",
              "No-query categories are based on saved diagnostics; ambiguous cases are not guessed.",
              "Counts cover saved repair prompts, not hypothetical future repair trajectories.",
              f"Read/measurement errors: {len(summary['errors'])}", f"Tokenizer error: {tokenizer_error}"]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {out / 'report.md'}", flush=True)
    return 1 if summary["errors"] or tokenizer_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
