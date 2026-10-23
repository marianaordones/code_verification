"""GPU/import/kernel checks inside the allocation, before loading model weights."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import socket
import sys


def main():
    import torch
    import transformers
    import vllm
    from baseline.storage import write_json

    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not visible or visible in ("NoDevFiles", "-1"):
        raise SystemExit("SLURM did not assign CUDA_VISIBLE_DEVICES; GPU allocation is missing")
    if torch.cuda.device_count() != 1:
        raise SystemExit(f"Expected one logical GPU, found {torch.cuda.device_count()}; check SLURM device isolation. CUDA_VISIBLE_DEVICES={visible}")
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable: inspect driver/PyTorch wheel compatibility")
    if torch.__version__.split("+")[0] != "2.6.0" or transformers.__version__ != "4.51.3" or vllm.__version__ != "0.8.5":
        raise SystemExit("Unexpected PyTorch/Transformers/vLLM imports; inspect package cache and PYTHONPATH")
    properties = torch.cuda.get_device_properties(0)
    if properties.major < 8 or not torch.cuda.is_bf16_supported():
        raise SystemExit(f"GPU {properties.name} does not support the prescribed BF16 stack; request high_performance")
    if properties.total_memory < 35 * 1024**3:
        raise SystemExit(f"GPU {properties.name} has less than 35 GiB; Qwen3-8B BF16/context 32768 needs an A100/L40S-class allocation")
    x = torch.randn(512, 512, device="cuda:0", dtype=torch.bfloat16)
    (x @ x).sum().item()
    torch.cuda.synchronize()
    info = {"complete": True, "hostname": socket.gethostname(), "python": sys.executable,
            "python_version": sys.version, "libc": platform.libc_ver(),
            "torch": torch.__version__, "torch_file": torch.__file__, "cuda_build": torch.version.cuda,
            "vllm": vllm.__version__, "transformers": transformers.__version__,
            "cuda_available": True, "visible_gpu_count": 1, "cuda_visible_devices": visible,
            "gpu_name": properties.name, "gpu_memory_bytes": properties.total_memory,
            "compute_capability": [properties.major, properties.minor],
            "gpu_uuid": str(getattr(properties, "uuid", "unavailable")),
            "job_id": os.environ.get("SLURM_JOB_ID"),
            "requirements_sha256": __import__("hashlib").sha256(Path(os.environ["CLUSTER_REQS"]).read_bytes()).hexdigest(),
            "versions": {name: importlib.metadata.version(name) for name in ("torch", "vllm", "transformers", "numpy")}}
    path = Path("logs") / f"preflight-{os.environ.get('SLURM_JOB_ID', 'local')}.json"
    write_json(path, info)
    print(json.dumps(info, indent=2), flush=True)
    print("CUDA BF16 KERNEL PREFLIGHT PASSED", flush=True)


if __name__ == "__main__":
    main()
