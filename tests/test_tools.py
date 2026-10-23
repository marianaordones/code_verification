"""Real compiler/integrity smoke tests, run separately on the cluster."""
import os
from pathlib import Path
import tempfile
import unittest

from baseline.integrity import IntegrityValidator
from baseline.verifier import Verifier, execute


@unittest.skipUnless(os.environ.get("VERUS_BIN") and os.environ.get("LYNETTE_BIN"),
                     "Requires real VERUS_BIN and LYNETTE_BIN (cluster)")
class RealToolsTests(unittest.TestCase):
    def test_trigger_annotations_with_real_verus_and_lynette(self):
        original_text = "use vstd::prelude::*; fn main() {} verus! { fn f(a: Vec<u64>) {} }"
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.rs"
            candidate = Path(directory) / "candidate.rs"
            original.write_text(original_text, encoding="utf-8")
            validator = IntegrityValidator(os.environ["LYNETTE_BIN"])
            verifier = Verifier(os.environ["VERUS_BIN"])
            expressions = [
                "forall|j: int| 0 <= j < a@.len() ==> #[trigger] a@[j] == a@[j]",
                "forall|j: int| 0 <= j < a@.len() ==> #[trigger(0)] a@[j] == a@[j]",
                "forall|j: int| #![auto] 0 <= j < a@.len() ==> a@[j] == a@[j]",
            ]
            for expression in expressions:
                code = original_text.replace("fn f(a: Vec<u64>) {}",
                    "fn f(a: Vec<u64>) { proof { assert(" + expression + "); } }")
                candidate.write_text(code, encoding="utf-8")
                result = verifier.verify(candidate)
                self.assertTrue(result["success"], result)
                check = validator.validate(original, candidate)
                self.assertTrue(check["valid"], check)
                # A legitimate proof attribute cannot mask executable changes.
                candidate.write_text(code.replace("proof {", "let extra = 0u64; proof {"), encoding="utf-8")
                self.assertFalse(validator.validate(original, candidate)["valid"])

    def test_valid_proof_and_invalid_mutations(self):
        original_text = """use vstd::prelude::*;
fn main() {}
verus! {
fn f(x: u64) -> (r: u64) ensures r == x, { x }
}
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, candidate = root / "original.rs", root / "candidate.rs"
            original.write_text(original_text, encoding="utf-8")
            validator = IntegrityValidator(os.environ["LYNETTE_BIN"])
            verifier = Verifier(os.environ["VERUS_BIN"])
            valid = original_text.replace("{ x }", "{ proof { assert(x == x); } x }")
            candidate.write_text(valid, encoding="utf-8")
            self.assertTrue(verifier.verify(candidate)["success"])
            self.assertTrue(validator.validate(original, candidate)["valid"])
            # Exercise AST checks: changing implementation/contracts, extra exec
            # after final item, and trusted mechanisms in added proof functions.
            mutations = [original_text.replace("{ x }", "{ 0 }"),
                         original_text.replace("ensures r == x,", "ensures true,"),
                         original_text.replace("ensures r == x,", "requires x > 0, ensures r == x,"),
                         original_text + "fn extra() {}",
                         original_text.replace("\n}", "\nfn extra() {}\n}"),
                         original_text + "verus! { proof fn p() { assume(false); } }"]
            for mutation in mutations:
                candidate.write_text(mutation, encoding="utf-8")
                self.assertFalse(validator.validate(original, candidate)["valid"], mutation)
            # New verified auxiliary lemma at the end is allowed.
            candidate.write_text(original_text.replace("\n}", "\nproof fn lemma() ensures 1int == 1int, {}\n}"), encoding="utf-8")
            self.assertTrue(validator.validate(original, candidate)["valid"])
            self.assertTrue(verifier.verify(candidate)["success"])


class ProcessTests(unittest.TestCase):
    def test_timeout_is_failure_and_output_is_preserved(self):
        import sys
        result = execute([sys.executable, "-c", "import time; print('started', flush=True); time.sleep(5)"], 0.1)
        self.assertTrue(result["timed_out"])
        self.assertIn("timeout", result["stderr"])


if __name__ == "__main__":
    unittest.main()
