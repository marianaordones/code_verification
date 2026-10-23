import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from baseline.inference import MODEL, REVISION, prepare_model


class ModelDownloadTests(unittest.TestCase):
    def test_download_uses_local_files_and_pinned_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def download(**kwargs):
                destination = Path(kwargs["local_dir"])
                destination.mkdir(parents=True)
                for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "weights.safetensors"):
                    (destination / name).write_bytes(b"test data")
                (destination / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"x": "weights.safetensors"}}))
            mocked = Mock(side_effect=download)
            with patch("baseline.inference.ROOT", root), patch.dict("sys.modules", {"huggingface_hub": SimpleNamespace(snapshot_download=mocked)}):
                result = prepare_model()
            self.assertEqual(result, str(root / ".cluster/models/Qwen3-8B" / REVISION))
            self.assertEqual(mocked.call_args.kwargs, {"repo_id": MODEL, "revision": REVISION,
                                                      "local_dir": result, "max_workers": 1})

    def test_missing_weight_shard_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / ".cluster/models/Qwen3-8B" / REVISION
            destination.mkdir(parents=True)
            (destination / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"x": "missing.safetensors"}}))
            with patch("baseline.inference.ROOT", root), patch.dict("sys.modules", {"huggingface_hub": SimpleNamespace(snapshot_download=Mock())}):
                with self.assertRaisesRegex(RuntimeError, "Incomplete model download"):
                    prepare_model()
