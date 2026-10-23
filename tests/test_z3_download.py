from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.cluster.download_z3 import PACKAGE, unpack_binary


class Z3UnpackTests(unittest.TestCase):
    def test_only_expected_binary_is_extracted_without_unzip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "z3.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(f"{PACKAGE}/bin/z3", b"test executable")
                bundle.writestr("../unexpected.txt", b"do not extract")
            destination = root / "z3"
            unpack_binary(archive, destination)
            self.assertEqual(destination.read_bytes(), b"test executable")
            self.assertEqual({p.name for p in root.iterdir()}, {"z3", "z3.zip"})

    def test_missing_expected_binary_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "wrong.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("other/bin/z3", b"wrong version")
            with self.assertRaises(KeyError):
                unpack_binary(archive, root / "z3")
            self.assertFalse((root / "z3").exists())
