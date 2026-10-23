import random
import unittest
from baseline.benchmark import coder100_selection, load_tasks, SEED
from baseline.inference import MODEL_CODER, model_identity
from baseline.__main__ import validate_config
from baseline.prompts import ROOT
from baseline.storage import read_json


class Coder100Tests(unittest.TestCase):
    def test_fixed_selection_and_config(self):
        frozen = read_json(ROOT / "data/pilot-qwen25coder14b-v2-100.json")
        self.assertEqual(frozen, coder100_selection(ROOT / "data/manifest.json"))
        pool = sorted(t["id"] for t in load_tasks(ROOT / "data/manifest.json"))
        self.assertEqual(frozen["task_ids"], sorted(random.Random(SEED).sample(pool, 100)))
        self.assertEqual(len(set(frozen["task_ids"])), 100)
        config = read_json(ROOT / "configs/qwen25coder14b-v2-100.json")
        validate_config(config, "pilot")
        self.assertEqual(model_identity(config)[0], MODEL_CODER)
        self.assertEqual(config["mode"], "instruct")
        self.assertFalse(config["enable_thinking"])
        self.assertEqual(config["max_repairs"], 2)
        self.assertEqual(config["prompt_version"], "v2")
