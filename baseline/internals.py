"""Compact solver-internals feedback, with no full SMT query in the prompt."""
import json
import time

from diagnostics.z3_internals import replay
from .prompts import build_messages
from .storage import read_json, write_json, write_text

STATISTICS = ("quant instantiations", "conflicts", "decisions", "propagations",
              "arith conflicts", "rlimit count", "time")


def render(payload):
    return "\n\n<solver_internals>\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n</solver_internals>"


def pack(report, replay_report, selected):
    original = selected["result"] if selected else None
    concordant = (selected is not None and replay_report.get("status") == "completed"
                  and replay_report.get("result") == original)
    return {"schema": "z3-internals-v1", "scope": "diagnostic_api_replay_not_original_search",
            "availability": "available" if concordant else "unavailable_or_result_mismatch",
            "original_query_counts": {s: sum(q["result"] == s for q in report["queries"])
                                      for s in ("sat", "unsat", "unknown", "timeout")},
            "capture_errors": len(report["capture_errors"]),
            "query_id": selected["id"] if selected else None,
            "original_result": original, "replay_result": replay_report.get("result"),
            "reason_unknown": replay_report.get("reason_unknown"),
            "replay_timeout_ms": replay_report.get("timeout_ms"),
            "unavailability_reason": None if concordant else (
                "no_captured_sat_or_unknown_query" if selected is None else
                "replay_result_mismatch" if replay_report.get("status") == "completed" else
                "replay_unavailable_inspect_saved_logs"),
            "statistics": {key: replay_report.get("statistics", {}).get(key) if concordant else None
                           for key in STATISTICS},
            "sampling": {"instantiations_observed": replay_report.get("instantiations_observed"),
                         "instantiations_saved": replay_report.get("instantiations_saved"),
                         "callback_errors": replay_report.get("callback_errors"),
                         "groups_in_prompt": 0, "instances_in_prompt": 0,
                         "policy": "first fitting events; at most 10 distinct quantifiers and 3 instances each; complete formulas only"},
            "quantifiers": []}


def select_events(payload, events, fits):
    # Quantifier text is repeated only once. Binding order is not guessed/relabelled.
    for event in events:
        quantifier = event["quantifier_smt"]
        group = next((g for g in payload["quantifiers"] if g["quantifier_smt"] == quantifier), None)
        if group is None and len(payload["quantifiers"]) >= 10:
            continue
        if group is not None and len(group["instances"]) >= 3:
            continue
        if group is None:
            group = {"id": f"Q{len(payload['quantifiers']) + 1}", "quantifier_smt": quantifier, "instances": []}
            payload["quantifiers"].append(group)
        instance = {key: event[key] for key in ("binding_terms_callback_order", "clause_literals_smt")}
        if instance in group["instances"]:
            continue
        group["instances"].append(instance)
        payload["sampling"]["groups_in_prompt"] = len(payload["quantifiers"])
        payload["sampling"]["instances_in_prompt"] = sum(len(g["instances"]) for g in payload["quantifiers"])
        if not fits(payload):
            group["instances"].pop()
            if not group["instances"]:
                payload["quantifiers"].remove(group)
    payload["sampling"]["groups_in_prompt"] = len(payload["quantifiers"])
    payload["sampling"]["instances_in_prompt"] = sum(len(g["instances"]) for g in payload["quantifiers"])
    return payload


def internal_feedback(folder, current, conventional, original, inference, config):
    started = time.perf_counter()
    root = folder / "internals"
    root.mkdir(parents=True, exist_ok=True)
    report = read_json(folder / "solver/report.json")
    selected = next((q for q in report["queries"] if q["result"] in ("sat", "unknown")), None)
    replay_report = {"status": "not_run", "error": "No captured SAT/UNKNOWN query"}
    if selected:
        replay_report = replay(folder / "solver" / selected["file"], root / "replay", config["replay_timeout_ms"])
    payload = pack(report, replay_report, selected)
    tokenizer = inference.tokenizer

    def fits(value):
        extra = render(value)
        block_tokens = len(tokenizer.encode(extra, add_special_tokens=False))
        if block_tokens > config["internals_token_budget"]:
            return False
        messages = build_messages(current, conventional + extra, config["prompt_version"], original=original)
        full_tokens = len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
        return full_tokens + config["max_tokens"] <= config.get("max_model_len", 32768)

    if not fits(payload):
        # Keep the saved raw reason, but omit an unusually long reason as a whole from the prompt.
        payload["reason_unknown"] = None
        payload["unavailability_reason"] = "Metadata exceeds token budget; reason omitted if present"
    if not fits(payload):
        raise ValueError("Repair prompt with minimum solver metadata exceeds the token budget")
    path = root / "replay/instantiations.jsonl"
    events = []
    if payload["availability"] == "available" and path.exists():
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = select_events(payload, events, fits)
    if not fits(payload):
        raise ValueError("Internal feedback budget invariant violated")
    extra = render(payload)
    seconds = time.perf_counter() - started
    write_json(root / "payload.json", payload)
    write_json(root / "exposure.json", {"seconds": seconds,
               "extra_tokens": len(tokenizer.encode(extra, add_special_tokens=False)),
               "has_instances": bool(payload["quantifiers"]),
               "statistics_available": any(v is not None for v in payload["statistics"].values()),
               "availability": payload["availability"], "query_id": payload["query_id"]})
    feedback = conventional + extra
    write_text(root / "feedback.txt", feedback)
    return feedback
