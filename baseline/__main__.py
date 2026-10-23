import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import time

from .benchmark import load_tasks, select_pilot, pilot10_selection, pilot50_selection, coder100_selection
from .evaluation import aggregate, pilot_report, single_report
from .inference import LocalVLLM, model_identity, MODEL_14B, MODEL_CODER
from .integrity import IntegrityValidator
from .prompts import ROOT
from .provenance import collect, tool_signature
from .runner import run_task
from .storage import digest, read_json, write_json
from .verifier import Verifier


@contextmanager
def run_lock(folder):
    # Kernel lock is released even after SIGKILL/preemption; no stale PID lock.
    if sys.platform != "linux":
        raise ValueError("Real experiments require Linux/vLLM; run unittest locally")
    import fcntl
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another process owns this run directory") from None
        yield


def validate_config(config, stage):
    model, _ = model_identity(config)
    sizes = {"qwen14b-v2-10": 10, "qwen14b-v2-50": 50}
    if config.get("experiment") in sizes:
        count = sizes[config["experiment"]]
        if (model != MODEL_14B or config.get("prompt_version") != "v2"
                or config.get("pilot_size") != count or config.get("max_num_seqs") != 1
                or config.get("task_selection") != f"data/pilot-qwen14b-v2-{count}.json"):
            raise ValueError(f"Unexpected configuration for the 14B/v2/{count}-task pilot")
    if config.get("experiment") == "qwen25coder14b-v2-100":
        if (model != MODEL_CODER or config.get("prompt_version") != "v2"
                or config.get("pilot_size") != 100 or config.get("max_num_seqs") != 1
                or config.get("task_selection") != "data/pilot-qwen25coder14b-v2-100.json"
                or config.get("mode") != "instruct" or stage == "baseline"):
            raise ValueError("Unexpected configuration for the Coder/100-task experiment")
    full_versions = {"qwen25coder14b-v3-150": "v3", "qwen25coder14b-v4-150": "v4",
                     "qwen25coder14b-b-150": "v4", "qwen25coder14b-b-96k-150": "v4",
                     "qwen25coder14b-c-internals-150": "v4-internals"}
    b_experiments = ("qwen25coder14b-b-150", "qwen25coder14b-b-96k-150")
    if config.get("experiment") in b_experiments and config.get("solver_feedback") != "obligation":
        raise ValueError("Experiment B requires obligation feedback")
    if config.get("experiment") == "qwen25coder14b-c-internals-150":
        if (config.get("solver_feedback") != "internals" or config.get("replay_timeout_ms") != 5000
                or config.get("internals_token_budget") != 12288):
            raise ValueError("Unexpected experiment C replay/feedback configuration")
    elif config.get("solver_feedback") and config.get("experiment") not in b_experiments:
        raise ValueError("Solver feedback requires the separate experiment B configuration")
    if config.get("experiment") == "qwen25coder14b-b-96k-150":
        if (config.get("max_model_len") != 98304
                or config.get("rope_scaling") != {"rope_type": "yarn", "factor": 4.0,
                                                  "original_max_position_embeddings": 32768}
                or config.get("cpu_offload_gb") != 12
                or config.get("enable_chunked_prefill") is not True
                or config.get("max_num_batched_tokens") != 2048):
            raise ValueError("Unexpected 96k context/memory configuration")
    elif config.get("max_model_len", 32768) != 32768 or "rope_scaling" in config:
        raise ValueError("Extended context requires the separate experiment B/96k configuration")
    if stage == "full" or config.get("experiment") in full_versions:
        if (config.get("experiment") not in full_versions
                or stage not in ("full", "smoke") or model != MODEL_CODER
                or config.get("prompt_version") != full_versions.get(config.get("experiment")) or config.get("mode") != "instruct"
                or config.get("max_num_seqs") != 1 or config.get("task_count") != 150
                or config.get("integrity_feedback") is not True):
            raise ValueError("Unexpected configuration for the full Coder/v3 experiment")
    mode = config["mode"]
    expected = {"thinking": (True, 0.6, 0.95, 8192), "nonthinking": (False, 0.7, 0.8, 4096),
                "instruct": (False, 0.7, 0.8, 4096)}
    actual = tuple(config[k] for k in ("enable_thinking", "temperature", "top_p", "max_tokens"))
    if mode not in expected or actual != expected[mode] or config["top_k"] != 20:
        raise ValueError("Sampling differs from the predeclared operational configurations")
    if config["seed"] != 20261018 or config["max_repairs"] != (5 if stage == "baseline" else 2):
        raise ValueError("Unexpected seed/repair budget")


def run(args):
    config = read_json(args.config)
    for key, variable in (("verus", "VERUS_BIN"), ("z3", "Z3_BIN"), ("lynette", "LYNETTE_BIN")):
        if os.environ.get(variable):
            config[key] = os.environ[variable]
    if args.stage == "baseline":
        config["max_repairs"] = 5
    validate_config(config, args.stage)
    tasks = load_tasks(ROOT / "data/manifest.json")
    if args.stage == "pilot":
        selection_path = ROOT / config.get("task_selection", "data/pilot.json")
        selection = read_json(selection_path)
        if config.get("experiment") == "qwen25coder14b-v2-100":
            expected_selection = coder100_selection(ROOT / "data/manifest.json")
        elif config.get("experiment") == "qwen14b-v2-50":
            expected_selection = pilot50_selection(ROOT / "data/manifest.json")
        elif config.get("experiment") == "qwen14b-v2-10":
            expected_selection = pilot10_selection(ROOT / "data/manifest.json", ROOT / "data/pilot.json")
        else:
            expected_selection = select_pilot(ROOT / "data/manifest.json", ROOT / "data/pilot.json")
        if selection != expected_selection:
            raise ValueError("Pilot selection changed")
        by_id = {task["id"]: task for task in tasks}
        tasks = [by_id[task_id] for task_id in selection["task_ids"]]
        if len(tasks) != config.get("pilot_size", 15):
            raise ValueError("Pilot task count does not match configuration")
        if args.task:
            raise ValueError("Use --stage smoke for subsets; the pilot requires the frozen task selection")
    elif args.stage == "full":
        if args.task or len(tasks) != 150:
            raise ValueError("The full experiment requires all 150 official tasks")
        tasks = sorted(tasks, key=lambda task: task["id"])
    elif args.stage == "smoke":
        if not args.task:
            raise ValueError("Specify one or two --task IDs for a real integration smoke test")
        if len(args.task) > 2 or not set(args.task) <= {t["id"] for t in tasks}:
            raise ValueError("Unknown task or more than two smoke-test tasks")
        tasks = [t for t in tasks if t["id"] in args.task]
    else:
        if args.task:
            raise ValueError("The full baseline requires all 150 tasks")
        if not args.decision:
            raise ValueError("Baseline requires --decision after reviewing the real pilot")
        decision = read_json(args.decision)
        report_path = Path(decision["pilot_report"])
        report = read_json(report_path)
        if (decision["mode"] != config["mode"] or not decision["rationale"].strip()
                or digest(report_path.read_bytes()) != decision["pilot_report_sha256"] or not report["complete"]):
            raise ValueError("Decision does not identify a complete pilot report and selected mode")
    model, revision = model_identity(config)
    print(f"Model={model}; revision={revision}; prompt={config.get('prompt_version', 'v1')}; "
          f"mode={config['mode']}; stage={args.stage}; tasks={len(tasks)}", flush=True)
    provenance = collect(config)
    # Node-local staging paths are ephemeral. Requests/configuration remain
    # resumable by identifying executables by content, while provenance logs
    # the actual paths used in this session.
    for name in ("verus", "z3", "lynette"):
        config[name] = "sha256:" + provenance[name]["sha256"]
    # Force Verus to use the exact Z3 whose version and hash were recorded.
    os.environ["VERUS_Z3_PATH"] = provenance["z3"]["path"]
    stable = {"stage": args.stage, "config": config,
              "tasks": [{k: v for k, v in t.items() if k != "file"} for t in tasks],
              "provenance": {k: provenance[k] for k in ("sources", "prompts", "verus", "z3", "lynette", "versions", "model_revision", "cluster_requirements", "dependency_lock_sha256")}}
    import json
    for name in ("verus", "z3", "lynette"):
        stable["provenance"][name] = tool_signature(stable["provenance"][name])
    if config.get("solver_feedback") == "internals":
        stable["provenance"]["solver_api"] = provenance["solver_api"]
    fingerprint = digest(json.dumps(stable, sort_keys=True).encode())
    output = Path(args.output)
    with run_lock(output):
        metadata_path = output / "run.json"
        if metadata_path.exists():
            metadata = read_json(metadata_path)
            if metadata["fingerprint"] != fingerprint:
                raise ValueError("Run configuration, inputs or tools changed. Use a new output directory")
        else:
            write_json(metadata_path, {**stable, "provenance": provenance, "fingerprint": fingerprint,
                                       "decision": read_json(args.decision) if args.decision else None})
        engine_started = time.perf_counter()
        inference = LocalVLLM(config)
        session_path = output / f"session_{time.time_ns()}.json"
        session = {"provenance": provenance, "model_load_seconds": time.perf_counter() - engine_started}
        write_json(session_path, session)
        verifier = Verifier(provenance["verus"]["path"], config["verification_timeout"])
        if config.get("solver_feedback") in ("obligation", "internals"):
            from .obligation import ObligationVerifier
            verifier = ObligationVerifier(provenance["verus"]["path"], provenance["z3"]["path"],
                                          config["verification_timeout"])
        integrity = IntegrityValidator(provenance["lynette"]["path"])
        errors = 0
        for task in tasks:
            try:
                result = run_task(task, config, output, inference, verifier, integrity)
                print(task["id"], "success" if result["success"] else "failed", flush=True)
            except Exception as error:
                errors += 1
                write_json(output / task["id"] / "task_error.json",
                           {"type": type(error).__name__, "message": str(error)})
                print(task["id"], "infrastructure error:", error, file=sys.stderr, flush=True)
        session["wall_seconds_including_model_load"] = time.perf_counter() - engine_started
        write_json(session_path, session)
        summary = aggregate(output)
        print(f"Completed {summary['completed_tasks']}/{summary['expected_tasks']}; solved {summary['solved']}")
        return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description="Qwen3 / Verus conventional-feedback baseline")
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select")
    select.add_argument("--output", default=str(ROOT / "data/pilot.json"))
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--stage", choices=["smoke", "pilot", "baseline", "full"], required=True)
    run_parser.add_argument("--task", action="append")
    run_parser.add_argument("--decision")
    report = sub.add_parser("report")
    report.add_argument("--thinking", required=True)
    report.add_argument("--nonthinking", required=True)
    report.add_argument("--output", required=True)
    single = sub.add_parser("single-report")
    single.add_argument("run_directory")
    recheck = sub.add_parser("revalidate")
    recheck.add_argument("--source", required=True)
    recheck.add_argument("--output", required=True)
    summary = sub.add_parser("aggregate")
    summary.add_argument("run_directory")
    args = parser.parse_args()
    if args.command == "select":
        print(select_pilot(ROOT / "data/manifest.json", args.output))
    elif args.command == "run":
        return run(args)
    elif args.command == "report":
        pilot_report(args.thinking, args.nonthinking, args.output)
    elif args.command == "revalidate":
        from .revalidate import revalidate
        source_path, output_path = Path(args.source).resolve(), Path(args.output).resolve()
        if (source_path == output_path or source_path in output_path.parents
                or output_path in source_path.parents):
            raise ValueError("Use a separate output directory outside the original run")
        with run_lock(Path(args.output)):
            return revalidate(args.source, args.output)
    elif args.command == "single-report":
        single_report(args.run_directory)
    else:
        print(aggregate(args.run_directory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
