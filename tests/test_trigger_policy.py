from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from baseline.integrity import lexical_check, IntegrityValidator
from baseline.revalidate import revalidate
from baseline.storage import write_json, read_json, digest
from baseline.benchmark import load_tasks
from baseline.prompts import ROOT
from baseline.__main__ import validate_config

SOURCE = "use vstd::prelude::*; fn main() {} verus! { fn f(a: Vec<u64>) { } }"


class TriggerPolicyTests(unittest.TestCase):
    def test_allow_only_additional_trigger_annotations(self):
        for annotation in ("#[trigger]", "#[trigger(0)]", "#![auto]"):
            candidate = SOURCE.replace("fn f", "proof fn lemma() { assert(forall|j: int| " + annotation + " j == j); } fn f")
            self.assertTrue(lexical_check(SOURCE, candidate)[0], annotation)
        for annotation in ("#[verifier::external_body]", "#[verifier::rlimit(999)]", "#[allow(unused)]", "#[trigger(fake)]", "#[trigger = false]"):
            self.assertFalse(lexical_check(SOURCE, SOURCE.replace("fn f", annotation + " fn f"))[0], annotation)
        original = SOURCE.replace("fn f", "#[trigger] fn f")
        self.assertFalse(lexical_check(original, SOURCE)[0])

    def test_attributes_in_comments_and_strings_are_not_exemptions(self):
        self.assertFalse(lexical_check(SOURCE, SOURCE.replace("fn f", "#[allow(unused)] /* #[trigger] */ fn f"))[0])
        self.assertFalse(lexical_check(SOURCE, SOURCE + ' const X: &str = "assume"; assume(false);')[0])

    def test_lynette_still_checks_candidate_with_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, candidate = Path(tmp)/"original.rs", Path(tmp)/"candidate.rs"
            original.write_text(SOURCE)
            candidate.write_text(SOURCE.replace("fn f", "proof fn p() { assert(forall|j:int| #[trigger] j == j); } fn f"))
            with patch("baseline.integrity.execute", return_value={"returncode":1,"timed_out":False,"seconds":0,"stdout":"Disallowed changes detected", "stderr":""}) as execute:
                self.assertFalse(IntegrityValidator("fake").validate(original, candidate)["valid"])
                execute.assert_called_once()
                self.assertEqual(execute.call_args.args[0][-1], str(candidate.resolve()))

    def test_v4_configuration(self):
        config = read_json(ROOT / "configs/qwen25coder14b-v4-150.json")
        validate_config(config, "full")
        self.assertEqual(config["max_repairs"], 2)

    def test_revalidation_is_separate_resumable_and_freezes_candidates(self):
        task = load_tasks(ROOT / "data/manifest.json")[0]
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/"old", Path(tmp)/"new"
            folder = source/task["id"]/"attempt_00"
            folder.mkdir(parents=True)
            (folder/"candidate.rs").write_text(SOURCE)
            attempt = {"attempt":0, "success":False, "invalid_modification":True,
                       "integrity_status":"invalid", "error_type":None,
                       "verification_seconds":1, "integrity_seconds":0, "total_seconds":3,
                       "inference_seconds":2,"input_tokens":10,"output_tokens":5,
                       "reasoning_tokens":0,"final_tokens":5,"truncated":False}
            write_json(folder/"result.json", attempt)
            write_json(source/task["id"]/"task.json", {"id":task["id"],"category":task["category"],"success":False,"attempts":[attempt]})
            tools = {name:{"path":str(Path(tmp)/name),"sha256":name} for name in ("verus","z3","lynette")}
            write_json(source/"run.json", {"stage":"full", "config":{"max_repairs":2,"mode":"instruct","model":"TEST","verification_timeout":120},
                       "tasks":[task], "fingerprint":"original", "provenance":{**tools,"gpu":"TEST"}})
            original_bytes = {str(p.relative_to(source)):p.read_bytes() for p in source.rglob("*") if p.is_file()}
            verification = {"success":True,"seconds":1,"error_type":None,"stdout":"verification results:: 1 verified, 0 errors", "stderr":""}
            check = {"valid":True,"status":"valid","seconds":0,"reason":""}
            with patch.dict("os.environ", {"VERUS_BIN":"verus", "Z3_BIN":"z3", "LYNETTE_BIN":"lynette"}), patch("baseline.revalidate.tool_identity", side_effect=lambda name:tools[name]), patch("baseline.revalidate.command", return_value={}), patch("baseline.revalidate.Verifier.verify", return_value=verification) as verify, patch("baseline.revalidate.IntegrityValidator.validate",return_value=check):
                self.assertEqual(revalidate(source, output), 0)
                self.assertEqual(read_json(output/"summary.json")["solved"],1)
                self.assertEqual(read_json(output/"revalidation-summary.json")["new_inference_calls"],0)
                self.assertEqual(revalidate(source, output), 0)
                self.assertEqual(verify.call_count,1)
                self.assertEqual(original_bytes, {str(p.relative_to(source)):p.read_bytes() for p in source.rglob("*") if p.is_file()})
                (folder/"candidate.rs").write_text(SOURCE+"\n")
                with self.assertRaises(ValueError):
                    revalidate(source, output)
                with self.assertRaises(ValueError):
                    revalidate(source, source/"nested")
