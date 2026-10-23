"""Recheck saved candidates without generation or modification of the source run."""
import os
from pathlib import Path
import json

from .benchmark import load_tasks
from .evaluation import single_report
from .integrity import IntegrityValidator, POLICY
from .prompts import ROOT
from .provenance import command, file_hashes, tool_identity, tool_signature
from .storage import digest, read_json, write_json, write_text
from .verifier import Verifier


def revalidate(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Use a separate output directory outside the original run")
    metadata = read_json(source / "run.json")
    if metadata["stage"] == "revalidation":
        raise ValueError("Revalidate the original generation run, not a revalidation")
    official = {t["id"]: t for t in load_tasks(ROOT / "data/manifest.json")}
    selected = metadata["tasks"]
    ids = [t["id"] for t in selected]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate task IDs")
    for task in selected:
        if task["id"] not in official or task["sha256"] != official[task["id"]]["sha256"]:
            raise ValueError("Saved task does not match the official input")

    tools = {name: tool_identity(os.environ[variable]) for name, variable in
             (("verus", "VERUS_BIN"), ("z3", "Z3_BIN"), ("lynette", "LYNETTE_BIN"))}
    for name in ("verus", "z3"):
        if tools[name]["sha256"] != metadata["provenance"][name]["sha256"]:
            raise ValueError(f"Revalidation requires the original {name} binary")
    os.environ["VERUS_Z3_PATH"] = tools["z3"]["path"]
    verifier = Verifier(tools["verus"]["path"], metadata["config"]["verification_timeout"])
    integrity = IntegrityValidator(tools["lynette"]["path"])

    # Freeze the snapshot, including candidate hashes. A growing source run
    # requires a fresh output directory; never silently mix two snapshots.
    completed = {}
    hashes = {"run.json": digest((source / "run.json").read_bytes())}
    for task_id in ids:
        path = source / task_id / "task.json"
        if not path.exists():
            continue
        task = read_json(path)
        if task["id"] != task_id:
            raise ValueError("Saved task ID differs")
        completed[task_id] = task
        hashes[path.relative_to(source).as_posix()] = digest(path.read_bytes())
        for index, attempt in enumerate(task["attempts"]):
            if attempt["attempt"] != index or index > metadata["config"]["max_repairs"]:
                raise ValueError("Saved attempt sequence/budget differs")
            for name in ("candidate.rs", "result.json"):
                saved = source / task_id / f"attempt_{index:02}" / name
                if not saved.resolve().is_relative_to(source):
                    raise ValueError("Saved candidate is outside the source run")
                hashes[saved.relative_to(source).as_posix()] = digest(saved.read_bytes())
            if read_json(source / task_id / f"attempt_{index:02}/result.json") != attempt:
                raise ValueError("Task and attempt records disagree")
    stable = {"policy": POLICY, "source_files": hashes,
              "sources": file_hashes((ROOT / "baseline").glob("*.py")),
              "tools": {k: tool_signature(v) for k, v in tools.items()}}
    fingerprint = digest(json.dumps(stable, sort_keys=True).encode())
    output.mkdir(parents=True, exist_ok=True)
    if (output / "run.json").exists():
        if read_json(output / "run.json")["fingerprint"] != fingerprint:
            raise ValueError("Snapshot, tools or evaluator changed; use a new output directory")
    else:
        if any(path.name != ".lock" for path in output.iterdir()):
            raise ValueError("Use an empty output directory")
        config = {**metadata["config"], "evaluation_policy": POLICY}
        provenance = {**metadata["provenance"], **tools}
        write_json(output / "run.json", {
            "stage": "revalidation", "config": config, "tasks": selected,
            "provenance": provenance, "fingerprint": fingerprint,
            "revalidation": {**stable, "source_run": str(source),
                             "original_fingerprint": metadata["fingerprint"],
                             "verus_version": command([tools["verus"]["path"], "--version"]),
                             "no_inference": True}})
    errors = 0
    for task_id, task in completed.items():
        attempts = []
        try:
            for saved in task["attempts"]:
                index = saved["attempt"]
                folder = output / task_id / f"attempt_{index:02}"
                if (folder / "result.json").exists():
                    record = read_json(folder / "result.json")
                    expected_hash = hashes[f"{task_id}/attempt_{index:02}/candidate.rs"]
                    if (record["candidate_sha256"] != expected_hash
                            or digest((folder / "candidate.rs").read_bytes()) != expected_hash):
                        raise ValueError("Revalidated candidate changed")
                    attempts.append(record)
                    continue
                source_candidate = source / task_id / f"attempt_{index:02}/candidate.rs"
                folder.mkdir(parents=True, exist_ok=True)
                candidate = folder / "candidate.rs"
                candidate_bytes = source_candidate.read_bytes()
                if digest(candidate_bytes) != hashes[f"{task_id}/attempt_{index:02}/candidate.rs"]:
                    raise ValueError("Source candidate changed during revalidation")
                candidate.write_bytes(candidate_bytes)
                verification = verifier.verify(candidate)
                check = integrity.validate(Path(official[task_id]["file"]), candidate)
                write_json(folder / "verification.json", verification)
                write_text(folder / "verus.stdout.txt", verification["stdout"])
                write_text(folder / "verus.stderr.txt", verification["stderr"])
                write_json(folder / "integrity.json", check)
                record = {**saved, "success": verification["success"] and check["valid"],
                          "invalid_modification": check["status"] == "invalid",
                          "integrity_status": check["status"], "error_type": verification["error_type"],
                          "verification_seconds": verification["seconds"],
                          "integrity_seconds": check["seconds"],
                          "total_seconds": saved["inference_seconds"] + verification["seconds"] + check["seconds"],
                          "revalidation_seconds": verification["seconds"] + check["seconds"],
                          "original_success": saved["success"],
                          "candidate_sha256": digest(candidate.read_bytes())}
                write_json(folder / "result.json", record)
                attempts.append(record)
            successes = [a["attempt"] for a in attempts if a["success"]]
            write_json(output / task_id / "task.json", {
                "id": task_id, "category": official[task_id]["category"],
                "attempts": attempts, "success": bool(successes),
                "first_success": min(successes) if successes else None,
                "total_seconds": sum(a["total_seconds"] for a in attempts),
                "original_success": task["success"]})
            print(task_id, "success" if successes else "failed", flush=True)
        except Exception as error:
            errors += 1
            write_json(output / task_id / "task_error.json",
                       {"type": type(error).__name__, "message": str(error)})
    summary = single_report(output)
    write_json(output / "revalidation-summary.json", {
        "original_solved_in_snapshot": sum(t["success"] for t in completed.values()),
        "revalidated_solved": summary["solved"], "completed_source_tasks": len(completed),
        "new_inference_calls": 0, "infrastructure_errors": errors,
        "revalidation_seconds": sum(a["revalidation_seconds"] for task_id in completed
                                    if (output / task_id / "task.json").exists()
                                    for a in read_json(output / task_id / "task.json")["attempts"])})
    return 1 if errors else 0
