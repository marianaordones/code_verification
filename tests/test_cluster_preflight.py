import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.cluster.preflight import main


class ClusterPreflightTests(unittest.TestCase):
    def check_failure(self, visible, count, available, message):
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(device_count=lambda: count, is_available=lambda: available))
        with patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": visible}), patch.dict(
                "sys.modules", {"torch": fake_torch, "transformers": SimpleNamespace(), "vllm": SimpleNamespace()}):
            with self.assertRaisesRegex(SystemExit, message):
                main()

    def test_no_slurm_gpu_fails_before_loading_model(self):
        self.check_failure("", 0, False, "did not assign")

    def test_multiple_visible_gpus_are_not_used_accidentally(self):
        self.check_failure("0,1", 2, True, "Expected one logical GPU")

    def test_cuda_unavailable_is_reported(self):
        self.check_failure("0", 1, False, "CUDA unavailable")
