"""Choose a short, working IPC directory independently of large pip temporaries."""
import os
from pathlib import Path
import sys
import tempfile
import uuid


def probe(folder):
    import zmq
    path = folder / str(uuid.uuid4())
    # vLLM appends a UUID too. Stay below Linux's Unix-socket pathname limit.
    if len(os.fsencode(path)) > 100:
        raise ValueError("IPC path is too long; use a shorter local scratch path")
    context = zmq.Context()
    sender = context.socket(zmq.PAIR)
    receiver = context.socket(zmq.PAIR)
    try:
        sender.setsockopt(zmq.SNDTIMEO, 2000)
        receiver.setsockopt(zmq.RCVTIMEO, 2000)
        address = "ipc://" + str(path)
        receiver.bind(address)
        sender.connect(address)
        sender.send(b"verus-ipc-test")
        if receiver.recv() != b"verus-ipc-test":
            raise RuntimeError("IPC message mismatch")
    finally:
        sender.close(linger=0)
        receiver.close(linger=0)
        context.term()
        path.unlink(missing_ok=True)


def prepare(candidates):
    failures = []
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        parent = Path(candidate).resolve()
        if parent in seen:
            continue
        seen.add(parent)
        if not parent.is_dir():
            continue
        work = None
        try:
            work = Path(tempfile.mkdtemp(prefix="vipc-", dir=parent))
            probe(work)
            return work
        except Exception as error:
            failures.append(f"{parent}: {type(error).__name__}: {error}")
            if work is not None:
                try:
                    work.rmdir()  # Only the empty directory just created by this call.
                except OSError:
                    pass
    raise RuntimeError("No working local ZMQ IPC directory. Set CLUSTER_IPC_TMP to a short "
                       "node-local path. Probes: " + "; ".join(failures))


def main():
    if sys.platform != "linux":
        raise SystemExit("Cluster IPC setup requires Linux")
    try:
        folder = prepare([os.environ.get("CLUSTER_IPC_TMP"), "/tmp", "/var/tmp",
                          os.environ.get("SLURM_TMPDIR")])
    except RuntimeError as error:
        raise SystemExit(str(error))
    print(folder)


if __name__ == "__main__":
    main()
