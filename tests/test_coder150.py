import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from baseline.__main__ import validate_config
from baseline.benchmark import load_tasks
from baseline.integrity import lexical_check
from baseline.prompts import ROOT, build_messages
from baseline.runner import run_task
from baseline.storage import read_json
from baseline.verifier import Verifier
from test_pipeline import SOURCE, FakeInference, FakeVerifier, FakeIntegrity


class Coder150Tests(unittest.TestCase):
    def test_full_config_and_original_reference(self):
        config = read_json(ROOT / "configs/qwen25coder14b-v3-150.json")
        validate_config(config, "full")
        self.assertEqual(len(load_tasks(ROOT / "data/manifest.json")), 150)
        self.assertEqual(config["max_repairs"], 2)
        messages = build_messages("ALTERED CANDIDATE", "error", "v3", original=SOURCE)
        self.assertIn(SOURCE, messages[1]["content"])
        self.assertIn("ALTERED CANDIDATE", messages[1]["content"])
        self.assertIn("Vec indexing expects int", messages[0]["content"])
        with self.assertRaises(ValueError):
            validate_config(config, "pilot")

    def test_integrity_feedback_reaches_repair_and_resume_is_identical(self):
        config = read_json(ROOT / "configs/qwen25coder14b-v3-150.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "original.rs"
            source.write_text(SOURCE, encoding="utf8")
            task = {"id": "test", "category": "Misc", "file": str(source)}
            inference = FakeInference()
            result = run_task(task, config, root / "out", inference, FakeVerifier(), FakeIntegrity(False))
            self.assertFalse(result["success"])
            self.assertEqual(len(inference.calls), 3)
            self.assertIn("Rejected: TEST ONLY", inference.calls[1][1]["content"])
            self.assertIn("<original_program>", inference.calls[1][1]["content"])
            resumed = FakeInference()
            self.assertEqual(run_task(task, config, root / "out", resumed, FakeVerifier(), FakeIntegrity(False))["attempts"], result["attempts"])
            self.assertEqual(resumed.calls, [])

    def test_import_rejection_names_the_change(self):
        valid, reason = lexical_check(SOURCE, SOURCE.replace("use vstd::prelude::*;", ""))
        self.assertFalse(valid)
        self.assertIn("imports", reason)
        self.assertIn("vstd", reason)

    def test_expected_type_is_not_syntax(self):
        result = {"returncode": 1, "timed_out": False, "seconds": 0,
                  "stdout": "", "stderr": "error[E0308]: mismatched types\nexpected `int`, found `usize`"}
        with patch("baseline.verifier.execute", return_value=result):
            self.assertEqual(Verifier("fake").verify(Path("test.rs"))["error_type"], "compilation")
