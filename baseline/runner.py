import time
from pathlib import Path

from .feedback import ConventionalFeedbackProvider
from .inference import extract_code
from .prompts import build_messages
from .storage import digest, read_json, write_json, write_text


def run_task(task, config, output, inference, verifier, integrity, feedback=None):
    feedback = feedback or ConventionalFeedbackProvider()
    root = Path(output) / task["id"]
    original = Path(task["file"])
    current = original.read_text(encoding="utf-8")
    original_code = current
    latest = None
    attempts = []
    started = time.perf_counter()
    for index in range(config["max_repairs"] + 1):
        folder = root / f"attempt_{index:02}"
        folder.mkdir(parents=True, exist_ok=True)
        record_path = folder / "result.json"
        if record_path.exists():
            record = read_json(record_path)
        else:
            attempt_started = time.perf_counter()
            messages = build_messages(current, latest, config.get("prompt_version", "v1"),
                                      original=original_code)
            request = {"messages": messages, "parameters": config,
                       "seed": config["seed"] + index,
                       "input_sha256": digest(original.read_bytes())}
            request_path = folder / "request.json"
            if request_path.exists() and read_json(request_path) != request:
                raise ValueError("Saved request differs; use a new run directory")
            write_json(request_path, request)
            response_path = folder / "response.json"
            if response_path.exists():
                response = read_json(response_path)
            else:
                response = inference.generate(messages, config, request["seed"])
                write_json(response_path, response)
            write_text(folder / "response.txt", response["text"])
            write_text(folder / "rendered_prompt.txt", response["rendered_prompt"])
            code = extract_code(response["text"], config["enable_thinking"])
            source = folder / "candidate.rs"
            write_text(source, code)
            # Always collect ordinary Verus output, even when integrity rejects.
            verification = verifier.verify(source)
            check = integrity.validate(original, source)
            write_json(folder / "verification.json", verification)
            write_text(folder / "verus.stdout.txt", verification["stdout"])
            write_text(folder / "verus.stderr.txt", verification["stderr"])
            write_json(folder / "integrity.json", check)
            record = {"attempt": index, "success": verification["success"] and check["valid"],
                      "invalid_modification": check.get("status", "valid" if check["valid"] else "invalid") == "invalid",
                      "integrity_status": check.get("status", "valid" if check["valid"] else "invalid"),
                      "error_type": verification["error_type"],
                      "verification_seconds": verification["seconds"],
                      "integrity_seconds": check["seconds"],
                      "total_seconds": response["inference_seconds"] + verification["seconds"] + check["seconds"],
                      "processing_session_seconds": time.perf_counter() - attempt_started,
                      **{k: response[k] for k in ("input_tokens", "output_tokens", "reasoning_tokens",
                                                  "final_tokens", "inference_seconds", "truncated", "seed")}}
            write_json(record_path, record)
        attempts.append(record)
        if record["success"]:
            break
        verification = read_json(folder / "verification.json")
        candidate = (folder / "candidate.rs").read_text(encoding="utf-8")
        # No extracted final answer means there is no new program to repair.
        # Keep the previous current program, without a hidden extra generation.
        if candidate.strip():
            current = candidate
        latest = feedback.extract(verification)
        # Opt-in v3 experiment: ordinary integrity diagnostics, no solver internals.
        if config.get("integrity_feedback", False):
            check = read_json(folder / "integrity.json")
            latest += ("\n\n<integrity_diagnostics>\n"
                       + ("Valid: original program preserved." if check["valid"] else
                          "Rejected: " + check["reason"])
                       + "\n</integrity_diagnostics>")
        if config.get("solver_feedback") == "obligation" and index < config["max_repairs"]:
            from .obligation import solver_feedback
            saved_feedback = folder / "solver/feedback.txt"
            latest = (saved_feedback.read_text(encoding="utf-8") if saved_feedback.exists() else
                      solver_feedback(folder, current, latest, original_code, inference, config))
        if config.get("solver_feedback") == "internals" and index < config["max_repairs"]:
            from .internals import internal_feedback
            saved_feedback = folder / "internals/feedback.txt"
            latest = (saved_feedback.read_text(encoding="utf-8") if saved_feedback.exists() else
                      internal_feedback(folder, current, latest, original_code, inference, config))
            if "solver_feedback_seconds" not in record:
                seconds = read_json(folder / "internals/exposure.json")["seconds"]
                record["solver_feedback_seconds"] = seconds
                record["total_seconds"] += seconds
                write_json(record_path, record)
    result = {"id": task["id"], "category": task["category"], "attempts": attempts,
              "success": any(a["success"] for a in attempts),
              "first_success": next((a["attempt"] for a in attempts if a["success"]), None),
              "total_seconds": sum(a["total_seconds"] for a in attempts),
              "active_session_seconds": time.perf_counter() - started}
    write_json(root / "task.json", result)
    return result
