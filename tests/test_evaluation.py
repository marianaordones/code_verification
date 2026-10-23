from pathlib import Path
import tempfile
import unittest

from baseline.evaluation import aggregate, pilot_report, single_report
from baseline.storage import read_json, write_json
from baseline.prompts import ROOT


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        tasks = read_json(ROOT / "data/manifest.json")["tasks"]
        ids = read_json(ROOT / "data/pilot.json")["task_ids"]
        self.tasks = [t for t in tasks if t["id"] in ids]
        self.dirs = []
        for mode in ("thinking", "nonthinking"):
            folder = self.root / mode
            self.dirs.append(folder)
            provenance = {key: "TEST" for key in ("sources", "prompts", "verus", "z3", "lynette", "model_revision", "versions", "gpu")}
            write_json(folder / "run.json", {"config": {"mode": mode, "max_repairs": 2},
                                             "stage": "pilot", "tasks": self.tasks,
                                             "fingerprint": "TEST", "provenance": provenance})
            for task in self.tasks:
                attempt = {"success": True, "attempt": 0, "inference_seconds": 2, "total_seconds": 3,
                           "verification_seconds": 1, "input_tokens": 10, "output_tokens": 5,
                           "reasoning_tokens": 0, "final_tokens": 5, "truncated": False,
                           "invalid_modification": False, "error_type": None}
                write_json(folder / task["id"] / "task.json", {"id": task["id"], "category": task["category"],
                           "success": True, "first_success": 0, "total_seconds": 3, "attempts": [attempt]})

    def test_single_configuration_report(self):
        folder = self.dirs[0]
        metadata = read_json(folder / "run.json")
        metadata["config"].update(mode="instruct", model="Qwen/Qwen2.5-Coder-14B-Instruct", prompt_version="v2")
        write_json(folder / "run.json", metadata)
        summary = single_report(folder)
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["solved"], 15)
        self.assertIn("Qwen2.5-Coder-14B-Instruct", (folder / "report.md").read_text(encoding="utf-8"))
        self.assertTrue((folder / "summary.json").exists())

    def test_report_separates_type_notes_from_syntax_headers(self):
        folder = self.dirs[0]
        write_json(folder / self.tasks[0]["id"] / "attempt_00/verification.json", {
            "stdout": "", "stderr": "error[E0308]: mismatched types\nexpected `int`, found `usize`"})
        summary = aggregate(folder)
        self.assertEqual(summary["diagnostics"]["problems_with_syntax_errors"], 0)
        self.assertEqual(summary["diagnostics"]["problems_with_type_mismatches"], 1)

    def test_complete_paired_report_and_categories(self):
        output = self.root / "report"
        report = pilot_report(*self.dirs, output)
        self.assertTrue(report["complete"])
        self.assertEqual(report["paired_outcomes"], {"(True, True)": 15})
        self.assertEqual(len(report["summaries"][0]["categories"]), 4)
        self.assertIn("piloto maior", report["recommendation"])
        self.assertIn("Success@3", output.with_suffix(".md").read_text(encoding="utf-8"))

    def test_infrastructure_missing_tasks_not_hidden(self):
        path = self.dirs[0] / self.tasks[0]["id"] / "task.json"
        path.unlink()
        report = pilot_report(*self.dirs, self.root / "report")
        self.assertFalse(report["complete"])
        self.assertEqual(report["summaries"][0]["completed_tasks"], 14)
        self.assertEqual(report["summaries"][0]["expected_tasks"], 15)
        self.assertIn("incompleta", report["recommendation"])

    def test_mismatched_pilot_tasks_are_rejected(self):
        path = self.dirs[1] / "run.json"
        metadata = read_json(path)
        metadata["tasks"] = metadata["tasks"][:-1]
        write_json(path, metadata)
        with self.assertRaises(ValueError):
            pilot_report(*self.dirs, self.root / "report")

    def test_other_gpu_class_does_not_prevent_resuming_or_reporting(self):
        path = self.dirs[1] / "run.json"
        metadata = read_json(path)
        metadata["provenance"]["gpu"] = "OTHER GPU CLASS"
        write_json(path, metadata)
        report = pilot_report(*self.dirs, self.root / "report")
        self.assertTrue(report["complete"])
        self.assertFalse(report["hardware_comparable"])
        self.assertIn("hardware", report["recommendation"])

    def test_staged_tool_paths_can_change_without_changing_binary_identity(self):
        for index, folder in enumerate(self.dirs):
            path = folder / "run.json"
            metadata = read_json(path)
            for tool in ("verus", "z3", "lynette"):
                metadata["provenance"][tool] = {"path": f"/tmp/job-{index}/{tool}", "sha256": tool}
            write_json(path, metadata)
        self.assertTrue(pilot_report(*self.dirs, self.root / "report")["complete"])

    def test_report_accepts_ten_task_14b_pilot_and_correct_title(self):
        for mode, folder in zip(("thinking", "nonthinking"), self.dirs):
            path = folder / "run.json"
            metadata = read_json(path)
            metadata["tasks"] = metadata["tasks"][:10]
            metadata["config"] = read_json(ROOT / f"configs/qwen14b-v2-{mode}.json")
            write_json(path, metadata)
        output = self.root / "report14"
        report = pilot_report(*self.dirs, output)
        self.assertTrue(report["complete"])
        self.assertEqual(report["summaries"][0]["expected_tasks"], 10)
        text = output.with_suffix(".md").read_text(encoding="utf-8")
        self.assertIn("Qwen/Qwen3-14B", text)
        self.assertIn("10 tarefas", text)
        self.assertIn("prompt v2", text)

    def test_report_accepts_fifty_task_pilot(self):
        ids = read_json(ROOT / "data/pilot-qwen14b-v2-50.json")["task_ids"]
        by_id = {t["id"]: t for t in read_json(ROOT / "data/manifest.json")["tasks"]}
        for mode, folder in zip(("thinking", "nonthinking"), self.dirs):
            metadata_path = folder / "run.json"
            metadata = read_json(metadata_path)
            template = read_json(folder / self.tasks[0]["id"] / "task.json")
            metadata["tasks"] = [by_id[task_id] for task_id in ids]
            metadata["config"] = read_json(ROOT / f"configs/qwen14b-v2-50-{mode}.json")
            write_json(metadata_path, metadata)
            for task in metadata["tasks"]:
                write_json(folder / task["id"] / "task.json", {
                    **template, "id": task["id"], "category": task["category"]})
        output = self.root / "report50"
        report = pilot_report(*self.dirs, output)
        self.assertTrue(report["complete"])
        self.assertEqual(report["summaries"][0]["expected_tasks"], 50)
        self.assertEqual(report["paired_outcomes"], {"(True, True)": 50})
        self.assertIn("50 tarefas", output.with_suffix(".md").read_text(encoding="utf-8"))
