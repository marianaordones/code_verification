import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys

from .inference import model_identity
from .prompts import ROOT, prompt_directory
from .storage import digest


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": str(error)}


def file_hashes(paths):
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths)}


def tool_identity(executable):
    resolved = shutil.which(executable)
    if not resolved:
        raise ValueError(f"Executable not found: {executable}")
    return {"path": str(Path(resolved).resolve()), "sha256": digest(Path(resolved).read_bytes())}


def tool_signature(value):
    """Scratch paths change per job; binary hashes and versions define identity."""
    return {key: item for key, item in value.items() if key != "path"} if isinstance(value, dict) else value


def collect(config):
    model, revision = model_identity(config)
    versions = {name: importlib.metadata.version(name) for name in ("vllm", "transformers", "torch")}
    if versions["vllm"] != "0.8.5" or versions["transformers"] != "4.51.3":
        raise ValueError("GPU dependencies differ from requirements-gpu.txt")
    verus, z3, lynette = (tool_identity(config[k]) for k in ("verus", "z3", "lynette"))
    verus["version"] = command([verus["path"], "--version"])
    z3["version"] = command([z3["path"], "--version"])
    # Require the built Verus version to identify the benchmark-compatible revision.
    version_text = str(verus["version"])
    if "33269ac" not in version_text:
        raise ValueError("Verus must identify commit 33269ac (see docs/cluster.md)")
    import torch
    device = torch.cuda.get_device_properties(0)
    logical_gpu = {"name": device.name, "memory_bytes": device.total_memory,
                   "compute_capability": [device.major, device.minor],
                   "cuda_build": torch.version.cuda}
    gpu_uuid = str(getattr(device, "uuid", ""))
    gpu_query = ["nvidia-smi", "--query-gpu=name,uuid,memory.total,driver_version", "--format=csv"]
    if gpu_uuid.startswith("GPU-"):
        gpu_query.extend(["-i", gpu_uuid])
    result = {"python": sys.version, "platform": platform.platform(), "hostname": socket.gethostname(), "model": model,
            "model_revision": revision, "dtype": "bfloat16", "versions": versions,
            "pip_freeze": command([sys.executable, "-m", "pip", "freeze"]),
            "verus": verus, "z3": z3, "lynette": lynette,
            "gpu": logical_gpu, "gpu_inventory": command(gpu_query), "gpu_uuid": gpu_uuid,
            "cluster_requirements": {"path": os.environ.get("CLUSTER_REQS"),
                                     "sha256": digest(Path(os.environ["CLUSTER_REQS"]).read_bytes())
                                     if os.environ.get("CLUSTER_REQS") else None},
            "dependency_lock_sha256": digest((Path(os.environ["PROJECT_LIBS"]) / "requirements-resolved.txt").read_bytes())
            if os.environ.get("PROJECT_LIBS") else None,
            "prompts": file_hashes(prompt_directory(config.get("prompt_version", "v1")).glob("*.txt")),
            "sources": file_hashes([*(ROOT / "baseline").glob("*.py"),
                                   *([ROOT / "diagnostics/z3_probe.py", ROOT / "diagnostics/__init__.py"]
                                     if config.get("solver_feedback") else []),
                                   *([ROOT / "diagnostics/z3_internals.py"]
                                     if config.get("solver_feedback") == "internals" else [])]),
            "slurm": {k: os.environ.get(k) for k in ("SLURM_JOB_ID", "SLURM_JOB_NODELIST", "CUDA_VISIBLE_DEVICES")}}
    if config.get("solver_feedback") == "internals":
        from diagnostics.z3_internals import api_identity
        result["solver_api"] = api_identity()
    return result
