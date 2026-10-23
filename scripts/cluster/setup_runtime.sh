#!/usr/bin/env bash
# Source from a job with `set -Eeuo pipefail`. No modules/venv required.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Use: source scripts/cluster/setup_runtime.sh" >&2
    exit 2
fi

PROJECT_ROOT="${SLURM_SUBMIT_DIR:?Submit from the repository root}"
cd "$PROJECT_ROOT"
REQS="${CLUSTER_REQS:-${PROJECT_ROOT}/requirements-cluster.txt}"
[[ -f "$REQS" ]] || { echo "Missing requirements: $REQS" >&2; return 20; }
command -v flock >/dev/null || { echo "Runtime requires the Linux flock command." >&2; return 20; }

# Ignore environment inherited from a login-node venv/module.
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_TARGET PIP_PREFIX PIP_USER
export PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export PIP_CACHE_DIR="${HOME}/pylibs/.wheel-cache"

PYTHON_BIN=""
for candidate in "${CLUSTER_PYTHON:-}" python3.12 python3.11 python3; do
    [[ -n "$candidate" ]] || continue
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    [[ -n "$resolved" ]] || continue
    if "$resolved" -c 'import sys,platform; assert (3,11) <= sys.version_info[:2] <= (3,12); assert platform.system()=="Linux" and platform.machine()=="x86_64"' 2>/dev/null; then
        PYTHON_BIN="$resolved"
        break
    fi
done
[[ -n "$PYTHON_BIN" ]] || { echo "No Linux x86_64 Python 3.11/3.12 on $(hostname). Set CLUSTER_PYTHON to a standalone interpreter." >&2; return 21; }

PYTHON_TAG="$("$PYTHON_BIN" -c 'import sys,platform; print("py%d%d-%s-%s" % (*sys.version_info[:2], platform.machine(), "".join(platform.libc_ver())))')"
REQ_HASH="$(sha256sum "$REQS" | awk '{print $1}')"
PROJECT_LIBS="${HOME}/pylibs/verus-${PYTHON_TAG}-${REQ_HASH:0:16}"
export PYTHON_BIN PROJECT_LIBS

FREE_TMP_GB="$(df -Pk /tmp 2>/dev/null | awk 'NR==2 {print int($4/1048576)}')" || FREE_TMP_GB=0
if [[ "${FREE_TMP_GB:-0}" -ge 25 ]]; then
    tmp_parent=/tmp
else
    tmp_parent="${HOME}/pylibs/.tmp"
fi
mkdir -p "$tmp_parent"
JOB_TMP="$(mktemp -d "${tmp_parent}/verus-${SLURM_JOB_ID:-local}-XXXXXXXX")"
export TMPDIR="$JOB_TMP"
# Remove only this exact, newly-created job directory, after checking its parent.
runtime_cleanup() {
    if declare -F native_cleanup >/dev/null; then native_cleanup; fi
    if [[ -n "${monitor_pid:-}" ]]; then kill "$monitor_pid" 2>/dev/null || true; fi
    if [[ -n "${VLLM_IPC_TMP:-}" && "$VLLM_IPC_TMP" == "${VLLM_IPC_PARENT}/vipc-"* && -d "$VLLM_IPC_TMP" && ! -L "$VLLM_IPC_TMP" ]]; then
        rm -rf -- "$VLLM_IPC_TMP"
    fi
    if [[ -n "${JOB_TMP:-}" && "$JOB_TMP" == "$tmp_parent"/verus-* && -d "$JOB_TMP" && ! -L "$JOB_TMP" ]]; then
        rm -rf -- "$JOB_TMP"
    fi
}
trap runtime_cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# A cache is visible only after successful install/import validation and rename.
# flock prevents two jobs installing or publishing the same cache concurrently.
mkdir -p "${HOME}/pylibs"
exec 9>"${PROJECT_LIBS}.lock"
flock 9
if [[ ! -f "${PROJECT_LIBS}/.complete" ]]; then
    if [[ -e "$PROJECT_LIBS" ]]; then
        echo "Incomplete cache at $PROJECT_LIBS; inspect/rename it before retrying." >&2
        return 22
    fi
    LIBS_STAGE="$(mktemp -d "${PROJECT_LIBS}.partial.XXXXXXXX")"
    if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
        # Bootstrap only inside job storage, without modifying system Python.
        "$PYTHON_BIN" - "$JOB_TMP/get-pip.py" <<'PY'
import sys, urllib.request
urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", sys.argv[1])
PY
        "$PYTHON_BIN" "$JOB_TMP/get-pip.py" --target "$JOB_TMP/pip" --no-cache-dir 'pip==25.0.1'
        export PYTHONPATH="$JOB_TMP/pip"
    fi
    echo "Installing cluster requirements into $LIBS_STAGE"
    # Wheels only: fail clearly instead of unexpectedly building vLLM/PyTorch.
    if ! "$PYTHON_BIN" -m pip install --only-binary=:all: --target "$LIBS_STAGE" -r "$REQS"; then
        echo "Install failed. Partial cache retained for diagnosis: $LIBS_STAGE" >&2
        return 23
    fi
    PYTHONPATH="$LIBS_STAGE" "$PYTHON_BIN" - "$LIBS_STAGE" "$REQ_HASH" <<'PY'
import importlib.metadata as m, json, pathlib, sys
import numpy, torch, transformers, vllm
root = pathlib.Path(sys.argv[1])
assert torch.__version__.split("+")[0] == "2.6.0", torch.__version__
assert vllm.__version__ == "0.8.5", vllm.__version__
assert transformers.__version__ == "4.51.3", transformers.__version__
assert numpy.__version__ == "1.26.4", numpy.__version__
packages = sorted(f"{d.metadata['Name']}=={d.version}" for d in m.distributions(path=[str(root)]))
(root / "requirements-resolved.txt").write_text("\n".join(packages) + "\n")
(root / ".complete").write_text(json.dumps({"requirements_sha256":sys.argv[2], "python":sys.version}))
PY
    mv -T -- "$LIBS_STAGE" "$PROJECT_LIBS"
else
    "$PYTHON_BIN" - "$PROJECT_LIBS/.complete" "$REQ_HASH" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))["requirements_sha256"] == sys.argv[2], "Cache requirements hash mismatch"
PY
    echo "Reusing complete cache: $PROJECT_LIBS"
fi
flock -u 9
exec 9>&-

mkdir -p "$JOB_TMP/bin"
printf '#!/usr/bin/env bash\nexec "%s" "$@"\n' "$PYTHON_BIN" > "$JOB_TMP/bin/python"
chmod +x "$JOB_TMP/bin/python"
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_LIBS}"
export PATH="${JOB_TMP}/bin:${PROJECT_LIBS}/bin:${HOME}/.cargo/bin:${PATH}"
# IPC sockets need only a tiny directory and must not inherit the HOME fallback
# chosen above for large package downloads. Validate real ZMQ bind/send/receive
# before importing vLLM or loading model weights.
VLLM_IPC_TMP="$("$PYTHON_BIN" scripts/cluster/prepare_ipc.py)"
VLLM_IPC_PARENT="$(dirname "$VLLM_IPC_TMP")"
export VLLM_RPC_BASE_PATH="$VLLM_IPC_TMP"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export MKL_NUM_THREADS="$OMP_NUM_THREADS" OPENBLAS_NUM_THREADS="$OMP_NUM_THREADS"
export HF_HOME="${HF_HOME:-${HOME}/.cache/huggingface}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"
export TORCH_EXTENSIONS_DIR="${PROJECT_ROOT}/.cluster/torch-extensions/${PYTHON_TAG}"
export TRITON_CACHE_DIR="${JOB_TMP}/triton"
export VLLM_WORKER_MULTIPROC_METHOD=spawn
echo "python=$PYTHON_BIN"
echo "package_cache=$PROJECT_LIBS"
echo "requirements_sha256=$REQ_HASH"
echo "tmpdir=$JOB_TMP"
echo "vllm_rpc_base_path=$VLLM_RPC_BASE_PATH (ZMQ IPC probe passed)"
