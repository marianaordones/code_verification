import copy
from pathlib import Path
import tempfile
import unittest

from baseline.benchmark import load_tasks, select_pilot
from baseline.evaluation import summarize
from baseline.feedback import ConventionalFeedbackProvider
from baseline.inference import extract_code
from baseline.integrity import lexical_check, tokens
from baseline.prompts import ROOT
from baseline.runner import run_task
from baseline.storage import read_json, write_json
from baseline.__main__ import validate_config


SOURCE = "use vstd::prelude::*; fn main() {} verus! { fn f(x: u64) -> (r:u64) ensures r == x, { x } }"


class FakeInference:
    """Explicit test double; never used by the experiment CLI."""
    def __init__(self):
        self.calls = []

    def generate(self, messages, config, seed):
        self.calls.append(messages)
        return {"text": SOURCE, "rendered_prompt": str(messages), "token_ids": [],
                "input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 0,
                "final_tokens": 50, "inference_seconds": 2.0, "seed": seed,
                "truncated": False, "finish_reason": "stop"}


class FakeVerifier:
    def __init__(self):
        self.calls = 0

    def verify(self, source):
        self.calls += 1
        success = self.calls >= 2
        return {"success": success, "stdout": "verification results:: 1 verified, 0 errors" if success else "",
                "stderr": "" if success else "assertion failed at line 4",
                "seconds": 1.0, "error_type": None if success else "verification"}


class FakeIntegrity:
    def __init__(self, valid=True):
        self.valid = valid

    def validate(self, original, candidate):
        return {"valid": self.valid, "reason": "TEST ONLY", "seconds": 0.5}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "original.rs"
        self.source.write_text(SOURCE, encoding="utf-8")
        self.task = {"id": "test_task", "category": "Misc", "file": str(self.source)}
        self.config = read_json(ROOT / "configs/nonthinking.json")

    def test_generate_repair_logs_and_resume(self):
        inference, verifier = FakeInference(), FakeVerifier()
        result = run_task(self.task, self.config, self.root, inference, verifier, FakeIntegrity())
        self.assertEqual(result["first_success"], 1)
        self.assertEqual(result["total_seconds"], 7.0)
        self.assertEqual(len(inference.calls), 2)
        self.assertEqual(len(inference.calls[1]), 2)
        self.assertIn("assertion failed at line 4", inference.calls[1][1]["content"])
        self.assertNotIn("TEST ONLY", inference.calls[1][1]["content"])
        for index in range(2):
            folder = self.root / "test_task" / f"attempt_{index:02}"
            for name in ("request.json", "response.json", "candidate.rs", "result.json", "verification.json", "integrity.json", "rendered_prompt.txt"):
                self.assertTrue((folder / name).exists())
        resumed = run_task(self.task, self.config, self.root, inference, verifier, FakeIntegrity())
        self.assertEqual(resumed["attempts"], result["attempts"])
        self.assertEqual(len(inference.calls), 2)
        self.assertEqual(verifier.calls, 2)

    def test_response_survives_interruption_before_verification(self):
        inference = FakeInference()
        class Interrupted:
            def verify(self, source):
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            run_task(self.task, self.config, self.root, inference, Interrupted(), FakeIntegrity())
        run_task(self.task, self.config, self.root, inference, FakeVerifier(), FakeIntegrity())
        self.assertEqual(len(inference.calls), 2)  # initial reused, only repair generated

    def test_integrity_is_required_even_if_verus_passes(self):
        result = run_task(self.task, self.config, self.root, FakeInference(), FakeVerifier(), FakeIntegrity(False))
        self.assertFalse(result["success"])
        self.assertEqual(len(result["attempts"]), 3)
        self.assertTrue(all(a["invalid_modification"] for a in result["attempts"]))

    def test_cumulative_metrics_and_cost_include_failed_tasks(self):
        result = run_task(self.task, self.config, self.root, FakeInference(), FakeVerifier(), FakeIntegrity())
        failed = copy.deepcopy(result)
        failed.update(success=False, first_success=None)
        summary = summarize([result, failed], 2, 2)
        self.assertEqual(summary["success_at"]["0"], 0)
        self.assertEqual(summary["success_at"]["1"], 0.5)
        self.assertIsNone(summary["success_at"]["5"])
        self.assertEqual(summary["seconds_per_solved"], 14.0)

    def test_extraction_unfinished_reasoning_is_not_code(self):
        self.assertEqual(extract_code("unfinished thought", True), "")
        self.assertEqual(extract_code("thought</think>```rust\nfn main() {}\n```", True), "fn main() {}")
        self.assertEqual(extract_code("fn main() {}", False), "fn main() {}")

    def test_sampling_protocol_is_fixed(self):
        validate_config(self.config, "pilot")
        self.config["temperature"] = 0.1
        with self.assertRaises(ValueError):
            validate_config(self.config, "pilot")

    def test_benchmark_and_selection_are_frozen_and_inputs_only(self):
        tasks = load_tasks(ROOT / "data/manifest.json")
        self.assertEqual(len(tasks), 150)
        self.assertTrue(all("unverified" in Path(t["file"]).parts for t in tasks))
        self.assertTrue(all("ground_truth" not in t for t in tasks))
        selected = select_pilot(ROOT / "data/manifest.json", self.root / "pilot.json")
        self.assertEqual(selected, read_json(ROOT / "data/pilot.json"))
        self.assertEqual(len(selected["task_ids"]), 15)

    def test_lexical_trust_guards(self):
        self.assertTrue(lexical_check(SOURCE, SOURCE)[0])
        for addition in ("assume(false);", "r#assume(false);", "#[verifier::external_body] proof fn p() {}",
                         "#[cfg(any())]", "use evil::*;", "include!(\"evil.rs\");", "unsafe {}"):
            self.assertFalse(lexical_check(SOURCE, SOURCE + addition)[0], addition)
        self.assertTrue(lexical_check(SOURCE, SOURCE + "/* assume(false); /* nested */ */")[0])
        self.assertIn('r#"not // a comment"#', tokens('r#"not // a comment"#'))

    def test_only_latest_verus_feedback(self):
        self.assertEqual(ConventionalFeedbackProvider().extract({"stdout": "ordinary", "stderr": "error", "solver_stats": "secret"}), "ordinary\nerror")


if __name__ == "__main__":
    unittest.main()
