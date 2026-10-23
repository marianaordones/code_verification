import json
from pathlib import Path
import tempfile
import unittest

from diagnostics.b_audit import audit, classify_missing, measure_feedback, replace_obligation


class CharacterTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {"tokenize": True, "add_generation_prompt": True}
        return list("".join(m["content"] for m in messages))


class BAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "run/task/attempt_00"
        (self.folder / "solver").mkdir(parents=True)
        self.report = {"queries": [], "capture_errors": [], "verus_wall_timeout": False}

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_queries_use_compiler_diagnostics_not_integrity(self):
        self.put(self.folder / "verification.json", {"error_type": "compilation", "stdout": "",
                 "stderr": "error[E0308]: mismatched types\nexpected int found usize"})
        self.put(self.folder / "integrity.json", {"status": "valid"})
        (self.folder / "candidate.rs").write_text("candidate")
        row = classify_missing(self.folder, self.report)
        self.assertEqual(row["category"], "type_mismatch_E0308")
        self.assertEqual(row["integrity_status"], "valid")
        self.assertFalse(row["empty_candidate"])
        self.report["capture_errors"] = ["capture failed"]
        self.assertEqual(classify_missing(self.folder, self.report)["category"], "capture_error")

    def test_exact_prompt_tokens_include_output_reserve_and_full_query(self):
        self.report["queries"] = [{"id": "q0", "file": "q0.smt2", "result": "unknown"},
                                  {"id": "q1", "file": "q1.smt2", "result": "unsat"}]
        (self.folder / "solver/q0.smt2").write_text('(declare-const x Int)\n(assert (> x 0))\n(check-sat)\n')
        (self.folder / "solver/q1.smt2").write_text('(check-sat)')
        self.put(self.folder / "solver/exposure.json", {"omission_reason": "complete_queries_exceed_context_budget"})
        self.put(self.folder.parent / "attempt_01/request.json", {
            "messages": [{"role": "system", "content": "original system"}, {"role": "user", "content":
                "original and candidate\n<solver_obligations>\nRead only\nQuery counts: {'unknown': 1}. Capture errors: 0.\n"
                "No complete query fits\n</solver_obligations>\nreturn Rust"}],
            "parameters": {"max_tokens": 40}})
        rows, measurement = measure_feedback(self.folder, self.report, CharacterTokenizer(), [1, 10000])
        self.assertEqual(len(rows), 1)  # Never substitute a smaller UNSAT for a failing query.
        self.assertEqual(rows[0]["required_context_tokens"], rows[0]["prompt_tokens"] + 40)
        self.assertIsNone(measurement["selected_query_at_1"])
        self.assertEqual(measurement["selected_query_at_10000"], "q0")
        self.put(self.folder / "solver/report.json", self.report)
        out = self.root / "out"
        out.mkdir()
        summary = audit(self.root / "run", out, CharacterTokenizer(), [1, 10000])
        self.assertEqual(summary["errors"], [])
        self.assertEqual(summary["context_coverage"]["10000"]["additional_feedbacks_previously_omitted_for_size"], 1)
        self.assertTrue((out / "query-token-budgets.csv").exists())

    def test_prompt_replacement_is_scoped_and_rejects_missing_block(self):
        messages = [{"role": "user", "content": "before<solver_obligations>old</solver_obligations>after"}]
        changed = replace_obligation(messages, "<solver_obligations>new</solver_obligations>")
        self.assertEqual(changed[0]["content"], "before<solver_obligations>new</solver_obligations>after")
        self.assertIn("old", messages[0]["content"])
        with self.assertRaises(ValueError):
            replace_obligation([{"role": "user", "content": "no feedback"}], "new")


if __name__ == "__main__":
    unittest.main()
