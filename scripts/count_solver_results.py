"""Count original solver outcomes saved by experiment B. Standard library only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys


DEFAULT_RUN = (Path(__file__).resolve().parents[1] /
               "results/qwen25coder14b-b-150/seed-20261018/full/instruct")


def summarize(root):
    paths = sorted(root.glob("*/attempt_*/solver/report.json"))
    if not paths:
        raise ValueError("No solver/report.json files found in " + str(root))
    totals = Counter({s: 0 for s in ("sat", "unsat", "unknown", "timeout")})
    capture_errors = wall_timeouts = no_queries = 0
    problems = set()
    read_errors = []
    for path in paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            counts = Counter(q["result"] for q in report["queries"])
            if set(counts) - set(totals):
                raise ValueError("Unexpected solver outcome")
            errors = len(report["capture_errors"])
            interrupted = bool(report["verus_wall_timeout"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            read_errors.append({"file": str(path), "error": str(error)})
            continue
        totals.update(counts)
        capture_errors += errors
        wall_timeouts += interrupted
        no_queries += not report["queries"]
        problems.add(path.parent.parent.parent.name)
    return {"run_directory": str(root), "query_results": dict(totals),
            "total_queries": sum(totals.values()), "reports_found": len(paths),
            "reports_read": len(paths) - len(read_errors),
            "problems_with_reports": len(problems),
            "reports_without_queries": no_queries, "capture_errors": capture_errors,
            "verus_wall_timeouts": wall_timeouts, "read_errors": read_errors,
            "scope": "Original captured queries across all saved attempts, not distinct problems. "
                     "Unknown is not reclassified as timeout. Capture errors may make counts incomplete."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", nargs="?", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, help="Also save the summary as JSON")
    args = parser.parse_args()
    try:
        report = summarize(args.run_directory.resolve())
    except ValueError as error:
        parser.exit(1, str(error) + "\nCheck the experiment directory.\n")
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 1 if report["read_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
