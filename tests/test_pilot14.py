import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from baseline.__main__ import validate_config
from baseline.benchmark import pilot10_selection
from baseline.inference import LocalVLLM, MODEL_14B, REVISION_14B, model_identity, prepare_model
from baseline.integrity import IntegrityValidator
from baseline.prompts import ROOT, build_messages
from baseline.storage import read_json
from baseline.verifier import Verifier


class Pilot14Tests(unittest.TestCase):
    def test_configs_use_same_frozen_ten_tasks_and_model(self):
        original = read_json(ROOT / "data/pilot.json")
        selected = read_json(ROOT / "data/pilot-qwen14b-v2-10.json")
        self.assertEqual(selected["task_ids"], original["task_ids"][:10])
        self.assertEqual(selected, pilot10_selection(ROOT / "data/manifest.json", ROOT / "data/pilot.json"))
        configs = [read_json(ROOT / f"configs/qwen14b-v2-{mode}.json") for mode in ("thinking", "nonthinking")]
        for config in configs:
            validate_config(config, "pilot")
            self.assertEqual(model_identity(config), (MODEL_14B, REVISION_14B))
            self.assertEqual(config["pilot_size"], 10)
            self.assertEqual(config["prompt_version"], "v2")
        self.assertEqual(configs[0]["task_selection"], configs[1]["task_selection"])

    def test_both_prompts_get_the_v2_syntax_guide(self):
        for feedback in (None, "latest diagnostic"):
            messages = build_messages("CURRENT CODE", feedback, "v2")
            self.assertEqual(len(messages), 2)
            self.assertIn("BEFORE the opening brace", messages[0]["content"])
            self.assertIn("forall|k: int|", messages[0]["content"])
            self.assertIn("CURRENT CODE", messages[1]["content"])
            if feedback:
                self.assertIn(feedback, messages[1]["content"])
        self.assertNotIn("Verus syntax reference", build_messages("code")[0]["content"])

    def test_engine_loads_local_14b_with_one_sequence(self):
        config = read_json(ROOT / "configs/qwen14b-v2-thinking.json")
        constructor = Mock()
        with patch.dict("sys.modules", {"vllm": SimpleNamespace(LLM=constructor)}), patch(
                "baseline.inference.prepare_model", return_value="/local/pinned-14b") as download:
            LocalVLLM(config)
        download.assert_called_once_with(MODEL_14B, REVISION_14B)
        args = constructor.call_args.kwargs
        self.assertEqual(args["model"], "/local/pinned-14b")
        self.assertEqual(args["tokenizer"], "/local/pinned-14b")
        self.assertEqual(args["dtype"], "bfloat16")
        self.assertEqual(args["max_num_seqs"], 1)
        self.assertEqual(args["tensor_parallel_size"], 1)
        self.assertEqual(args["max_model_len"], 32768)

    def test_14b_download_keeps_revision_and_separate_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            def download(**kwargs):
                destination = Path(kwargs["local_dir"])
                destination.mkdir(parents=True)
                for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "part.safetensors"):
                    (destination / name).write_bytes(b"test")
                (destination / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"x": "part.safetensors"}}))
            mocked = Mock(side_effect=download)
            with patch("baseline.inference.ROOT", Path(directory)), patch.dict("sys.modules", {
                    "huggingface_hub": SimpleNamespace(snapshot_download=mocked)}):
                destination = prepare_model(MODEL_14B, REVISION_14B)
            self.assertIn("Qwen3-14B", destination)
            self.assertEqual(mocked.call_args.kwargs["revision"], REVISION_14B)

    def test_compiler_error_with_zero_verification_errors_is_compilation(self):
        base = {"returncode": 1, "timed_out": False, "seconds": 0.1,
                "stdout": "verification results:: 0 verified, 0 errors",
                "stderr": "error: cannot find macro `verus` in this scope"}
        with patch("baseline.verifier.execute", return_value=base):
            result = Verifier("unused").verify(ROOT / "candidate.rs")
        self.assertEqual(result["error_type"], "compilation")
        self.assertFalse(result["success"])
        with patch("baseline.verifier.execute", return_value={**base, "stderr": "error: expected curly braces"}):
            self.assertEqual(Verifier("unused").verify(ROOT / "candidate.rs")["error_type"], "syntax")

    def test_parser_panic_is_checker_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.rs"
            source.write_text("fn main() {}")
            with patch("baseline.integrity.execute", return_value={
                    "returncode": 101, "timed_out": False, "seconds": 0.1,
                    "stdout": "", "stderr": "thread 'main' panicked at parser"}):
                result = IntegrityValidator("unused").validate(source, source)
            self.assertFalse(result["valid"])
            self.assertEqual(result["status"], "checker_error")
