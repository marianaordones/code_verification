from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.cluster.prepare_ipc import prepare, probe


class ClusterIPCTests(unittest.TestCase):
    def test_uses_only_a_directory_that_passes_the_socket_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / 'bad', root / 'good'
            first.mkdir()
            second.mkdir()
            with patch('scripts.cluster.prepare_ipc.probe', side_effect=[OSError('Input/output error'), None]) as check:
                selected = prepare([str(first), str(second)])
            self.assertEqual(selected.parent, second.resolve())
            self.assertEqual(check.call_count, 2)
            self.assertEqual(list(first.iterdir()), [])

    def test_no_silent_home_fallback_when_all_probes_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch('scripts.cluster.prepare_ipc.probe', side_effect=OSError('unsupported')):
                with self.assertRaisesRegex(RuntimeError, 'CLUSTER_IPC_TMP'):
                    prepare([temporary])
            self.assertEqual(list(Path(temporary).iterdir()), [])

    @unittest.skipUnless(sys.platform == 'linux', 'Real IPC socket probe requires Linux')
    def test_real_zmq_socket(self):
        try:
            import zmq
        except ImportError:
            self.skipTest('pyzmq not installed')
        with tempfile.TemporaryDirectory(dir='/tmp') as temporary:
            probe(Path(temporary))


if __name__ == '__main__':
    unittest.main()
