import random
import unittest

from baseline.__main__ import validate_config
from baseline.benchmark import SEED, pilot50_selection
from baseline.prompts import ROOT
from baseline.storage import read_json


class Pilot50Tests(unittest.TestCase):
    def test_frozen_selection_is_a_sample_of_all_150_ids(self):
        expected = pilot50_selection(ROOT / "data/manifest.json")
        frozen = read_json(ROOT / "data/pilot-qwen14b-v2-50.json")
        self.assertEqual(expected, frozen)
        pool = sorted(t["id"] for t in read_json(ROOT / "data/manifest.json")["tasks"])
        self.assertEqual(frozen["task_ids"], sorted(random.Random(SEED).sample(pool, 50)))
        self.assertEqual(len(set(frozen["task_ids"])), 50)
        self.assertEqual(sum(frozen["category_counts"].values()), 50)
        self.assertNotIn("ranking", frozen)
        self.assertNotIn("excluded", frozen)

    def test_both_modes_use_50_tasks_with_same_model_and_prompt(self):
        configs = [read_json(ROOT / f"configs/qwen14b-v2-50-{mode}.json")
                   for mode in ("thinking", "nonthinking")]
        for config in configs:
            validate_config(config, "pilot")
            self.assertEqual(config["pilot_size"], 50)
            self.assertEqual(config["model"], "Qwen/Qwen3-14B")
            self.assertEqual(config["prompt_version"], "v2")
            self.assertEqual(config["max_repairs"], 2)
        for key in ("task_selection", "model_revision", "seed", "experiment"):
            self.assertEqual(configs[0][key], configs[1][key])
        self.assertEqual(configs[0]["max_tokens"], 8192)
        self.assertEqual(configs[1]["max_tokens"], 4096)
